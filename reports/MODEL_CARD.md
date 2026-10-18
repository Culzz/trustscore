# Model Card — TrustScore (`trustscore-1.0.0`)

_Generated 2026-10-17T14:56:17.092804+00:00 by `python -m training.src.train`._

> TrustScore is a demonstration of responsible-AI credit decisioning. It is not a real lending tool, not financial advice, and not a loan offer. Decisions shown are simulated.

## Overview

TrustScore estimates the probability that a loan applicant defaults, turns that estimate into a simulated approve/refer/decline decision under an explicit cost matrix, explains the estimate in plain language, and audits the result for group-level disparities.

## Intended use

- **Intended for:** demoing and studying an explainable, fairness-aware credit decisioning workflow; teaching; portfolio review.
- **Not intended for:** real lending, credit scoring of real people, regulatory reporting, or any financial decision.

## Data

- Source: https://www.kaggle.com/datasets/laotse/credit-risk-dataset
- Rows after cleaning: **32,416** (from 32,581 raw)
- Default rate: **21.87%**
- Splits: train 19,449 / validation 6,483 / test 6,484 (stratified, seed 42)
- Model features (13): `person_age`, `person_income`, `person_emp_length`, `loan_amnt`, `loan_int_rate`, `loan_percent_income`, `cb_person_cred_hist_length`, `emp_length_missing`, `int_rate_missing`, `person_home_ownership`, `loan_intent`, `loan_grade`, `cb_person_default_on_file`
- Audit-only groupings (never model features): age band, income band

### Cleaning

- Duplicate rows removed: 165
- Ages outside 18–100: 5 set to missing
- Employment length > 60 years: 2 set to missing
- Non-positive income: 0 set to missing
- Loan amounts out of range: 0 set to missing
- Remaining missing values (imputed in-pipeline): person_age (5), person_emp_length (889), loan_int_rate (3,095)

## Evaluation protocol

Three disjoint sets are used. Every number in this card states which set it comes from:

- **train** — fit booster + cross-fitted isotonic calibration + equalized-odds mitigation
- **validation** — policy verification and the interactive auditor *policy tuning* set
- **test** — one-time held-out final evaluation (model card, evaluation report)

- The auditor console runs **only** on the policy tuning set (`validation`, n=6,483). Row-level data for the final evaluation set (`test`, n=6,484) is deliberately not shipped, so it stays held out. Tuning-set figures are therefore *not* the published test figures.
- Equalized-odds mitigation is fitted on train (out-of-fold calibrated scores) and measured on test (headline), validation (console/tuning).

## Performance (test split)

| Model | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- |
| Logistic regression (baseline) | 0.8775 | 0.7294 | 0.1007 |
| LightGBM (uncalibrated) | 0.9495 | 0.9064 | 0.0527 |
| LightGBM (calibrated) | 0.9490 | 0.8984 | 0.0527 |

At a 0.50 rounding threshold the calibrated model gives precision 0.9575, recall 0.7313, F1 0.8293.

95% bootstrap confidence intervals (test split, 400 resamples of the applicants): ROC-AUC [0.9413, 0.9559], PR-AUC [0.8847, 0.9113], Brier [0.0483, 0.0571]. These capture sampling noise only — not dataset shift, label noise or model-selection uncertainty.

## Calibration

- Brier score (calibrated): **0.0527**
- Expected calibration error (10 bins): **0.0053**
- The reliability curve is stored in `reports/calibration_v1.json`.

## Decision policy and cost

| Cost | Value (per unit of loan amount) |
| --- | --- |
| False approve (approve a defaulter) | 1.0 |
| False decline (decline a good applicant) | 0.2 |
| Manual review | 0.05 |

The band thresholds are derived **analytically** from the cost matrix: for each applicant the policy picks the cheapest of approve / refer / decline, which yields two crossover points.

- Approve → refer at PD = review ÷ false_approve = **0.05000**
- Refer → decline at PD = 1 − review ÷ false_decline = **0.75000**

- Deployed approve band: PD ≤ **0.05000**
- Deployed refer band: 0.05000 < PD < 0.75000
- Deployed decline band: PD ≥ **0.75000**
- **Verification.** An independent brute-force grid search over the validation split found approve ≤ 0.05534 / decline ≥ 0.67619 at a cost 0.00000000 above the analytic policy — i.e. cost-identical. The expected-cost surface is flat across a gap in the score distribution, so the grid point is an arbitrary member of a plateau while the analytic crossover is the exact per-applicant optimum. Analytic-is-cost-optimal: **True**.
- Expected cost per loan at these thresholds (validation): **0.0266** exposure-weighted cost units
- Test approval rate: **0.4528** (bands: {'approve': 2936, 'refer': 2536, 'decline': 1012})
- Thresholds are configurable in the auditor view.

## Fairness

> This dashboard reports statistical disparities between groups. It does not establish legal compliance or non-compliance, and it is not a legal opinion.

### Home ownership

| Group | n | Approval rate | TPR | FPR | Precision |
| --- | --- | --- | --- | --- | --- |
| MORTGAGE | 2,637 | 0.5226 | 0.5851 | 0.0925 | 0.9775 |
| OTHER *(small sample)* | 15 | 0.2667 | 0.4444 | 0.0000 | 1.0000 |
| OWN | 493 | 0.8905 | 0.9670 | 0.0000 | 1.0000 |
| RENT | 3,339 | 0.3339 | 0.4781 | 0.0145 | 0.9865 |

- Selection-rate ratio (min/max): **0.3750**
- Demographic parity difference: 0.5565
- Equal opportunity difference (TPR gap): 0.4889
- Equalized odds difference (max TPR/FPR gap): 0.4889
- Disparate-impact ratio (four-fifths rule): **0.3750** [BREACH vs floor 0.8000]
- Disparate-impact 95% bootstrap CI: [0.3548, 0.3999]
- Equalized-odds 95% bootstrap CI: [0.4620, 0.5168]
- Groups used in the ratios: 3 of 4 (smaller groups are shown but excluded).

### Age band

| Group | n | Approval rate | TPR | FPR | Precision |
| --- | --- | --- | --- | --- | --- |
| 18-25 | 3,077 | 0.4355 | 0.5588 | 0.0212 | 0.9888 |
| 26-35 | 2,721 | 0.4550 | 0.5647 | 0.0436 | 0.9798 |
| 36-45 | 560 | 0.5161 | 0.6345 | 0.0526 | 0.9792 |
| 46-55 | 102 | 0.5000 | 0.6538 | 0.0000 | 1.0000 |
| 56-65 *(small sample)* | 18 | 0.7778 | 0.8235 | 0.0000 | 1.0000 |
| 66+ *(small sample)* | 5 | 0.6000 | 0.6000 | n/a | 1.0000 |
| unknown *(small sample)* | 1 | 1.0000 | 1.0000 | n/a | 1.0000 |

- Selection-rate ratio (min/max): **0.8439**
- Demographic parity difference: 0.0806
- Equal opportunity difference (TPR gap): 0.0950
- Equalized odds difference (max TPR/FPR gap): 0.0950
- Disparate-impact ratio (four-fifths rule): **0.8439** [PASS vs floor 0.8000]
- Disparate-impact 95% bootstrap CI: [0.7116, 0.9047]
- Equalized-odds 95% bootstrap CI: [0.0562, 0.1925]
- Groups used in the ratios: 4 of 7 (smaller groups are shown but excluded).

### Income band

| Group | n | Approval rate | TPR | FPR | Precision |
| --- | --- | --- | --- | --- | --- |
| high | 661 | 0.6884 | 0.7375 | 0.2222 | 0.9692 |
| low | 2,139 | 0.2613 | 0.4089 | 0.0089 | 0.9875 |
| lower-middle | 2,142 | 0.4468 | 0.5410 | 0.0327 | 0.9864 |
| upper-middle | 1,542 | 0.6258 | 0.6941 | 0.0710 | 0.9876 |

- Selection-rate ratio (min/max): **0.3797**
- Demographic parity difference: 0.4270
- Equal opportunity difference (TPR gap): 0.3286
- Equalized odds difference (max TPR/FPR gap): 0.3286
- Disparate-impact ratio (four-fifths rule): **0.3797** [BREACH vs floor 0.8000]
- Disparate-impact 95% bootstrap CI: [0.3496, 0.4142]
- Equalized-odds 95% bootstrap CI: [0.2868, 0.3671]
- Groups used in the ratios: 4 of 4 (smaller groups are shown but excluded).

### Loan purpose

| Group | n | Approval rate | TPR | FPR | Precision |
| --- | --- | --- | --- | --- | --- |
| DEBTCONSOLIDATION | 1,012 | 0.3656 | 0.5042 | 0.0304 | 0.9757 |
| EDUCATION | 1,314 | 0.4376 | 0.5269 | 0.0256 | 0.9896 |
| HOMEIMPROVEMENT | 728 | 0.3668 | 0.4799 | 0.0275 | 0.9813 |
| MEDICAL | 1,234 | 0.3914 | 0.5186 | 0.0311 | 0.9793 |
| PERSONAL | 1,096 | 0.4599 | 0.5621 | 0.0664 | 0.9702 |
| VENTURE | 1,100 | 0.6700 | 0.7813 | 0.0063 | 0.9986 |

- Selection-rate ratio (min/max): **0.5457**
- Demographic parity difference: 0.3044
- Equal opportunity difference (TPR gap): 0.3015
- Equalized odds difference (max TPR/FPR gap): 0.3015
- Disparate-impact ratio (four-fifths rule): **0.5457** [BREACH vs floor 0.8000]
- Disparate-impact 95% bootstrap CI: [0.4872, 0.5751]
- Equalized-odds 95% bootstrap CI: [0.2632, 0.3541]
- Groups used in the ratios: 6 of 6 (smaller groups are shown but excluded).

### Prior default on file

| Group | n | Approval rate | TPR | FPR | Precision |
| --- | --- | --- | --- | --- | --- |
| N | 5,318 | 0.5212 | 0.6293 | 0.0409 | 0.9856 |
| Y | 1,166 | 0.1407 | 0.2179 | 0.0136 | 0.9634 |

- Selection-rate ratio (min/max): **0.2698**
- Demographic parity difference: 0.3806
- Equal opportunity difference (TPR gap): 0.4114
- Equalized odds difference (max TPR/FPR gap): 0.4114
- Disparate-impact ratio (four-fifths rule): **0.2698** [BREACH vs floor 0.8000]
- Disparate-impact 95% bootstrap CI: [0.2333, 0.3114]
- Equalized-odds 95% bootstrap CI: [0.3767, 0.4449]
- Groups used in the ratios: 2 of 2 (smaller groups are shown but excluded).

**Not available in this dataset (reported honestly, not estimated):** gender, race/ethnicity, geography/region, marital status, disability status.

### Guardrail

- Disparate-impact floor: **0.8000**
- Status: **BREACH** (4 attribute(s) below the floor)

| Breaching attribute | Lowest group (n) | Selection rate | DI ratio | DI 95% CI |
| --- | --- | --- | --- | --- |
| Home ownership | RENT (3,339) | 0.3339 | 0.3750 | [0.3548, 0.3999] |
| Income band | low (2,139) | 0.2613 | 0.3797 | [0.3496, 0.4142] |
| Loan purpose | DEBTCONSOLIDATION (1,012) | 0.3656 | 0.5457 | [0.4872, 0.5751] |
| Prior default on file | Y (1,166) | 0.1407 | 0.2698 | [0.2333, 0.3114] |

> A ratio at or above the floor for one attribute is not evidence that the system is fair overall, and it is not a legal-compliance finding. Every remaining breach is listed here and must be read together with its confidence interval and its group sizes.

## Fairness mitigation (equalized odds)

The fairness-tuned model (**Beta**, `trustscore-1.1.0`) keeps the same booster and appends a *post-processing* decision rule: per-group randomised probability thresholds chosen so that the true-positive and false-positive rates line up across the groups of one attribute.

- Method: **equalized_odds**
- Attribute: `loan_intent`
- Target TPR / FPR: 0.5838 / 0.0386
- Base approve threshold: 0.0500
- Fitted on: train (out-of-fold calibrated scores) (min group size 50)
- Measured on: test (headline, below) and validation (console)

**Final evaluation (held-out test split)**

| Metric | Baseline | After mitigation |
| --- | --- | --- |
| Approval rate | 0.453 | 0.455 |
| Realized cost per loan | 0.0264 | 0.0277 |
| Disparate-impact ratio | 0.5457 | 0.8588 |
| Equalized odds difference | 0.3015 | 0.0664 |
| Attributes breaching the floor | 4 | 3 |

The measured cost of this intervention is **0.001332** additional realized cost per unit of exposure on the held-out test split.

**Policy tuning set (validation, what the auditor console shows):** DI 0.5199 → 0.8487; EO gap 0.3350 → 0.0893; breaches 4 → 3.

> **Caveat.** Mitigation is an experimental policy intervention, not a fairness guarantee and not a compliance finding. Even with it enabled, 3 attribute(s) remain below the floor (Home ownership, Income band, Prior default on file). Clearing one attribute says nothing about the others, and every figure above is sensitive to the dataset, the group definitions, group sizes, the cost matrix and the metric chosen.

## Feature provenance and ablation

The dataset's `loan_grade` and `loan_int_rate` are **lender-assigned** fields: they already encode an underwriting judgement made at origination. A model that uses them may be partly reproducing the lender's own risk tiering rather than predicting independently. To quantify that, a second model was trained on the same split with those fields removed.

| Model | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- |
| Full feature set | 0.9495 | 0.9064 | 0.0527 |
| Without `loan_grade`, `loan_int_rate` | 0.9031 | 0.8202 | 0.0818 |

Removing the lender-assigned fields costs **0.0464 ROC-AUC** — that gap is the part of the headline performance that came from reproducing the lender's own decision, and it is the honest expectation for a system that must score applicants the lender has not already judged.

> Both rows are uncalibrated and evaluated on the same test split, so the delta is like-for-like. It measures how much of the headline ranking skill came from reproducing the lender's own risk tiering; a system that must score applicants the lender has not already judged should expect the lower number.

## Robustness: out-of-population check

The dataset has no timestamp, so a temporal split is not possible. Holding out an entire income segment is the closest available proxy: it shows how ranking skill changes on applicants drawn from a part of the population the model never trained on. The random stratified split used for the headline metrics does not capture this.

| Evaluation | ROC-AUC | PR-AUC |
| --- | --- | --- |
| In-population (held-out slice of the modelled segment, n=5,190) | 0.9568 | 0.9255 |
| Out-of-population (top income quintile (person_income > q80), n=6,464) | 0.8826 | 0.7168 |

Ranking skill drops by **0.0743 ROC-AUC** on the held-out population. The headline test metrics come from a random stratified split, which shares the training distribution; they are not a forecast of performance on future or different applicants.

## Most influential features

| Feature | Mean absolute contribution |
| --- | --- |
| `loan_percent_income` | 0.9408 |
| `person_income` | 0.7228 |
| `person_home_ownership_OWN` | 0.5194 |
| `loan_int_rate` | 0.5037 |
| `loan_intent_VENTURE` | 0.3821 |
| `person_home_ownership_RENT` | 0.3210 |
| `loan_grade_D` | 0.2500 |
| `loan_grade_A` | 0.2069 |
| `loan_intent_HOMEIMPROVEMENT` | 0.1604 |
| `person_emp_length` | 0.1468 |
| `loan_amnt` | 0.1390 |
| `loan_grade_B` | 0.1330 |

## Limitations

- Trained on the public Kaggle Credit Risk Dataset, which is not Nigerian credit data. It demonstrates the system, not a production score for any real market.
- Fairness is audited only for attributes present in the data (home ownership, age band, income band, loan purpose, prior default flag). Gender, race/ethnicity, geography and other attributes are not in the dataset and are reported as 'not available'.
- Fairness figures are statistical disparities between groups. They do not prove legal compliance or non-compliance.
- Counterfactuals are model-generated scenarios, not guaranteed approval conditions.
- Performance monitoring is offline/simulated: the public dataset has no live outcome stream.
- Deployment targets a serverless environment, so the production model is kept deliberately light (LightGBM only; no SHAP library at runtime).
- The measured ROC-AUC is optimistic for a real credit setting: the dataset's loan grade and interest rate are lender-assigned fields that already encode an underwriting judgement, so part of the model's skill is reproducing the lender's own risk tiering rather than independent prediction.
- All headline metrics come from a single random stratified split of one public dataset. A random split measures performance on a similar distribution; it does not establish performance on future applicants or on a different population. The out-of-population check in this card exists precisely because the random split hides the difference.
- The auditor console runs only on the validation (policy tuning) split. Its live figures are therefore not the published test figures, and it must not be used to select a policy on the basis of test-set performance.
- Fairness mitigation is an experimental policy intervention, not a fairness guarantee and not a legal-compliance finding. It targets one attribute at a time; other audited attributes can and do remain below the four-fifths floor with it enabled.

## Ethical considerations

- Protected attributes are never used as model inputs and are never suggested as things to change.
- Reason codes are shown instead of raw numbers so applicants get actionable, non-technical explanations.
- Every prediction carries the model version and a prediction ID for auditability.

## Version and reproducibility

- Model version: **trustscore-1.0.0**
- Fixed random seed: 42
- Artifacts: `api/artifacts/model.joblib`, `api/artifacts/metadata.json`, `api/artifacts/model_fair.joblib`, `api/artifacts/registry.json`
- Reports: `reports/metrics_v1.json`, `reports/fairness_v1.json`, `reports/fairness_v110.json`, `reports/calibration_v1.json`
