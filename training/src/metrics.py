"""Metrics and calibration measurement.

Thin, explicit wrappers so the numbers in the reports are traceable to one place.
"""
from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.metrics import average_precision_score


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    phat = k / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return [max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)]


def bootstrap_metric_ci(
    y_true: np.ndarray,
    p: np.ndarray,
    n_boot: int = 400,
    seed: int = 42,
) -> dict:
    """Percentile bootstrap confidence intervals for the headline metrics.

    Resamples applicants with replacement. Gives a sense of sampling noise only:
    it does not cover dataset shift, label noise or model-selection uncertainty.
    """
    y = np.asarray(y_true)
    p = np.asarray(p, dtype=float)
    n = len(y)
    if n == 0:
        return {}
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {"roc_auc": [], "pr_auc": [], "brier": []}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yy, pp = y[idx], p[idx]
        if len(np.unique(yy)) < 2:
            continue
        draws["roc_auc"].append(float(roc_auc_score(yy, pp)))
        draws["pr_auc"].append(float(average_precision_score(yy, pp)))
        draws["brier"].append(float(brier_score_loss(yy, pp)))
    out: dict = {
        "method": "percentile bootstrap (resampling applicants with replacement)",
        "n_boot": n_boot,
        "seed": seed,
    }
    for metric, values in draws.items():
        if len(values) >= 20:
            lo, hi = np.percentile(values, [2.5, 97.5])
            out[metric] = {"ci_low": float(lo), "ci_high": float(hi), "n_boot_used": len(values)}
    return out


def classification_metrics(
    y_true: np.ndarray, p: np.ndarray, threshold: float = 0.5, ci: bool = False
) -> dict:
    """Standard metrics treating default (1) as the positive class."""
    y = np.asarray(y_true)
    p = np.asarray(p, dtype=float)
    yhat = (p >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    out = {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "threshold": float(threshold),
        "precision": float(precision_score(y, yhat, zero_division=0)),
        "recall": float(recall_score(y, yhat, zero_division=0)),
        "f1": float(f1_score(y, yhat, zero_division=0)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }
    if ci:
        out["intervals"] = bootstrap_metric_ci(y, p)
    return out


def calibration_curve_data(y_true: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict:
    """Reliability curve plus expected calibration error."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    ece = 0.0
    n = len(p)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {"bin_lower": float(lo), "bin_upper": float(hi), "count": 0,
                 "mean_predicted": None, "observed_rate": None}
            )
            continue
        mean_pred = float(p[mask].mean())
        observed = float(y[mask].mean())
        ece += (count / n) * abs(observed - mean_pred)
        bins.append(
            {
                "bin_lower": float(lo),
                "bin_upper": float(hi),
                "count": count,
                "mean_predicted": mean_pred,
                "observed_rate": observed,
                "observed_ci": _wilson(int(y[mask].sum()), count),
            }
        )
    return {"bins": bins, "ece": float(ece), "n_bins": n_bins}
