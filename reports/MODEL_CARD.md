# Model Card — TrustScore (`trustscore-1.0.0`)

_Generated 2026-10-17T13:32:53.601837+00:00 by `python -m training.src.train`._

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

## Performance (test split)

| Model | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- |
| Logistic regression (baseline) | 0.8775 | 0.7294 | 0.1007 |
| LightGBM (uncalibrated) | 0.9495 | 0.9064 | 0.0527 |
| LightGBM (calibrated) | 0.9490 | 0.8984 | 0.0527 |

At a 0.50 rounding threshold the calibrated model gives precision 0.9575, recall 0.7313, F1 0.8293.

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

- Approve band: PD ≤ **0.0553**
- Refer band: 0.0553 < PD < 0.6762
- Decline band: PD ≥ **0.6762**
- Expected cost per loan at these thresholds (validation): **0.0266** exposure-weighted cost units
- Thresholds are configurable in the lender view.

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

**Not available in this dataset (reported honestly, not estimated):** gender, race/ethnicity, geography/region, marital status, disability status.

### Guardrail

- Disparate-impact floor: **0.8000**
- Status: **BREACH** (4 attribute(s) below the floor)

## Fairness mitigation (equalized odds)

The fairness-tuned model (**Beta**, `trustscore-1.1.0`) keeps the same booster and appends a *post-processing* rule: per-group randomised probability thresholds that equalise the true-positive and false-positive rates across age bands.

- Method: **equalized_odds**
- Attribute: `loan_intent`
- Target TPR / FPR: 0.5846 / 0.0310
- Base approve threshold: 0.0553

| Metric | Baseline | After mitigation |
| --- | --- | --- |
| Approval rate | 0.453 | 0.457 |
| Realized cost per loan | 0.0264 | 0.0276 |
| Disparate-impact ratio | 0.5457 | 0.8427 |
| Equalized odds difference | 0.3015 | 0.0664 |

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

## Ethical considerations

- Protected attributes are never used as model inputs and are never suggested as things to change.
- Reason codes are shown instead of raw numbers so applicants get actionable, non-technical explanations.
- Every prediction carries the model version and a prediction ID for auditability.

## Version and reproducibility

- Model version: **trustscore-1.0.0**
- Fixed random seed: 42
- Artifacts: `api/artifacts/model.joblib`, `api/artifacts/metadata.json`, `api/artifacts/model_fair.joblib`, `api/artifacts/registry.json`
- Reports: `reports/metrics_v1.json`, `reports/fairness_v1.json`, `reports/fairness_v110.json`, `reports/calibration_v1.json`
