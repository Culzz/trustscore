"""Generate the Model Card (Markdown + JSON) from the training run.

The card is written from measured numbers only. If a number was not produced by
the pipeline it is not claimed here.
"""
from __future__ import annotations

import json
from pathlib import Path

DISCLAIMER = (
    "TrustScore is a demonstration of responsible-AI credit decisioning. It is "
    "not a real lending tool, not financial advice, and not a loan offer. "
    "Decisions shown are simulated."
)

LIMITATIONS = [
    "Trained on the public Kaggle Credit Risk Dataset, which is not Nigerian "
    "credit data. It demonstrates the system, not a production score for any "
    "real market.",
    "Fairness is audited only for attributes present in the data (home "
    "ownership, age band, income band, loan purpose, prior default flag). "
    "Gender, race/ethnicity, geography and other attributes are not in the "
    "dataset and are reported as 'not available'.",
    "Fairness figures are statistical disparities between groups. They do not "
    "prove legal compliance or non-compliance.",
    "Counterfactuals are model-generated scenarios, not guaranteed approval "
    "conditions.",
    "Performance monitoring is offline/simulated: the public dataset has no "
    "live outcome stream.",
    "Deployment targets a serverless environment, so the production model is "
    "kept deliberately light (LightGBM only; no SHAP library at runtime).",
    "The measured ROC-AUC is optimistic for a real credit setting: the dataset's "
    "loan grade and interest rate are lender-assigned fields that already encode "
    "an underwriting judgement, so part of the model's skill is reproducing the "
    "lender's own risk tiering rather than independent prediction.",
]


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_model_card(context: dict) -> tuple[str, dict]:
    """Return (markdown, json) for the model card."""
    v = context["version"]
    ds = context["dataset"]
    metrics = context["metrics"]
    thr = context["thresholds"]
    fairness = context["fairness"]
    cal = context["calibration"]

    lines: list[str] = []
    lines.append(f"# Model Card — TrustScore (`{v}`)")
    lines.append("")
    lines.append(f"_Generated {context['trained_at']} by `python -m training.src.train`._")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    lines.append(
        "TrustScore estimates the probability that a loan applicant defaults, "
        "turns that estimate into a simulated approve/refer/decline decision "
        "under an explicit cost matrix, explains the estimate in plain "
        "language, and audits the result for group-level disparities."
    )
    lines.append("")

    lines.append("## Intended use")
    lines.append("")
    lines.append("- **Intended for:** demoing and studying an explainable, "
                 "fairness-aware credit decisioning workflow; teaching; portfolio review.")
    lines.append("- **Not intended for:** real lending, credit scoring of real "
                 "people, regulatory reporting, or any financial decision.")
    lines.append("")

    lines.append("## Data")
    lines.append("")
    lines.append(f"- Source: {ds['source']}")
    lines.append(f"- Rows after cleaning: **{ds['rows']:,}** (from {ds['rows_in']:,} raw)")
    lines.append(f"- Default rate: **{ds['target_rate']:.2%}**")
    lines.append(f"- Splits: train {ds['split_sizes']['train']:,} / "
                 f"validation {ds['split_sizes']['validation']:,} / "
                 f"test {ds['split_sizes']['test']:,} (stratified, seed {ds['seed']})")
    lines.append(f"- Model features ({len(ds['features'])}): {', '.join('`'+f+'`' for f in ds['features'])}")
    lines.append("- Audit-only groupings (never model features): age band, income band")
    lines.append("")
    lines.append("### Cleaning")
    lines.append("")
    cr = ds["clean_report"]
    lines.append(f"- Duplicate rows removed: {cr['duplicate_rows_removed']:,}")
    lines.append(f"- Ages outside 18–{100}: {cr['age_out_of_range']:,} set to missing")
    lines.append(f"- Employment length > 60 years: {cr['emp_length_out_of_range']:,} set to missing")
    lines.append(f"- Non-positive income: {cr['income_non_positive']:,} set to missing")
    lines.append(f"- Loan amounts out of range: {cr['loan_amnt_out_of_range']:,} set to missing")
    if cr.get("missing_after"):
        miss = ", ".join(f"{k} ({n:,})" for k, n in cr["missing_after"].items())
        lines.append(f"- Remaining missing values (imputed in-pipeline): {miss}")
    lines.append("")

    lines.append("## Performance (test split)")
    lines.append("")
    lines.append("| Model | ROC-AUC | PR-AUC | Brier |")
    lines.append("| --- | --- | --- | --- |")
    for name, key in (("Logistic regression (baseline)", "baseline_lr"),
                      ("LightGBM (uncalibrated)", "lightgbm"),
                      ("LightGBM (calibrated)", "calibrated")):
        m = metrics.get(key, {})
        lines.append(
            f"| {name} | {_fmt(m.get('roc_auc'))} | {_fmt(m.get('pr_auc'))} | {_fmt(m.get('brier'))} |"
        )
    lines.append("")
    cal_m = metrics.get("calibrated", {})
    lines.append(f"At a 0.50 rounding threshold the calibrated model gives "
                 f"precision {_fmt(cal_m.get('precision'))}, recall {_fmt(cal_m.get('recall'))}, "
                 f"F1 {_fmt(cal_m.get('f1'))}.")
    lines.append("")

    lines.append("## Calibration")
    lines.append("")
    lines.append(f"- Brier score (calibrated): **{_fmt(cal.get('brier'))}**")
    lines.append(f"- Expected calibration error (10 bins): **{_fmt(cal.get('ece'))}**")
    lines.append("- The reliability curve is stored in `reports/calibration_v1.json`.")
    lines.append("")

    lines.append("## Decision policy and cost")
    lines.append("")
    cm = thr["cost_matrix"]
    lines.append("| Cost | Value (per unit of loan amount) |")
    lines.append("| --- | --- |")
    lines.append(f"| False approve (approve a defaulter) | {cm['false_approve']} |")
    lines.append(f"| False decline (decline a good applicant) | {cm['false_decline']} |")
    lines.append(f"| Manual review | {cm['review']} |")
    lines.append("")
    lines.append(f"- Approve band: PD ≤ **{_fmt(thr['approve_max_pd'])}**")
    lines.append(f"- Refer band: {_fmt(thr['approve_max_pd'])} < PD < {_fmt(thr['decline_min_pd'])}")
    lines.append(f"- Decline band: PD ≥ **{_fmt(thr['decline_min_pd'])}**")
    lines.append(f"- Expected cost per loan at these thresholds (validation): "
                 f"**{_fmt(thr['expected_cost_per_loan'])}** exposure-weighted cost units")
    lines.append("- Thresholds are configurable in the lender view.")
    lines.append("")

    lines.append("## Fairness")
    lines.append("")
    lines.append(f"> {fairness['disclaimer']}")
    lines.append("")
    for attr, block in fairness["attributes"].items():
        lines.append(f"### {block['label']}")
        lines.append("")
        lines.append("| Group | n | Approval rate | TPR | FPR | Precision |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for g in block["groups"]:
            flag = " *(small sample)*" if g.get("low_sample") else ""
            lines.append(
                f"| {g['group']}{flag} | {g['n']:,} | {_fmt(g['selection_rate'])} | "
                f"{_fmt(g['tpr'])} | {_fmt(g['fpr'])} | {_fmt(g['precision'])} |"
            )
        s = block["summary"]
        lines.append("")
        lines.append(f"- Selection-rate ratio (min/max): **{_fmt(s['selection_rate_ratio'])}**")
        lines.append(f"- Demographic parity difference: {_fmt(s['demographic_parity_difference'])}")
        lines.append(f"- Equal opportunity difference (TPR gap): {_fmt(s['equal_opportunity_difference'])}")
        lines.append("")
    lines.append("**Not available in this dataset (reported honestly, not estimated):** "
                 + ", ".join(fairness["unavailable_attributes"]) + ".")
    lines.append("")

    lines.append("## Most influential features")
    lines.append("")
    lines.append("| Feature | Mean absolute contribution |")
    lines.append("| --- | --- |")
    for f in context["top_features"]:
        lines.append(f"| `{f['feature']}` | {_fmt(f['mean_abs_contribution'])} |")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for item in LIMITATIONS:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Ethical considerations")
    lines.append("")
    lines.append("- Protected attributes are never used as model inputs and are never "
                 "suggested as things to change.")
    lines.append("- Reason codes are shown instead of raw numbers so applicants get "
                 "actionable, non-technical explanations.")
    lines.append("- Every prediction carries the model version and a prediction ID for "
                 "auditability.")
    lines.append("")

    lines.append("## Version and reproducibility")
    lines.append("")
    lines.append(f"- Model version: **{v}**")
    lines.append(f"- Fixed random seed: {ds['seed']}")
    lines.append("- Artifacts: `api/artifacts/model.joblib`, `api/artifacts/metadata.json`")
    lines.append("- Reports: `reports/metrics_v1.json`, `reports/fairness_v1.json`, "
                 "`reports/calibration_v1.json`")
    lines.append("")

    markdown = "\n".join(lines)

    json_card = {
        "version": v,
        "generated_at": context["trained_at"],
        "disclaimer": DISCLAIMER,
        "intended_use": "Demo and study of explainable, fairness-aware credit decisioning.",
        "not_intended_for": "Real lending, credit scoring of real people, financial advice.",
        "dataset": ds,
        "metrics": metrics,
        "calibration": cal,
        "thresholds": thr,
        "fairness": fairness,
        "top_features": context["top_features"],
        "limitations": LIMITATIONS,
    }
    return markdown, json_card


def write_model_card(context: dict, md_path: Path, json_path: Path) -> None:
    markdown, json_card = build_model_card(context)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(json_card, indent=2), encoding="utf-8")
