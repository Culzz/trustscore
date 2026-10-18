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
    "All headline metrics come from a single random stratified split of one public "
    "dataset. A random split measures performance on a similar distribution; it "
    "does not establish performance on future applicants or on a different "
    "population. The out-of-population check in this card exists precisely because "
    "the random split hides the difference.",
    "The auditor console runs only on the validation (policy tuning) split. Its "
    "live figures are therefore not the published test figures, and it must not be "
    "used to select a policy on the basis of test-set performance.",
    "Fairness mitigation is an experimental policy intervention, not a fairness "
    "guarantee and not a legal-compliance finding. It targets one attribute at a "
    "time; other audited attributes can and do remain below the four-fifths floor "
    "with it enabled.",
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

    proto = context.get("evaluation_protocol")
    if proto:
        lines.append("## Evaluation protocol")
        lines.append("")
        lines.append(
            "Three disjoint sets are used. Every number in this card states which "
            "set it comes from:"
        )
        lines.append("")
        for name, role in (proto.get("role_split") or {}).items():
            lines.append(f"- **{name}** — {role}")
        lines.append("")
        pt = proto.get("policy_tuning_set") or {}
        fe = proto.get("final_evaluation_set") or {}
        if pt and fe:
            lines.append(
                f"- The auditor console runs **only** on the policy tuning set "
                f"(`{pt.get('name')}`, n={pt.get('rows', 0):,}). Row-level data for "
                f"the final evaluation set (`{fe.get('name')}`, n={fe.get('rows', 0):,}) "
                "is deliberately not shipped, so it stays held out. Tuning-set "
                "figures are therefore *not* the published test figures."
            )
        lines.append(
            f"- Equalized-odds mitigation is fitted on {proto.get('mitigation_fit_on')} "
            f"and measured on {', '.join(proto.get('mitigation_measured_on') or [])}."
        )
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
    ci = cal_m.get("intervals") or {}
    if ci.get("roc_auc"):
        def _ci(key: str) -> str:
            block = ci.get(key) or {}
            if block.get("ci_low") is None:
                return "n/a"
            return f"[{_fmt(block['ci_low'])}, {_fmt(block['ci_high'])}]"
        lines.append("")
        lines.append(
            f"95% bootstrap confidence intervals (test split, "
            f"{ci.get('n_boot')} resamples of the applicants): ROC-AUC {_ci('roc_auc')}, "
            f"PR-AUC {_ci('pr_auc')}, Brier {_ci('brier')}. These capture sampling "
            "noise only — not dataset shift, label noise or model-selection "
            "uncertainty."
        )
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
    lines.append(
        "The band thresholds are derived **analytically** from the cost matrix: for "
        "each applicant the policy picks the cheapest of approve / refer / decline, "
        "which yields two crossover points."
    )
    lines.append("")
    lines.append(
        f"- Approve → refer at PD = review ÷ false_approve = "
        f"**{_fmt(thr.get('analytic_approve_max_pd'), 5)}**"
    )
    lines.append(
        f"- Refer → decline at PD = 1 − review ÷ false_decline = "
        f"**{_fmt(thr.get('analytic_decline_min_pd'), 5)}**"
    )
    lines.append("")
    lines.append(f"- Deployed approve band: PD ≤ **{_fmt(thr['approve_max_pd'], 5)}**")
    lines.append(f"- Deployed refer band: {_fmt(thr['approve_max_pd'], 5)} < PD < "
                 f"{_fmt(thr['decline_min_pd'], 5)}")
    lines.append(f"- Deployed decline band: PD ≥ **{_fmt(thr['decline_min_pd'], 5)}**")
    grid = thr.get("grid_verification") or {}
    if grid:
        lines.append(
            f"- **Verification.** An independent brute-force grid search over the "
            f"validation split found approve ≤ {_fmt(grid.get('approve_max_pd'), 5)} / "
            f"decline ≥ {_fmt(grid.get('decline_min_pd'), 5)} at a cost "
            f"{_fmt(grid.get('cost_delta_vs_analytic'), 8)} above the analytic policy — "
            "i.e. cost-identical. The expected-cost surface is flat across a gap in "
            "the score distribution, so the grid point is an arbitrary member of a "
            "plateau while the analytic crossover is the exact per-applicant "
            f"optimum. Analytic-is-cost-optimal: **{grid.get('analytic_is_cost_optimal')}**."
        )
    lines.append(f"- Expected cost per loan at these thresholds (validation): "
                 f"**{_fmt(thr['expected_cost_per_loan'])}** exposure-weighted cost units")
    lines.append(f"- Test approval rate: **{_fmt(thr.get('test_approval_rate'), 4)}** "
                 f"(bands: {thr.get('test_band_counts')})")
    lines.append("- Thresholds are configurable in the auditor view.")
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
        lines.append(
            f"- Equalized odds difference (max TPR/FPR gap): "
            f"{_fmt(s.get('equalized_odds_difference'))}"
        )
        di = s.get("disparate_impact_ratio")
        if di is not None:
            status = "PASS" if s.get("disparate_impact_pass") else "BREACH"
            lines.append(
                f"- Disparate-impact ratio (four-fifths rule): **{_fmt(di)}** "
                f"[{status} vs floor {_fmt(fairness.get('disparate_impact_floor'))}]"
            )
        di_ci = s.get("disparate_impact_ratio_ci")
        if di_ci:
            lines.append(
                f"- Disparate-impact 95% bootstrap CI: [{_fmt(di_ci[0])}, {_fmt(di_ci[1])}]"
            )
        eo_ci = s.get("equalized_odds_difference_ci")
        if eo_ci:
            lines.append(
                f"- Equalized-odds 95% bootstrap CI: [{_fmt(eo_ci[0])}, {_fmt(eo_ci[1])}]"
            )
        lines.append(
            f"- Groups used in the ratios: {s.get('n_groups_considered')} of "
            f"{s.get('n_groups_total')} (smaller groups are shown but excluded)."
        )
        lines.append("")
    lines.append("**Not available in this dataset (reported honestly, not estimated):** "
                 + ", ".join(fairness["unavailable_attributes"]) + ".")
    lines.append("")

    guardrail = fairness.get("guardrail")
    if guardrail:
        lines.append("### Guardrail")
        lines.append("")
        lines.append(
            f"- Disparate-impact floor: **{_fmt(guardrail['disparate_impact_floor'])}**"
        )
        lines.append(f"- Status: **{'PASS' if guardrail['passed'] else 'BREACH'}** "
                     f"({guardrail['n_breaches']} attribute(s) below the floor)")
        breaches = guardrail.get("breaches") or []
        if breaches:
            lines.append("")
            lines.append("| Breaching attribute | Lowest group (n) | Selection rate | DI ratio | DI 95% CI |")
            lines.append("| --- | --- | --- | --- | --- |")
            for b in breaches:
                ci_b = b.get("disparate_impact_ratio_ci")
                ci_txt = f"[{_fmt(ci_b[0])}, {_fmt(ci_b[1])}]" if ci_b else "n/a"
                lines.append(
                    f"| {b['label']} | {b['lowest_group']} ({b.get('lowest_group_n', 0):,}) | "
                    f"{_fmt(b.get('lowest_selection_rate'))} | {_fmt(b.get('disparate_impact_ratio'))} | "
                    f"{ci_txt} |"
                )
        if guardrail.get("interpretation"):
            lines.append("")
            lines.append(f"> {guardrail['interpretation']}")
        lines.append("")

    mitigation = context.get("mitigation")
    if mitigation:
        lines.append("## Fairness mitigation (equalized odds)")
        lines.append("")
        lines.append(
            "The fairness-tuned model (**Beta**, "
            f"`{context.get('fair_version', 'trustscore-1.1.0')}`) keeps the same "
            "booster and appends a *post-processing* decision rule: per-group "
            "randomised probability thresholds chosen so that the true-positive and "
            "false-positive rates line up across the groups of one attribute."
        )
        lines.append("")
        lines.append(f"- Method: **{mitigation['method']}**")
        lines.append(f"- Attribute: `{mitigation['attribute']}`")
        lines.append(f"- Target TPR / FPR: {_fmt(mitigation['target_tpr'])} / "
                     f"{_fmt(mitigation['target_fpr'])}")
        lines.append(f"- Base approve threshold: {_fmt(mitigation['base_threshold'])}")
        lines.append(f"- Fitted on: {mitigation.get('fit_on')} "
                     f"(min group size {mitigation.get('min_group_size')})")
        lines.append(f"- Measured on: test (headline, below) and validation (console)")
        impact = context.get("mitigation_impact") or {}
        if impact:
            lines.append("")
            lines.append("**Final evaluation (held-out test split)**")
            lines.append("")
            lines.append("| Metric | Baseline | After mitigation |")
            lines.append("| --- | --- | --- |")
            lines.append(
                f"| Approval rate | {_fmt(impact.get('approval_rate_base'), 3)} | "
                f"{_fmt(impact.get('approval_rate_mitigated'), 3)} |"
            )
            lines.append(
                f"| Realized cost per loan | {_fmt(impact.get('realized_cost_per_loan_base'))} | "
                f"{_fmt(impact.get('realized_cost_per_loan_mitigated'))} |"
            )
            lines.append(
                f"| Disparate-impact ratio | {_fmt(impact.get('disparate_impact_ratio_base'))} | "
                f"{_fmt(impact.get('disparate_impact_ratio_mitigated'))} |"
            )
            lines.append(
                f"| Equalized odds difference | "
                f"{_fmt(impact.get('equalized_odds_difference_base'))} | "
                f"{_fmt(impact.get('equalized_odds_difference_mitigated'))} |"
            )
            lines.append(
                f"| Attributes breaching the floor | "
                f"{impact.get('n_breaches_base')} | {impact.get('n_breaches_mitigated')} |"
            )
            cost_of = None
            if (
                impact.get("realized_cost_per_loan_mitigated") is not None
                and impact.get("realized_cost_per_loan_base") is not None
            ):
                cost_of = (
                    impact["realized_cost_per_loan_mitigated"]
                    - impact["realized_cost_per_loan_base"]
                )
            if cost_of is not None:
                lines.append("")
                lines.append(
                    f"The measured cost of this intervention is "
                    f"**{_fmt(cost_of, 6)}** additional realized cost per unit of "
                    "exposure on the held-out test split."
                )
        tuning = context.get("mitigation_impact_tuning") or {}
        if tuning:
            lines.append("")
            lines.append(
                f"**Policy tuning set (validation, what the auditor console shows):** "
                f"DI {_fmt(tuning.get('disparate_impact_ratio_base'))} → "
                f"{_fmt(tuning.get('disparate_impact_ratio_mitigated'))}; "
                f"EO gap {_fmt(tuning.get('equalized_odds_difference_base'))} → "
                f"{_fmt(tuning.get('equalized_odds_difference_mitigated'))}; "
                f"breaches {tuning.get('n_breaches_base')} → "
                f"{tuning.get('n_breaches_mitigated')}."
            )
        remaining = (context.get("fairness_mitigated") or {}).get("guardrail") or {}
        if remaining.get("breaches"):
            names = ", ".join(b["label"] for b in remaining["breaches"])
            lines.append("")
            lines.append(
                f"> **Caveat.** Mitigation is an experimental policy intervention, "
                f"not a fairness guarantee and not a compliance finding. Even with it "
                f"enabled, {remaining.get('n_breaches')} attribute(s) remain below the "
                f"floor ({names}). Clearing one attribute says nothing about the "
                "others, and every figure above is sensitive to the dataset, the "
                "group definitions, group sizes, the cost matrix and the metric chosen."
            )
        lines.append("")

    ablation = context.get("ablation")
    if ablation:
        lines.append("## Feature provenance and ablation")
        lines.append("")
        lines.append(
            "The dataset's `loan_grade` and `loan_int_rate` are **lender-assigned** "
            "fields: they already encode an underwriting judgement made at "
            "origination. A model that uses them may be partly reproducing the "
            "lender's own risk tiering rather than predicting independently. To "
            "quantify that, a second model was trained on the same split with those "
            "fields removed."
        )
        lines.append("")
        lines.append("| Model | ROC-AUC | PR-AUC | Brier |")
        lines.append("| --- | --- | --- | --- |")
        full = ablation.get("full") or {}
        abl = ablation.get("without_lender_assigned") or {}
        lines.append(
            f"| Full feature set | {_fmt(full.get('roc_auc'))} | {_fmt(full.get('pr_auc'))} | "
            f"{_fmt(full.get('brier'))} |"
        )
        lines.append(
            f"| Without `loan_grade`, `loan_int_rate` | {_fmt(abl.get('roc_auc'))} | "
            f"{_fmt(abl.get('pr_auc'))} | {_fmt(abl.get('brier'))} |"
        )
        lines.append("")
        if ablation.get("delta_roc_auc") is not None:
            lines.append(
                f"Removing the lender-assigned fields costs **{_fmt(ablation['delta_roc_auc'])} "
                "ROC-AUC** — that gap is the part of the headline performance that "
                "came from reproducing the lender's own decision, and it is the "
                "honest expectation for a system that must score applicants the "
                "lender has not already judged."
            )
            lines.append("")
        if ablation.get("provenance_note"):
            lines.append(f"> {ablation['provenance_note']}")
            lines.append("")

    robustness = context.get("robustness") or {}
    seg = robustness.get("income_segment_holdout")
    if seg:
        lines.append("## Robustness: out-of-population check")
        lines.append("")
        lines.append(seg.get("note", ""))
        lines.append("")
        lines.append("| Evaluation | ROC-AUC | PR-AUC |")
        lines.append("| --- | --- | --- |")
        lines.append(
            f"| In-population (held-out slice of the modelled segment, "
            f"n={seg.get('n_in_population', 0):,}) | "
            f"{_fmt((seg.get('in_population') or {}).get('roc_auc'))} | "
            f"{_fmt((seg.get('in_population') or {}).get('pr_auc'))} |"
        )
        lines.append(
            f"| Out-of-population ({seg.get('segment')}, "
            f"n={seg.get('n_out_of_population', 0):,}) | "
            f"{_fmt((seg.get('out_of_population') or {}).get('roc_auc'))} | "
            f"{_fmt((seg.get('out_of_population') or {}).get('pr_auc'))} |"
        )
        lines.append("")
        if seg.get("delta_roc_auc") is not None:
            lines.append(
                f"Ranking skill drops by **{_fmt(seg['delta_roc_auc'])} ROC-AUC** on the "
                "held-out population. The headline test metrics come from a random "
                "stratified split, which shares the training distribution; they are "
                "not a forecast of performance on future or different applicants."
            )
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
    lines.append("- Artifacts: `api/artifacts/model.joblib`, `api/artifacts/metadata.json`, "
                 "`api/artifacts/model_fair.joblib`, `api/artifacts/registry.json`")
    lines.append("- Reports: `reports/metrics_v1.json`, `reports/fairness_v1.json`, "
                 "`reports/fairness_v110.json`, `reports/calibration_v1.json`")
    lines.append("")

    markdown = "\n".join(lines)

    json_card = {
        "version": v,
        "generated_at": context["trained_at"],
        "disclaimer": DISCLAIMER,
        "intended_use": "Demo and study of explainable, fairness-aware credit decisioning.",
        "not_intended_for": "Real lending, credit scoring of real people, financial advice.",
        "dataset": ds,
        "evaluation_protocol": context.get("evaluation_protocol"),
        "metrics": metrics,
        "calibration": cal,
        "thresholds": thr,
        "fairness": fairness,
        "fairness_guardrail": fairness.get("guardrail"),
        "fairness_mitigated": context.get("fairness_mitigated"),
        "mitigation": context.get("mitigation"),
        "mitigation_impact": context.get("mitigation_impact"),
        "mitigation_impact_tuning": context.get("mitigation_impact_tuning"),
        "ablation": context.get("ablation"),
        "robustness": context.get("robustness"),
        "top_features": context["top_features"],
        "limitations": LIMITATIONS,
    }
    return markdown, json_card


def write_model_card(context: dict, md_path: Path, json_path: Path) -> None:
    markdown, json_card = build_model_card(context)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(json_card, indent=2), encoding="utf-8")
