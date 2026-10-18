"""Generate the standalone Model Evaluation Report (``reports/EVALUATION.md``).

Where the model card is the short, standard summary, this report is the long form:
dataset provenance, the split strategy and why it is shaped that way, baselines,
calibration, the decision-cost assumptions, fairness and recourse limitations, the
feature-provenance ablation, the out-of-population check, and the deployment
constraints. Everything is written from measured values; nothing is asserted that the
pipeline did not produce.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .modelcard import DISCLAIMER, LIMITATIONS, _fmt


def _ci(block: dict | None) -> str:
    if not block or block.get("ci_low") is None:
        return "n/a"
    return f"[{_fmt(block['ci_low'])}, {_fmt(block['ci_high'])}]"


def build_evaluation_report(context: dict) -> str:
    v = context["version"]
    ds = context.get("dataset") or {}
    metrics = context.get("metrics") or {}
    thr = context.get("thresholds") or {}
    fairness = context.get("fairness") or {}
    cal = context.get("calibration") or {}
    proto = context.get("evaluation_protocol") or {}
    ablation = context.get("ablation") or {}
    robustness = (context.get("robustness") or {}).get("income_segment_holdout") or {}
    mitigation = context.get("mitigation") or {}
    impact = context.get("mitigation_impact") or {}
    impact_tuning = context.get("mitigation_impact_tuning") or {}
    mitigated_fairness = context.get("fairness_mitigated") or {}

    cal_m = metrics.get("calibrated") or {}
    lgbm_m = metrics.get("lightgbm") or {}
    lr_m = metrics.get("baseline_lr") or {}
    intervals = cal_m.get("intervals") or {}

    L: list[str] = []
    L.append(f"# TrustScore — Model Evaluation Report (`{v}`)")
    L.append("")
    L.append(f"_Generated {context.get('trained_at')} by `python -m training.src.train`._")
    L.append("")
    L.append(f"> {DISCLAIMER}")
    L.append("")

    # ------------------------------------------------------------------ summary
    L.append("## 1. Summary")
    L.append("")
    L.append(
        f"TrustScore is a credit-default model plus an explicit decision policy. The "
        f"calibrated model reaches **ROC-AUC {_fmt(cal_m.get('roc_auc'))} "
        f"{_ci(intervals.get('roc_auc'))}**, **PR-AUC {_fmt(cal_m.get('pr_auc'))} "
        f"{_ci(intervals.get('pr_auc'))}** and **Brier {_fmt(cal_m.get('brier'))} "
        f"{_ci(intervals.get('brier'))}** on the held-out test split "
        f"(n={proto.get('final_evaluation_set', {}).get('rows', 0):,}). The decision "
        f"policy is the analytic cost crossover of the configured cost matrix, "
        f"verified by an independent grid search."
    )
    L.append("")
    L.append(
        "The honest caveats are part of the summary, not a footnote: the dataset is "
        "public and not from the target market; two of the strongest features are "
        "lender-assigned; the fairness audit covers only the attributes the data "
        "contains; and fairness mitigation does not clear every attribute."
    )
    L.append("")

    # ------------------------------------------------------- dataset provenance
    L.append("## 2. Dataset provenance")
    L.append("")
    L.append(f"- Source: **{ds.get('name', 'n/a')}**")
    if ds.get("source"):
        L.append(f"- Reference: {ds['source']}")
    L.append(f"- Rows: raw {ds.get('rows_raw', 0):,}, cleaned {ds.get('rows_clean', 0):,}")
    L.append(f"- Positive (default) rate: **{_fmt(ds.get('positive_rate'))}**")
    L.append(f"- Split sizes: {ds.get('split_sizes')}")
    if ds.get("seed") is not None:
        L.append(f"- Seed: `{ds.get('seed')}`")
    L.append("")
    cr = ds.get("clean_report") or {}
    if cr:
        L.append("Cleaning decisions (from the pipeline's own report):")
        L.append("")
        L.append("```json")
        L.append(json.dumps(cr, indent=2)[:4000])
        L.append("```")
        L.append("")
    L.append(
        "**Provenance note.** `loan_grade` is assigned by the lender at origination "
        "and `loan_int_rate` follows from it. Both are underwriting *outputs* rather "
        "than independent applicant signals, so a model that uses them may be "
        "reproducing the lender's own risk tiering. Section 7 quantifies this."
    )
    L.append("")

    # ---------------------------------------------------------- split strategy
    L.append("## 3. Split strategy")
    L.append("")
    L.append(
        f"Protocol: **{proto.get('protocol_version', 'n/a')}**. The full contract is "
        "in `docs/EVALUATION.md`."
    )
    L.append("")
    for name, role in (proto.get("role_split") or {}).items():
        L.append(f"- **{name}** — {role}")
    L.append("")
    pt = proto.get("policy_tuning_set") or {}
    fe = proto.get("final_evaluation_set") or {}
    if pt and fe:
        L.append(
            f"The auditor console reads the policy tuning set "
            f"(`{pt.get('name')}`, n={pt.get('rows', 0):,}). Row-level data for the "
            f"final evaluation set (`{fe.get('name')}`, n={fe.get('rows', 0):,}) is "
            "not shipped, so the final set cannot be inspected interactively by "
            f"accident. Mitigation is fitted on **{proto.get('mitigation_fit_on')}**."
        )
        L.append("")
    L.append(
        "Consequence: **tuning-set figures are not the published test figures.** "
        "They are expected to differ, and are labelled as tuning-set figures wherever "
        "they appear."
    )
    L.append("")

    # ----------------------------------------------------------------- baselines
    L.append("## 4. Baselines")
    L.append("")
    L.append("| Model | ROC-AUC | PR-AUC | Brier |")
    L.append("| --- | --- | --- | --- |")
    L.append(
        f"| Logistic regression (baseline) | {_fmt(lr_m.get('roc_auc'))} | "
        f"{_fmt(lr_m.get('pr_auc'))} | {_fmt(lr_m.get('brier'))} |"
    )
    L.append(
        f"| LightGBM (uncalibrated) | {_fmt(lgbm_m.get('roc_auc'))} | "
        f"{_fmt(lgbm_m.get('pr_auc'))} | {_fmt(lgbm_m.get('brier'))} |"
    )
    L.append(
        f"| LightGBM + isotonic (deployed) | **{_fmt(cal_m.get('roc_auc'))}** | "
        f"**{_fmt(cal_m.get('pr_auc'))}** | **{_fmt(cal_m.get('brier'))}** |"
    )
    L.append("")
    L.append(
        "All three are measured on the same held-out test split. Calibration does not "
        "change ranking (ROC-AUC/PR-AUC move only through ties), but it is what makes "
        "the probability interpretable as a probability and therefore what makes the "
        "cost-based policy meaningful."
    )
    L.append("")

    # --------------------------------------------------------------- calibration
    L.append("## 5. Calibration")
    L.append("")
    L.append(
        f"- Brier score: **{_fmt(cal.get('brier'))}** — mean squared error of the "
        "predicted probabilities (lower is better)."
    )
    L.append(
        f"- Expected calibration error: **{_fmt(cal.get('ece'))}** — average |predicted − "
        "observed| across probability bins."
    )
    L.append(
        "- The isotonic map is fitted on 5-fold **out-of-fold** predictions within the "
        "training split, so it is not fitted on in-sample scores."
    )
    L.append("")
    bins = (context.get("calibration_bins") or [])
    if bins:
        L.append("| Bin | n | Mean predicted | Observed | Observed 95% CI |")
        L.append("| --- | --- | --- | --- | --- |")
        for b in bins:
            L.append(
                f"| {_fmt(b.get('bin_lower'), 2)}–{_fmt(b.get('bin_upper'), 2)} | "
                f"{b.get('count', 0):,} | {_fmt(b.get('mean_predicted'))} | "
                f"{_fmt(b.get('observed_rate'))} | {b.get('observed_ci')} |"
            )
        L.append("")

    # ------------------------------------------------------- decision-cost setup
    L.append("## 6. Decision-cost assumptions and the policy")
    L.append("")
    costs = thr.get("cost_matrix") or {}
    L.append("| Cost | Value (per unit of loan exposure) |")
    L.append("| --- | --- |")
    for key in ("false_approve", "false_decline", "review"):
        L.append(f"| {key.replace('_', ' ')} | {_fmt(costs.get(key))} |")
    L.append("")
    L.append(
        "These are **assumptions, not measurements.** They encode a preference: a "
        "false approve is treated as five times as costly as a false decline, and a "
        "manual review costs 0.05. Every threshold in the product follows from them; "
        "change them and the policy changes."
    )
    L.append("")
    L.append(
        f"- Analytic policy: approve ≤ **{_fmt(thr.get('analytic_approve_max_pd'), 5)}**, "
        f"decline ≥ **{_fmt(thr.get('analytic_decline_min_pd'), 5)}**."
    )
    grid = thr.get("grid_verification") or {}
    if grid:
        L.append(
            f"- Grid verification (validation split): approve "
            f"{_fmt(grid.get('approve_max_pd'), 5)} / decline "
            f"{_fmt(grid.get('decline_min_pd'), 5)}, cost delta "
            f"**{_fmt(grid.get('cost_delta_vs_analytic'), 8)}** — i.e. the same cost. "
            "The surface is flat across a gap in the score distribution, so the grid "
            "point is an arbitrary plateau member; the analytic crossover is the "
            "exact per-applicant optimum and generalises to unseen applicants."
        )
    L.append(
        f"- Expected cost per loan (validation): {_fmt(thr.get('expected_cost_per_loan'))}; "
        f"realized cost per loan (test): {_fmt(thr.get('test_realized_cost_per_loan'))}."
    )
    L.append(
        f"- Test approval rate: **{_fmt(thr.get('test_approval_rate'))}** "
        f"(bands {thr.get('test_band_counts')})."
    )
    L.append("")

    # ------------------------------------------------------------------ fairness
    L.append("## 7. Fairness evaluation")
    L.append("")
    L.append(f"- Disparate-impact floor (four-fifths rule): **{_fmt(fairness.get('disparate_impact_floor'))}**")
    L.append(
        f"- Audited attributes: {', '.join((fairness.get('attributes') or {}).keys()) or 'none'}"
    )
    L.append(
        f"- **Not available in the data:** {', '.join(fairness.get('unavailable_attributes') or []) or 'n/a'}"
    )
    L.append("")
    attrs = fairness.get("attributes") or {}
    L.append("| Attribute | DI ratio | DI 95% CI | EO gap | EO 95% CI | Groups used |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for key, block in attrs.items():
        s = block.get("summary") or {}
        di_ci = s.get("disparate_impact_ratio_ci")
        eo_ci = s.get("equalized_odds_difference_ci")
        L.append(
            f"| {block.get('label', key)} | {_fmt(s.get('disparate_impact_ratio'))} | "
            f"{_ci({'ci_low': di_ci[0], 'ci_high': di_ci[1]}) if di_ci else 'n/a'} | "
            f"{_fmt(s.get('equalized_odds_difference'))} | "
            f"{_ci({'ci_low': eo_ci[0], 'ci_high': eo_ci[1]}) if eo_ci else 'n/a'} | "
            f"{s.get('n_groups_considered')} / {s.get('n_groups_total')} |"
        )
    L.append("")
    guardrail = fairness.get("guardrail") or {}
    L.append(
        f"Guardrail status on the test split: **{'PASS' if guardrail.get('passed') else 'BREACH'}** "
        f"({guardrail.get('n_breaches', 0)} attribute(s) below the floor)."
    )
    if guardrail.get("breaches"):
        L.append("")
        L.append("| Breaching attribute | Lowest group (n) | Selection rate | DI ratio | DI 95% CI |")
        L.append("| --- | --- | --- | --- | --- |")
        for b in guardrail["breaches"]:
            ci_b = b.get("disparate_impact_ratio_ci")
            L.append(
                f"| {b.get('label')} | {b.get('lowest_group')} "
                f"(n={b.get('lowest_group_n')}) | {_fmt(b.get('lowest_selection_rate'))} | "
                f"{_fmt(b.get('disparate_impact_ratio'))} | "
                f"{_ci({'ci_low': ci_b[0], 'ci_high': ci_b[1]}) if ci_b else 'n/a'} |"
            )
    if guardrail.get("interpretation"):
        L.append("")
        L.append(f"> {guardrail['interpretation']}")
    L.append("")

    # ---------------------------------------------------------- mitigation cost
    L.append("## 8. Fairness mitigation: what it buys and what it costs")
    L.append("")
    L.append(
        "Mitigation is an **experimental policy intervention** (equalized-odds "
        "post-processing), not a fairness guarantee and not a legal-compliance "
        "finding. It targets one attribute at a time."
    )
    L.append("")
    if mitigation:
        L.append(
            f"- Method: **{mitigation.get('method')}** on `{mitigation.get('attribute')}`; "
            f"fitted on {mitigation.get('fit_on')}."
        )
    if impact:
        L.append("")
        L.append("**Final evaluation — held-out test split:**")
        L.append("")
        L.append("| Metric | Baseline | After mitigation |")
        L.append("| --- | --- | --- |")
        L.append(
            f"| Approval rate | {_fmt(impact.get('approval_rate_base'))} | "
            f"{_fmt(impact.get('approval_rate_mitigated'))} |"
        )
        L.append(
            f"| Realized cost per loan | {_fmt(impact.get('realized_cost_per_loan_base'))} | "
            f"{_fmt(impact.get('realized_cost_per_loan_mitigated'))} |"
        )
        L.append(
            f"| Disparate-impact ratio | {_fmt(impact.get('disparate_impact_ratio_base'))} | "
            f"{_fmt(impact.get('disparate_impact_ratio_mitigated'))} |"
        )
        L.append(
            f"| Equalized-odds gap | {_fmt(impact.get('equalized_odds_difference_base'))} | "
            f"{_fmt(impact.get('equalized_odds_difference_mitigated'))} |"
        )
        L.append(
            f"| Attributes breaching the floor | {impact.get('n_breaches_base')} | "
            f"**{impact.get('n_breaches_mitigated')}** |"
        )
        L.append("")
        if (
            impact.get("realized_cost_per_loan_mitigated") is not None
            and impact.get("realized_cost_per_loan_base") is not None
        ):
            delta = (
                impact["realized_cost_per_loan_mitigated"]
                - impact["realized_cost_per_loan_base"]
            )
            L.append(
                f"**Measured cost of the intervention: {_fmt(delta, 6)} additional "
                "realized cost per unit of exposure** on the held-out test split "
                "(the trade-off is real, and it should be stated next to the "
                "improvement)."
            )
            L.append("")
    if impact_tuning:
        L.append(
            f"**Policy tuning set (validation, what the console shows):** DI "
            f"{_fmt(impact_tuning.get('disparate_impact_ratio_base'))} → "
            f"{_fmt(impact_tuning.get('disparate_impact_ratio_mitigated'))}; "
            f"EO gap {_fmt(impact_tuning.get('equalized_odds_difference_base'))} → "
            f"{_fmt(impact_tuning.get('equalized_odds_difference_mitigated'))}; "
            f"breaches {impact_tuning.get('n_breaches_base')} → "
            f"{impact_tuning.get('n_breaches_mitigated')}."
        )
        L.append("")
    if mitigated_fairness:
        remaining = (mitigated_fairness.get("guardrail") or {}).get("breaches") or []
        L.append(
            f"**This mitigation is fitted for `{mitigation.get('attribute')}` only.** "
            f"On the test split it clears that attribute, but {len(remaining)} "
            "attribute(s) remain below the four-fifths floor overall"
            + (f" ({', '.join(b['label'] for b in remaining)})" if remaining else "")
            + ". Clearing one attribute says nothing about the others, and every "
            "figure here is sensitive to the dataset, the group definitions, group "
            "sizes, the cost matrix and the metric chosen."
        )
        L.append("")

    # -------------------------------------------------------------- exploitation
    L.append("## 9. Feature provenance (ablation)")
    L.append("")
    if ablation:
        L.append(ablation.get("reason", ""))
        L.append("")
        full = ablation.get("full") or {}
        abl = ablation.get("without_lender_assigned") or {}
        L.append("| Model (same split, uncalibrated) | ROC-AUC | PR-AUC | Brier |")
        L.append("| --- | --- | --- | --- |")
        L.append(
            f"| Full feature set | {_fmt(full.get('roc_auc'))} | {_fmt(full.get('pr_auc'))} | "
            f"{_fmt(full.get('brier'))} |"
        )
        L.append(
            f"| Without `loan_grade`, `loan_int_rate` | {_fmt(abl.get('roc_auc'))} | "
            f"{_fmt(abl.get('pr_auc'))} | {_fmt(abl.get('brier'))} |"
        )
        L.append("")
        if ablation.get("delta_roc_auc") is not None:
            L.append(
                f"Removing the lender-assigned fields costs "
                f"**{_fmt(ablation['delta_roc_auc'])} ROC-AUC**. That gap is the part "
                "of the headline performance that came from reproducing the lender's "
                "own decision, and it is the honest expectation for a system that must "
                "score applicants the lender has not already judged."
            )
            L.append("")
        if ablation.get("provenance_note"):
            L.append(f"> {ablation['provenance_note']}")
            L.append("")

    # ---------------------------------------------------------------- robustness
    L.append("## 10. Out-of-population robustness")
    L.append("")
    if robustness:
        L.append(robustness.get("note", ""))
        L.append("")
        L.append("| Evaluation | ROC-AUC | PR-AUC |")
        L.append("| --- | --- | --- |")
        L.append(
            f"| In-population (n={robustness.get('n_in_population', 0):,}) | "
            f"{_fmt((robustness.get('in_population') or {}).get('roc_auc'))} | "
            f"{_fmt((robustness.get('in_population') or {}).get('pr_auc'))} |"
        )
        L.append(
            f"| Out-of-population — {robustness.get('segment')} "
            f"(n={robustness.get('n_out_of_population', 0):,}) | "
            f"{_fmt((robustness.get('out_of_population') or {}).get('roc_auc'))} | "
            f"{_fmt((robustness.get('out_of_population') or {}).get('pr_auc'))} |"
        )
        L.append("")
        if robustness.get("delta_roc_auc") is not None:
            L.append(
                f"Ranking skill drops by **{_fmt(robustness['delta_roc_auc'])} ROC-AUC** "
                "on the held-out population. The headline test metrics come from a "
                "random stratified split, which shares the training distribution; they "
                "are not a forecast of performance on future or different applicants."
            )
            L.append("")

    # ------------------------------------------------------ recourse limitations
    L.append("## 11. Recourse and explanation limitations")
    L.append("")
    L.append(
        "- Recommendations are limited to fields an applicant actually controls "
        "(requested amount, loan purpose). Income is surfaced only as an "
        "explicitly-labelled informational option."
    )
    L.append(
        "- Immutable factors (age, tenure, employment length, prior default, credit "
        "history length, lender-assigned grade/rate) are never suggested, and the API "
        "lists them explicitly so it is visible what was *not* used."
    )
    L.append(
        "- Recommendations are constrained to plausible ranges; there is no "
        "unbounded optimiser that will propose a 40x income increase."
    )
    L.append(
        "- When no change in the applicant-controlled fields reaches a better band, "
        "the API says so explicitly instead of inventing a marginal suggestion."
    )
    L.append(
        "- Every scenario carries an explicit non-guarantee disclaimer. A route is a "
        "model-generated estimate, not a promise and not a condition any lender has "
        "agreed to."
    )
    L.append("")

    # ---------------------------------------------------- deployment constraints
    L.append("## 12. Deployment constraints")
    L.append("")
    L.append(
        "- The production artifact is served with **native LightGBM only**: no "
        "scikit-learn, SciPy, SHAP or matplotlib at runtime, so it fits a serverless "
        "bundle. Explainability is computed from LightGBM's own prediction "
        "contributions."
    )
    L.append(
        "- The default deployment is a lightweight API plus a web front end on the "
        "free tier. Async jobs are mirrored to durable storage when a database is "
        "configured; without one, job state is in-process and a recycled instance "
        "loses it (documented, not hidden)."
    )
    L.append(
        "- Governance logging is **best-effort and anonymised**: a failure to write "
        "never blocks an applicant, and only derived/non-identifier fields are stored."
    )
    L.append(
        "- Tracking of live outcomes, live drift against a live label stream, and "
        "real population monitoring are **not** implemented, because the public "
        "dataset has no live outcome stream. Drift is monitored on input "
        "distributions only."
    )
    L.append("")

    # ------------------------------------------------------------------ limitations
    L.append("## 13. Limitations")
    L.append("")
    for item in LIMITATIONS:
        L.append(f"- {item}")
    L.append("")
    L.append("## 14. Reproduction")
    L.append("")
    L.append("```")
    L.append("python -m training.src.train")
    L.append("```")
    L.append("")
    L.append(
        f"Seeded with `SEED = {ds.get('seed')}`. Produces `api/artifacts/*`, "
        "`reports/*.json`, `reports/MODEL_CARD.md` and this report."
    )
    L.append("")
    return "\n".join(L)


def write_evaluation_report(context: dict, path: Path | None = None) -> dict:
    target = path or config.EVALUATION_MD
    markdown = build_evaluation_report(context)
    target.write_text(markdown, encoding="utf-8")
    return {"path": str(target), "bytes": len(markdown)}
