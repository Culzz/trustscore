"""Portfolio analytics: policy simulation, A/B comparison and bias injection.

All of this runs on the bundled **policy tuning set**
(``api/artifacts/portfolio.json``, the validation split), so the audit console can
show real, group-aware numbers live -- approval rates, cost, profitability,
disparate impact, equalized odds -- without a database and without touching
applicant data. The final test split is deliberately **not** shipped: it stays a
one-time held-out evaluation (see ``docs/EVALUATION.md`` and the
``evaluation_protocol`` block in metadata).

Three things live here:

* :func:`simulate` -- apply a policy (thresholds, cost matrix, optional
  mitigation) to the portfolio and return the KPIs plus the fairness guardrail.
* :func:`sweep` -- repeat that across approve thresholds to draw a trade-off
  curve.
* :func:`bias_inject` -- deliberately skew a group's scores so the guardrail can
  be seen firing, then show whether mitigation recovers it. This is the "bias
  injector": a teaching tool with no effect on the real model.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

import numpy as np

from ..core.config import get_settings
from .decision import APPROVE, DECLINE, REFER
from .mitigation import apply_equalized_odds

DEFAULT_MARGIN_RATE = 0.12  # margin earned on a repaid loan, as a share of exposure
DEFAULT_LOSS_GIVEN_DEFAULT = 1.0  # loss on a default, as a share of exposure

# Human labels for the audited attributes, so the API can name a breaching
# attribute without the UI having to carry its own lookup table.
ATTRIBUTE_LABELS = {
    "age_band": "Age band",
    "income_band": "Income band",
    "person_home_ownership": "Home ownership",
    "loan_intent": "Loan purpose",
    "cb_person_default_on_file": "Prior default on file",
}


@lru_cache(maxsize=1)
def load_portfolio() -> dict | None:
    """Load the bundled portfolio slice, or None when it has not been built."""
    path = get_settings().portfolio_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _group_arrays(portfolio: dict) -> dict[str, np.ndarray]:
    """Per-attribute group labels for the slice.

    Current artifacts store one integer code per attribute per row alongside a
    ``levels`` table (compact, and it keeps every audited attribute available for
    mitigation, A/B and the bias injector). Older single-attribute artifacts
    stored the group label directly in column 1; both shapes are supported.
    """
    rows = portfolio["rows"]
    attributes = portfolio.get("attributes")
    if attributes and rows and isinstance(rows[0][-1], list):
        levels = portfolio.get("levels", {})
        return {
            attribute: np.array(
                [levels[attribute][int(row[3][i])] for row in rows], dtype=object
            )
            for i, attribute in enumerate(attributes)
        }
    attribute = portfolio.get("group_attribute", "age_band")
    return {attribute: np.array([r[1] for r in rows], dtype=object)}


def available_attributes(portfolio: dict) -> list[str]:
    return list(_group_arrays(portfolio).keys())


def _arrays(portfolio: dict, attribute: str | None = None):
    rows = portfolio["rows"]
    pd = np.array([r[0] for r in rows], dtype=float)
    if isinstance(rows[0][-1], list):
        exposure = np.array([r[1] for r in rows], dtype=float)
        y = np.array([r[2] for r in rows], dtype=float)
    else:
        exposure = np.array([r[2] for r in rows], dtype=float)
        y = np.array([r[3] for r in rows], dtype=float)

    groups_by_attribute = _group_arrays(portfolio)
    key = attribute or portfolio.get("group_attribute", "age_band")
    if key not in groups_by_attribute:
        raise ValueError(
            f"unknown attribute '{key}'. Available: {sorted(groups_by_attribute)}"
        )
    return pd, groups_by_attribute[key], exposure, y, key


# ---------------------------------------------------------------------------
# Fairness helpers (kept local so the training package is not a dependency)
# ---------------------------------------------------------------------------
def _selection_rates(groups: np.ndarray, approved: np.ndarray, min_size: int = 30) -> dict:
    out: dict[str, dict] = {}
    for g in sorted({str(x) for x in groups.tolist()}):
        mask = groups == g
        n = int(mask.sum())
        if n == 0:
            continue
        out[g] = {"group": g, "n": n, "selection_rate": float(approved[mask].mean())}
    return out


def _di_ratio(per_group: dict, min_size: int = 30) -> float | None:
    rates = [v["selection_rate"] for v in per_group.values() if v["n"] >= min_size]
    if len(rates) < 2 or max(rates) <= 0:
        return None
    return float(min(rates) / max(rates))


def _eo_difference(
    y: np.ndarray, groups: np.ndarray, approved: np.ndarray, min_size: int = 30
) -> float | None:
    tprs, fprs = [], []
    for g in sorted({str(x) for x in groups.tolist()}):
        mask = groups == g
        if int(mask.sum()) < min_size:
            continue
        y_g = y[mask]
        a_g = approved[mask]
        repaid = y_g == 0
        defaulted = y_g == 1
        if repaid.any():
            tprs.append(float(a_g[repaid].mean()))
        if defaulted.any():
            fprs.append(float(a_g[defaulted].mean()))
    if len(tprs) < 2:
        return None
    tpr_gap = max(tprs) - min(tprs)
    fpr_gap = (max(fprs) - min(fprs)) if len(fprs) >= 2 else 0.0
    return float(max(tpr_gap, fpr_gap))


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for a proportion."""
    if n <= 0:
        return None
    phat = k / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return [max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)]


def _bootstrap_di_eo(
    groups: np.ndarray,
    approved: np.ndarray,
    y: np.ndarray,
    min_size: int = 30,
    n_boot: int = 300,
    seed: int = 42,
) -> dict:
    """Percentile bootstrap CIs for DI and the equalized-odds gap.

    Group sample sizes vary by orders of magnitude here, so a bare point estimate
    invites over-reading. Resamples applicants with replacement.
    """
    labels = sorted({str(x) for x in groups.tolist()})
    code_of = {label: i for i, label in enumerate(labels)}
    codes = np.array([code_of[str(g)] for g in groups.tolist()], dtype=int)
    counts_all = np.bincount(codes, minlength=len(labels))
    keep = np.array([counts_all[c] >= min_size for c in codes])
    codes = np.where(keep, codes, -1)
    n = len(codes)
    appr_rep = approved.astype(float) * (y == 0).astype(float)
    appr_defd = approved.astype(float) * (y == 1).astype(float)
    rng = np.random.default_rng(seed)
    di_draws: list[float] = []
    eo_draws: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        g = codes[idx]
        m = g >= 0
        if not m.any():
            continue
        gc = g[m]
        counts = np.bincount(gc, minlength=len(labels)).astype(float)
        a = np.bincount(gc, weights=approved[idx][m].astype(float), minlength=len(labels))
        rep = np.bincount(gc, weights=(y[idx][m] == 0).astype(float), minlength=len(labels))
        dfd = np.bincount(gc, weights=(y[idx][m] == 1).astype(float), minlength=len(labels))
        ar = np.bincount(gc, weights=appr_rep[idx][m], minlength=len(labels))
        ad = np.bincount(gc, weights=appr_defd[idx][m], minlength=len(labels))
        sr = np.where(counts > 0, a / np.maximum(counts, 1.0), np.nan)
        tpr = np.where(rep > 0, ar / np.maximum(rep, 1.0), np.nan)
        fpr = np.where(dfd > 0, ad / np.maximum(dfd, 1.0), np.nan)
        sr_ok = sr[np.isfinite(sr)]
        if len(sr_ok) >= 2 and sr_ok.max() > 0:
            di_draws.append(float(sr_ok.min() / sr_ok.max()))
        tpr_ok = tpr[np.isfinite(tpr)]
        fpr_ok = fpr[np.isfinite(fpr)]
        if len(tpr_ok) >= 2 or len(fpr_ok) >= 2:
            eo_draws.append(
                max(
                    float(tpr_ok.max() - tpr_ok.min()) if len(tpr_ok) >= 2 else 0.0,
                    float(fpr_ok.max() - fpr_ok.min()) if len(fpr_ok) >= 2 else 0.0,
                )
            )

    def _pct(draws: list[float]) -> list[float] | None:
        if len(draws) < 20:
            return None
        return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]

    return {
        "n_boot": n_boot,
        "method": "percentile bootstrap (resampling applicants with replacement)",
        "disparate_impact_ratio_ci": _pct(di_draws),
        "equalized_odds_difference_ci": _pct(eo_draws),
    }


def _fairness_table(
    y: np.ndarray, groups: np.ndarray, approved: np.ndarray, exposure: np.ndarray
) -> list[dict]:
    rows = []
    for g in sorted({str(x) for x in groups.tolist()}):
        mask = groups == g
        n = int(mask.sum())
        if n == 0:
            continue
        y_g = y[mask]
        a_g = approved[mask]
        repaid = y_g == 0
        defaulted = y_g == 1
        rows.append(
            {
                "group": g,
                "n": n,
                "selection_rate": float(a_g.mean()),
                "selection_rate_ci": _wilson(int(a_g.sum()), n),
                "tpr": float(a_g[repaid].mean()) if repaid.any() else None,
                "tpr_ci": _wilson(int(a_g[repaid].sum()), int(repaid.sum())) if repaid.any() else None,
                "fpr": float(a_g[defaulted].mean()) if defaulted.any() else None,
                "fpr_ci": _wilson(int(a_g[defaulted].sum()), int(defaulted.sum())) if defaulted.any() else None,
                "mean_exposure": float(exposure[mask].mean()),
                "low_sample": n < 30,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------
def _decide_bands(pd: np.ndarray, approve_max_pd: float, decline_min_pd: float) -> np.ndarray:
    out = np.full(pd.shape, REFER, dtype=object)
    out[pd <= approve_max_pd] = APPROVE
    out[pd >= decline_min_pd] = DECLINE
    return out


def simulate(
    portfolio: dict,
    approve_max_pd: float,
    decline_min_pd: float,
    costs: dict | None = None,
    apply_fairness: bool = False,
    mitigation_params: dict | None = None,
    floor: float = 0.80,
    margin_rate: float = DEFAULT_MARGIN_RATE,
    loss_given_default: float = DEFAULT_LOSS_GIVEN_DEFAULT,
    pd_override: np.ndarray | None = None,
    attribute: str | None = None,
    with_ci: bool = True,
) -> dict:
    """Apply a policy to the portfolio and return KPIs + the fairness guardrail.

    ``attribute`` selects which audited attribute the fairness metrics (and, when
    mitigation is on, the equalized-odds groups) refer to. It defaults to the
    slice's primary attribute so the sweep curve stays comparable.
    """
    pd, groups, exposure, y, key = _arrays(portfolio, attribute)
    if pd_override is not None:
        pd = np.asarray(pd_override, dtype=float)

    costs = costs or {"false_approve": 1.0, "false_decline": 0.2, "review": 0.05}
    cfa = float(costs.get("false_approve", 1.0))
    cfd = float(costs.get("false_decline", 0.2))
    crv = float(costs.get("review", 0.05))

    approved = pd <= approve_max_pd
    mitigation_note = None
    if apply_fairness and mitigation_params:
        # Row keys are derived the same way as the offline measurement *of this
        # set* (the tuning-set artifact records the shared prefix), so the
        # randomised tie-break -- and therefore every reported fairness figure --
        # is reproducible instead of flickering between runs.
        prefix = portfolio.get("row_key_prefix", "tuning")
        approved = apply_equalized_odds(
            pd, groups, mitigation_params, keys=[f"{prefix}:{i}" for i in range(len(pd))]
        )
        mitigation_note = (
            "Equalized-odds thresholds were fitted at the training approve "
            f"threshold ({mitigation_params.get('base_threshold'):.4f}); they are "
            "applied here as-is."
        )

    decisions = _decide_bands(pd, approve_max_pd, decline_min_pd)
    # Reconcile the mitigated binary decision with the three-band display.
    decisions = np.where(
        approved & (decisions != APPROVE),
        APPROVE,
        np.where((~approved) & (decisions == APPROVE), REFER, decisions),
    )

    is_approve = decisions == APPROVE
    is_decline = decisions == DECLINE
    is_refer = ~is_approve & ~is_decline

    total_exposure = float(exposure.sum()) or 1.0
    expected_cost = (
        cfa * float(np.sum(pd[is_approve] * exposure[is_approve]))
        + cfd * float(np.sum((1 - pd[is_decline]) * exposure[is_decline]))
        + crv * float(np.sum(exposure[is_refer]))
    )
    realized_cost = (
        cfa * float(np.sum(y[is_approve] * exposure[is_approve]))
        + cfd * float(np.sum((1 - y[is_decline]) * exposure[is_decline]))
        + crv * float(np.sum(exposure[is_refer]))
    )

    # Simple profitability model on the approved book.
    profit = float(
        np.sum((1 - y[is_approve]) * margin_rate * exposure[is_approve])
        - np.sum(y[is_approve] * loss_given_default * exposure[is_approve])
    )

    per_group = _selection_rates(groups, is_approve)
    di = _di_ratio(per_group)
    eo = _eo_difference(y, groups, is_approve)
    uncertainty = (
        _bootstrap_di_eo(groups, is_approve, y) if with_ci else None
    )

    band_counts = {
        APPROVE: int(is_approve.sum()),
        REFER: int(is_refer.sum()),
        DECLINE: int(is_decline.sum()),
    }

    breaches = []
    if di is not None and di < floor:
        eligible = [v for v in per_group.values() if v["n"] >= 30]
        if eligible:
            worst = min(eligible, key=lambda v: v["selection_rate"])
            breaches.append(
                {
                    "attribute": key,
                    "label": ATTRIBUTE_LABELS.get(key, key),
                    "disparate_impact_ratio": di,
                    "disparate_impact_ratio_ci": (
                        uncertainty or {}
                    ).get("disparate_impact_ratio_ci"),
                    "floor": floor,
                    "lowest_group": worst["group"],
                    "lowest_group_n": worst["n"],
                    "lowest_selection_rate": worst["selection_rate"],
                }
            )

    return {
        "n": int(len(pd)),
        "evaluation_set": portfolio.get("set", "validation"),
        "evaluation_role": portfolio.get("role", "policy_tuning"),
        "approve_max_pd": float(approve_max_pd),
        "decline_min_pd": float(decline_min_pd),
        "apply_fairness": bool(apply_fairness),
        "approval_rate": float(is_approve.mean()),
        "band_counts": band_counts,
        "band_shares": {k: float(v / len(pd)) for k, v in band_counts.items()},
        "expected_cost_per_loan": float(expected_cost / total_exposure),
        "realized_cost_per_loan": float(realized_cost / total_exposure),
        "profit_total": profit,
        "profit_per_loan": float(profit / len(pd)),
        "margin_rate": margin_rate,
        "loss_given_default": loss_given_default,
        "disparate_impact_ratio": di,
        "equalized_odds_difference": eo,
        "uncertainty": uncertainty,
        "fairness_table": _fairness_table(y, groups, is_approve, exposure),
        "group_attribute": key,
        "guardrail": {
            "disparate_impact_floor": floor,
            "passed": len(breaches) == 0,
            "n_breaches": len(breaches),
            "breaches": breaches,
        },
        "mitigation_note": mitigation_note,
    }


def sweep(
    portfolio: dict,
    approve_thresholds: list[float],
    decline_min_pd: float,
    costs: dict | None = None,
    floor: float = 0.80,
    margin_rate: float = DEFAULT_MARGIN_RATE,
    loss_given_default: float = DEFAULT_LOSS_GIVEN_DEFAULT,
    attribute: str | None = None,
) -> dict:
    """Trade-off curve: approval rate, cost, profit and DI across cut-offs."""
    points = []
    group_attribute = portfolio.get("group_attribute", "age_band")
    for t in approve_thresholds:
        res = simulate(
            portfolio,
            float(t),
            decline_min_pd,
            costs=costs,
            floor=floor,
            margin_rate=margin_rate,
            loss_given_default=loss_given_default,
            attribute=attribute,
            with_ci=False,
        )
        group_attribute = res["group_attribute"]
        points.append(
            {
                "approve_max_pd": float(t),
                "approval_rate": res["approval_rate"],
                "expected_cost_per_loan": res["expected_cost_per_loan"],
                "realized_cost_per_loan": res["realized_cost_per_loan"],
                "profit_per_loan": res["profit_per_loan"],
                "disparate_impact_ratio": res["disparate_impact_ratio"],
                "guardrail_passed": res["guardrail"]["passed"],
            }
        )
    return {"points": points, "group_attribute": group_attribute}


def ab_compare(
    portfolio: dict,
    approve_max_pd: float,
    decline_min_pd: float,
    costs: dict | None = None,
    mitigation_params: dict | None = None,
    floor: float = 0.80,
    attribute: str | None = None,
) -> dict:
    """Alpha (baseline) vs Beta (fairness-tuned) on the same portfolio."""
    alpha = simulate(
        portfolio, approve_max_pd, decline_min_pd, costs=costs, floor=floor, attribute=attribute
    )
    beta = simulate(
        portfolio,
        approve_max_pd,
        decline_min_pd,
        costs=costs,
        apply_fairness=bool(mitigation_params),
        mitigation_params=mitigation_params,
        floor=floor,
        attribute=attribute,
    )
    delta = {
        "approval_rate": beta["approval_rate"] - alpha["approval_rate"],
        "expected_cost_per_loan": beta["expected_cost_per_loan"] - alpha["expected_cost_per_loan"],
        "profit_per_loan": beta["profit_per_loan"] - alpha["profit_per_loan"],
        "disparate_impact_ratio": (
            (beta["disparate_impact_ratio"] or 0.0) - (alpha["disparate_impact_ratio"] or 0.0)
            if alpha["disparate_impact_ratio"] is not None
            and beta["disparate_impact_ratio"] is not None
            else None
        ),
        "equalized_odds_difference": (
            (beta["equalized_odds_difference"] or 0.0)
            - (alpha["equalized_odds_difference"] or 0.0)
            if alpha["equalized_odds_difference"] is not None
            and beta["equalized_odds_difference"] is not None
            else None
        ),
    }
    return {"alpha": alpha, "beta": beta, "delta": delta}


# ---------------------------------------------------------------------------
# Bias injector
# ---------------------------------------------------------------------------
def bias_inject(
    portfolio: dict,
    attribute_group: str,
    factor: float = 1.5,
    approve_max_pd: float = 0.05,
    decline_min_pd: float = 0.75,
    costs: dict | None = None,
    mitigation_params: dict | None = None,
    floor: float = 0.80,
    attribute: str | None = None,
) -> dict:
    """Skew one group's scores and show the guardrail firing, then recovery."""
    pd, groups, _exposure, _y, _key = _arrays(portfolio, attribute)
    mask = groups == attribute_group
    if not mask.any():
        raise ValueError(f"unknown group: {attribute_group}")
    skewed = pd.copy()
    skewed[mask] = np.clip(skewed[mask] * float(factor), 0.0, 1.0)

    biased = simulate(
        portfolio,
        approve_max_pd,
        decline_min_pd,
        costs=costs,
        floor=floor,
        pd_override=skewed,
        attribute=attribute,
    )
    recovered = simulate(
        portfolio,
        approve_max_pd,
        decline_min_pd,
        costs=costs,
        floor=floor,
        apply_fairness=bool(mitigation_params),
        mitigation_params=mitigation_params,
        pd_override=skewed,
        attribute=attribute,
    )
    clean = simulate(
        portfolio,
        approve_max_pd,
        decline_min_pd,
        costs=costs,
        floor=floor,
        attribute=attribute,
    )
    return {
        "injection": {
            "group": attribute_group,
            "attribute": clean["group_attribute"],
            "factor": float(factor),
            "note": (
                f"Scores for {attribute_group} were multiplied by {factor}. This "
                "simulates a biased model; it has no effect on the real model."
            ),
        },
        "clean": {
            "disparate_impact_ratio": clean["disparate_impact_ratio"],
            "guardrail": clean["guardrail"],
            "guardrail_passed": clean["guardrail"]["passed"],
        },
        "biased": {
            "disparate_impact_ratio": biased["disparate_impact_ratio"],
            "equalized_odds_difference": biased["equalized_odds_difference"],
            "guardrail": biased["guardrail"],
            "fairness_table": biased["fairness_table"],
        },
        "recovered": {
            "disparate_impact_ratio": recovered["disparate_impact_ratio"],
            "equalized_odds_difference": recovered["equalized_odds_difference"],
            "guardrail": recovered["guardrail"],
            "fairness_table": recovered["fairness_table"],
        },
    }
