"""One scoring pipeline shared by every endpoint.

Before this module each router re-derived thresholds and bands. Centralising it
means the macro tilt, the fairness mitigation toggle and the group labelling all
behave identically whether a caller hits ``/predict``, ``/decision`` or the
asynchronous ``/apply`` job.
"""
from __future__ import annotations

from ..core import registry
from ..core.features import age_band
from ..core.model import get_predictor
from . import decision as policy
from .feature_store import adjust_thresholds, macro_context
from .mitigation import apply_equalized_odds, apply_to_band, group_labels, row_key


def base_thresholds(pred) -> tuple[float, float]:
    thr = pred.thresholds or {}
    return (
        float(thr.get("approve_max_pd", 0.10)),
        float(thr.get("decline_min_pd", 0.50)),
    )


def score_row(
    row: dict,
    model_version: str | None = None,
    apply_fairness: bool = False,
    region: str = "national",
    use_macro_tilt: bool = False,
    approve_max_pd: float | None = None,
    decline_min_pd: float | None = None,
    mitigation_attribute: str | None = None,
) -> dict:
    """Score one applicant and return everything the callers need.

    Never raises on mitigation: if no mitigation parameters exist, the baseline
    band is returned and ``mitigation_applied`` is False.
    """
    pred = get_predictor(model_version)
    pd_value = pred.predict_proba(row)

    am, dm = base_thresholds(pred)
    if approve_max_pd is not None:
        am = float(approve_max_pd)
    if decline_min_pd is not None:
        dm = float(decline_min_pd)

    context = macro_context(region)
    tilt_info: dict = {"applied": False}
    if use_macro_tilt:
        am, dm, tilt_info = adjust_thresholds(am, dm, context)
    if dm <= am:
        dm = min(0.99, am + 0.01)

    band = policy.decide(pd_value, am, dm)
    group = age_band(row.get("person_age"))

    mitigated_band = band
    mitigation_applied = False
    used_attribute = None
    if apply_fairness:
        params = registry.mitigation_params_for(model_version, mitigation_attribute)
        if params:
            used_attribute = params.get("attribute", "age_band")
            groups = group_labels([row], used_attribute, registry.income_cutpoints())
            approved = bool(
                apply_equalized_odds([pd_value], groups, params, keys=[row_key(row)])[0]
            )
            mitigated_band = apply_to_band(pd_value, band, approved)
            mitigation_applied = mitigated_band != band

    return {
        "model_version": pred.version,
        "probability_of_default": float(pd_value),
        "thresholds": {"approve_max_pd": float(am), "decline_min_pd": float(dm)},
        "band": band,
        "band_label": policy.band_label(band),
        "final_band": mitigated_band,
        "final_band_label": policy.band_label(mitigated_band),
        "mitigation": {
            "requested": bool(apply_fairness),
            "applied": mitigation_applied,
            "changed_band": mitigation_applied,
            "attribute": used_attribute,
            "method": "equalized_odds" if (apply_fairness and used_attribute) else "none",
        },
        "group": group,
        "context": context,
        "macro_tilt": tilt_info,
    }
