"""Live drift and adversarial-validation alerting.

The offline report in ``training/src/drift.py`` compares split against split.
This module watches **fresh traffic**: it compares the most recent submissions
(binned feature summaries logged by the API) against the stored training
reference and raises an alert when the population has moved.

Two statistics per feature:

* **PSI** against the stored decile bins -- the standard "has the population
  moved?" measure.
* **KS** against a stored reference sample -- sensitive to shape changes.

A one-dimensional KS also gives a cheap **adversarial-validation proxy**: if a
fresh sample is easy to tell apart from the reference, ``0.5 + KS/2`` climbs
above 0.5. A real adversarial-validation model trains a classifier to separate
train from production; the proxy captures the same signal at zero runtime cost.

When storage is not configured (the Vercel default) there is no live stream, so
the endpoint falls back to a **clearly-labelled simulated window**.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from ..core.config import get_settings
from .psi import (
    KS_MODERATE,
    PSI_MODERATE,
    ks_two_sample,
    psi_from_proportions,
    verdict_ks,
    verdict_psi,
)

MIN_WINDOW = 25


@lru_cache(maxsize=1)
def load_reference() -> dict | None:
    path = get_settings().reference_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _binned(values: list[float], edges: list[float]) -> np.ndarray:
    full = np.array([-np.inf, *edges, np.inf], dtype=float)
    counts, _ = np.histogram(np.asarray(values, dtype=float), bins=full)
    return counts


def _simulated_window(reference: dict, n: int = 400, shift: float = 0.0) -> list[dict]:
    """Deterministic pseudo-window drawn from the stored reference sample.

    ``shift`` (in standard deviations) lets callers *demonstrate* an alert.
    """
    rng = np.random.default_rng(7)
    rows: list[dict] = []
    numeric = reference.get("numeric", {})
    for i in range(n):
        row: dict = {}
        for col, spec in numeric.items():
            sample = np.asarray(spec.get("sample", []), dtype=float)
            if len(sample) == 0:
                continue
            base = float(rng.choice(sample))
            sd = float(np.std(sample)) or 1.0
            row[col] = base + shift * sd
        rows.append(row)
    return rows


def _categorical_simulated(reference: dict, n: int, rng) -> list[dict]:
    rows = []
    cats = reference.get("categorical", {})
    for _ in range(n):
        row = {}
        for col, spec in cats.items():
            props = spec.get("expected_proportions", {})
            if not props:
                continue
            keys = list(props.keys())
            p = np.array([props[k] for k in keys], dtype=float)
            p = p / p.sum()
            row[col] = str(rng.choice(keys, p=p))
        rows.append(row)
    return rows


def evaluate(current_rows: list[dict], window_label: str, simulated: bool) -> dict:
    """Compare a window of fresh rows against the stored reference."""
    reference = load_reference()
    if reference is None:
        return {
            "available": False,
            "note": "Reference distributions not found. Re-run training.",
        }

    current_rows = current_rows or []
    if len(current_rows) < MIN_WINDOW:
        return {
            "available": True,
            "enough_data": False,
            "n": len(current_rows),
            "min_window": MIN_WINDOW,
            "note": (
                f"Only {len(current_rows)} recent rows; at least {MIN_WINDOW} are "
                "needed before drift is meaningful."
            ),
            "alert": False,
            "window": window_label,
            "simulated": simulated,
        }

    features: dict[str, dict] = {}
    max_psi = 0.0
    max_ks = 0.0
    alerts: list[dict] = []

    for col, spec in reference.get("numeric", {}).items():
        values = [r.get(col) for r in current_rows if r.get(col) is not None]
        values = [float(v) for v in values if v == v]
        if not values:
            continue
        edges = spec.get("edges", [])
        expected = spec.get("expected_proportions", [])
        counts = _binned(values, edges)
        total = counts.sum() or 1
        psi = psi_from_proportions(np.asarray(expected, dtype=float), counts / total)
        ks, n = ks_two_sample(values, spec.get("sample", []))
        max_psi, max_ks = max(max_psi, psi), max(max_ks, ks)
        entry = {
            "type": "numeric",
            "n": n,
            "psi": float(psi),
            "psi_verdict": verdict_psi(psi),
            "ks": float(ks),
            "ks_verdict": verdict_ks(ks),
        }
        features[col] = entry
        if psi >= PSI_MODERATE or ks >= KS_MODERATE:
            alerts.append({"feature": col, "statistic": "psi" if psi >= PSI_MODERATE else "ks",
                           "value": entry["psi"] if psi >= PSI_MODERATE else entry["ks"]})

    for col, spec in reference.get("categorical", {}).items():
        expected = spec.get("expected_proportions", {})
        if not expected:
            continue
        counts: dict[str, int] = {}
        for r in current_rows:
            v = r.get(col)
            if v is None:
                continue
            counts[str(v)] = counts.get(str(v), 0) + 1
        if not counts:
            continue
        total = sum(counts.values())
        keys = sorted(set(expected) | set(counts))
        cur = np.array([counts.get(k, 0) / total for k in keys], dtype=float)
        exp = np.array([expected.get(k, 0.0) for k in keys], dtype=float)
        psi = psi_from_proportions(exp, cur)
        max_psi = max(max_psi, psi)
        features[col] = {
            "type": "categorical",
            "psi": float(psi),
            "psi_verdict": verdict_psi(psi),
            "ks": None,
        }
        if psi >= PSI_MODERATE:
            alerts.append({"feature": col, "statistic": "psi", "value": float(psi)})

    adversarial_auc = 0.5 + max_ks / 2.0
    alert = len(alerts) > 0
    severity = "ok"
    if max_psi >= PSI_MODERATE or max_ks >= KS_MODERATE:
        severity = "warning"
    if max_psi >= 0.5 or max_ks >= 0.4:
        severity = "critical"

    return {
        "available": True,
        "enough_data": True,
        "n": len(current_rows),
        "window": window_label,
        "simulated": simulated,
        "alert": alert,
        "severity": severity,
        "max_psi": float(max_psi),
        "max_ks": float(max_ks),
        "features": features,
        "alerts": alerts,
        "adversarial_validation": {
            "proxy_auc": float(adversarial_auc),
            "note": (
                "0.5 = production is indistinguishable from training; values above "
                "0.6 mean a simple model can separate them, a drift warning sign."
            ),
        },
        "thresholds": {"psi_moderate": PSI_MODERATE, "ks_moderate": KS_MODERATE},
        "note": (
            "Simulated window (no live stream configured)."
            if simulated
            else "Computed from logged recent submissions."
        ),
    }


def live_drift(current_rows: list[dict] | None = None, shift: float = 0.0) -> dict:
    """Evaluate logged rows, or a simulated window when none are available."""
    reference = load_reference()
    if reference is None:
        return {"available": False, "note": "Reference distributions not found."}
    if current_rows and len(current_rows) >= MIN_WINDOW:
        return evaluate(current_rows, "logged submissions", simulated=False)
    rng = np.random.default_rng(11)
    rows = _simulated_window(reference, n=400, shift=shift)
    rows = [{**r, **_categorical_simulated(reference, 1, rng)[0]} for r in rows]
    label = "simulated window" + (" (shift injected)" if shift else "")
    return evaluate(rows, label, simulated=True)


# ---------------------------------------------------------------------------
# Privacy-safe path: binned counts only
# ---------------------------------------------------------------------------
def bins_for_row(row: dict) -> dict:
    """Convert a raw applicant row into bin indices + categories for logging.

    Only bin indices and category codes are stored, never the underlying values,
    so the live monitor can compute PSI without holding personal data.
    """
    reference = load_reference()
    if not reference:
        return {}
    bins: dict = {}
    cats: dict = {}
    for col, spec in reference.get("numeric", {}).items():
        value = row.get(col)
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value != value:
            continue
        edges = np.asarray(spec.get("edges", []), dtype=float)
        bins[col] = int(np.searchsorted(edges, value, side="right"))
    for col in reference.get("categorical", {}):
        value = row.get(col)
        if value is not None:
            cats[col] = str(value)
    return {"bins": bins, "cats": cats}


def _psi_from_bin_counts(counts: list[int], expected: list[float]) -> float:
    total = sum(counts) or 1
    cur = np.array([c / total for c in counts], dtype=float)
    exp = np.array(expected[: len(counts)], dtype=float)
    if len(exp) < len(cur):
        exp = np.concatenate([exp, np.zeros(len(cur) - len(exp))])
    return psi_from_proportions(exp, cur)


def evaluate_binned(
    bin_counts: dict, cat_counts: dict, n: int, simulated: bool, window_label: str
) -> dict:
    """PSI from pre-computed bin counts (the privacy-safe live path)."""
    reference = load_reference()
    if reference is None:
        return {"available": False, "note": "Reference distributions not found."}
    if n < MIN_WINDOW:
        return {
            "available": True,
            "enough_data": False,
            "n": n,
            "min_window": MIN_WINDOW,
            "alert": False,
            "window": window_label,
            "simulated": simulated,
            "note": f"Only {n} recent submissions; need {MIN_WINDOW}.",
        }

    features: dict = {}
    alerts: list = []
    max_psi = 0.0
    for col, spec in reference.get("numeric", {}).items():
        counts = bin_counts.get(col)
        if not counts:
            continue
        psi = _psi_from_bin_counts(counts, spec.get("expected_proportions", []))
        max_psi = max(max_psi, psi)
        features[col] = {"type": "numeric", "psi": float(psi), "psi_verdict": verdict_psi(psi)}
        if psi >= PSI_MODERATE:
            alerts.append({"feature": col, "statistic": "psi", "value": float(psi)})

    for col, spec in reference.get("categorical", {}).items():
        counts = cat_counts.get(col)
        if not counts:
            continue
        expected = spec.get("expected_proportions", {})
        total = sum(counts.values()) or 1
        keys = sorted(set(expected) | set(counts))
        cur = np.array([counts.get(k, 0) / total for k in keys], dtype=float)
        exp = np.array([expected.get(k, 0.0) for k in keys], dtype=float)
        psi = psi_from_proportions(exp, cur)
        max_psi = max(max_psi, psi)
        features[col] = {"type": "categorical", "psi": float(psi), "psi_verdict": verdict_psi(psi)}
        if psi >= PSI_MODERATE:
            alerts.append({"feature": col, "statistic": "psi", "value": float(psi)})

    severity = "ok"
    if max_psi >= PSI_MODERATE:
        severity = "warning"
    if max_psi >= 0.5:
        severity = "critical"

    return {
        "available": True,
        "enough_data": True,
        "n": n,
        "window": window_label,
        "simulated": simulated,
        "alert": len(alerts) > 0,
        "severity": severity,
        "max_psi": float(max_psi),
        "max_ks": None,
        "features": features,
        "alerts": alerts,
        "adversarial_validation": {
            "proxy_auc": float(0.5 + min(0.45, max_psi / 2.0)),
            "note": "Proxy derived from PSI (bin-count path; no raw samples stored).",
        },
        "thresholds": {"psi_moderate": PSI_MODERATE, "ks_moderate": KS_MODERATE},
        "note": (
            "Simulated window (no live stream configured)."
            if simulated
            else "Computed from binned recent submissions."
        ),
    }
