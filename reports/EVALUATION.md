# TrustScore — Model Evaluation Report (`trustscore-1.0.0`)

_Generated 2026-10-17T14:56:17.092804+00:00 by `python -m training.src.train`._

> TrustScore is a demonstration of responsible-AI credit decisioning. It is not a real lending tool, not financial advice, and not a loan offer. Decisions shown are simulated.

## 1. Summary

TrustScore is a credit-default model plus an explicit decision policy. The calibrated model reaches **ROC-AUC 0.9490 [0.9413, 0.9559]**, **PR-AUC 0.8984 [0.8847, 0.9113]** and **Brier 0.0527 [0.0483, 0.0571]** on the held-out test split (n=6,484). The decision policy is the analytic cost crossover of the configured cost matrix, verified by an independent grid search.

The honest caveats are part of the summary, not a footnote: the dataset is public and not from the target market; two of the strongest features are lender-assigned; the fairness audit covers only the attributes the data contains; and fairness mitigation does not clear every attribute.

## 2. Dataset provenance

- Source: **Kaggle Credit Risk Dataset (laotse)**
- Reference: https://www.kaggle.com/datasets/laotse/credit-risk-dataset
- Rows: raw 0, cleaned 0
- Positive (default) rate: **n/a**
- Split sizes: {'train': 19449, 'validation': 6483, 'test': 6484}
- Seed: `42`

Cleaning decisions (from the pipeline's own report):

```json
{
  "rows_in": 32581,
  "rows_out": 32416,
  "duplicate_rows_removed": 165,
  "missing_target_removed": 0,
  "age_out_of_range": 5,
  "emp_length_out_of_range": 2,
  "income_non_positive": 0,
  "loan_amnt_out_of_range": 0,
  "missing_after": {
    "person_age": 5,
    "person_emp_length": 889,
    "loan_int_rate": 3095
  }
}
```

**Provenance note.** `loan_grade` is assigned by the lender at origination and `loan_int_rate` follows from it. Both are underwriting *outputs* rather than independent applicant signals, so a model that uses them may be reproducing the lender's own risk tiering. Section 7 quantifies this.

## 3. Split strategy

Protocol: **3-way (train / validation / test)**. The full contract is in `docs/EVALUATION.md`.

- **train** — fit booster + cross-fitted isotonic calibration + equalized-odds mitigation
- **validation** — policy verification and the interactive auditor *policy tuning* set
- **test** — one-time held-out final evaluation (model card, evaluation report)

The auditor console reads the policy tuning set (`validation`, n=6,483). Row-level data for the final evaluation set (`test`, n=6,484) is not shipped, so the final set cannot be inspected interactively by accident. Mitigation is fitted on **train (out-of-fold calibrated scores)**.

Consequence: **tuning-set figures are not the published test figures.** They are expected to differ, and are labelled as tuning-set figures wherever they appear.

## 4. Baselines

| Model | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- |
| Logistic regression (baseline) | 0.8775 | 0.7294 | 0.1007 |
| LightGBM (uncalibrated) | 0.9495 | 0.9064 | 0.0527 |
| LightGBM + isotonic (deployed) | **0.9490** | **0.8984** | **0.0527** |

All three are measured on the same held-out test split. Calibration does not change ranking (ROC-AUC/PR-AUC move only through ties), but it is what makes the probability interpretable as a probability and therefore what makes the cost-based policy meaningful.

## 5. Calibration

- Brier score: **0.0527** — mean squared error of the predicted probabilities (lower is better).
- Expected calibration error: **0.0053** — average |predicted − observed| across probability bins.
- The isotonic map is fitted on 5-fold **out-of-fold** predictions within the training split, so it is not fitted on in-sample scores.

| Bin | n | Mean predicted | Observed | Observed 95% CI |
| --- | --- | --- | --- | --- |
| 0.00–0.10 | 4,044 | 0.0341 | 0.0302 | [0.025325742758265365, 0.035902344823027336] |
| 0.10–0.20 | 960 | 0.1428 | 0.1385 | [0.11812456074636393, 0.1618401139470712] |
| 0.20–0.30 | 191 | 0.2234 | 0.2670 | [0.2093198034419278, 0.3338988931813805] |
| 0.30–0.40 | 201 | 0.3587 | 0.3582 | [0.2951525950476804, 0.42658361478469736] |
| 0.40–0.50 | 5 | 0.4000 | 0.6000 | [0.23071993220883702, 0.8823817688407467] |
| 0.50–0.60 | 50 | 0.5068 | 0.4800 | [0.347969123955057, 0.6148848774119157] |
| 0.60–0.70 | 21 | 0.6411 | 0.6667 | [0.45373075657210293, 0.828054635673163] |
| 0.70–0.80 | 0 | n/a | n/a | None |
| 0.80–0.90 | 55 | 0.8509 | 0.8182 | [0.6966928866143076, 0.898124385519693] |
| 0.90–1.00 | 957 | 0.9981 | 0.9969 | [0.990823967393005, 0.9989333453628123] |

## 6. Decision-cost assumptions and the policy

| Cost | Value (per unit of loan exposure) |
| --- | --- |
| false approve | 1.0000 |
| false decline | 0.2000 |
| review | 0.0500 |

These are **assumptions, not measurements.** They encode a preference: a false approve is treated as five times as costly as a false decline, and a manual review costs 0.05. Every threshold in the product follows from them; change them and the policy changes.

- Analytic policy: approve ≤ **0.05000**, decline ≥ **0.75000**.
- Grid verification (validation split): approve 0.05534 / decline 0.67619, cost delta **0.00000000** — i.e. the same cost. The surface is flat across a gap in the score distribution, so the grid point is an arbitrary plateau member; the analytic crossover is the exact per-applicant optimum and generalises to unseen applicants.
- Expected cost per loan (validation): 0.0266; realized cost per loan (test): 0.0264.
- Test approval rate: **0.4528** (bands {'approve': 2936, 'refer': 2536, 'decline': 1012}).

## 7. Fairness evaluation

- Disparate-impact floor (four-fifths rule): **0.8000**
- Audited attributes: person_home_ownership, age_band, income_band, loan_intent, cb_person_default_on_file
- **Not available in the data:** gender, race/ethnicity, geography/region, marital status, disability status

| Attribute | DI ratio | DI 95% CI | EO gap | EO 95% CI | Groups used |
| --- | --- | --- | --- | --- | --- |
| Home ownership | 0.3750 | [0.3548, 0.3999] | 0.4889 | [0.4620, 0.5168] | 3 / 4 |
| Age band | 0.8439 | [0.7116, 0.9047] | 0.0950 | [0.0562, 0.1925] | 4 / 7 |
| Income band | 0.3797 | [0.3496, 0.4142] | 0.3286 | [0.2868, 0.3671] | 4 / 4 |
| Loan purpose | 0.5457 | [0.4872, 0.5751] | 0.3015 | [0.2632, 0.3541] | 6 / 6 |
| Prior default on file | 0.2698 | [0.2333, 0.3114] | 0.4114 | [0.3767, 0.4449] | 2 / 2 |

Guardrail status on the test split: **BREACH** (4 attribute(s) below the floor).

| Breaching attribute | Lowest group (n) | Selection rate | DI ratio | DI 95% CI |
| --- | --- | --- | --- | --- |
| Home ownership | RENT (n=3339) | 0.3339 | 0.3750 | [0.3548, 0.3999] |
| Income band | low (n=2139) | 0.2613 | 0.3797 | [0.3496, 0.4142] |
| Loan purpose | DEBTCONSOLIDATION (n=1012) | 0.3656 | 0.5457 | [0.4872, 0.5751] |
| Prior default on file | Y (n=1166) | 0.1407 | 0.2698 | [0.2333, 0.3114] |

> A ratio at or above the floor for one attribute is not evidence that the system is fair overall, and it is not a legal-compliance finding. Every remaining breach is listed here and must be read together with its confidence interval and its group sizes.

## 8. Fairness mitigation: what it buys and what it costs

Mitigation is an **experimental policy intervention** (equalized-odds post-processing), not a fairness guarantee and not a legal-compliance finding. It targets one attribute at a time.

- Method: **equalized_odds** on `loan_intent`; fitted on train (out-of-fold calibrated scores).

**Final evaluation — held-out test split:**

| Metric | Baseline | After mitigation |
| --- | --- | --- |
| Approval rate | 0.4528 | 0.4548 |
| Realized cost per loan | 0.0264 | 0.0277 |
| Disparate-impact ratio | 0.5457 | 0.8588 |
| Equalized-odds gap | 0.3015 | 0.0664 |
| Attributes breaching the floor | 4 | **3** |

**Measured cost of the intervention: 0.001332 additional realized cost per unit of exposure** on the held-out test split (the trade-off is real, and it should be stated next to the improvement).

**Policy tuning set (validation, what the console shows):** DI 0.5199 → 0.8487; EO gap 0.3350 → 0.0893; breaches 4 → 3.

**This mitigation is fitted for `loan_intent` only.** On the test split it clears that attribute, but 3 attribute(s) remain below the four-fifths floor overall (Home ownership, Income band, Prior default on file). Clearing one attribute says nothing about the others, and every figure here is sensitive to the dataset, the group definitions, group sizes, the cost matrix and the metric chosen.

## 9. Feature provenance (ablation)

loan_grade is assigned by the lender at origination and loan_int_rate follows from it, so both encode the lender's own underwriting judgement rather than an independent applicant signal.

| Model (same split, uncalibrated) | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- |
| Full feature set | 0.9495 | 0.9064 | 0.0527 |
| Without `loan_grade`, `loan_int_rate` | 0.9031 | 0.8202 | 0.0818 |

Removing the lender-assigned fields costs **0.0464 ROC-AUC**. That gap is the part of the headline performance that came from reproducing the lender's own decision, and it is the honest expectation for a system that must score applicants the lender has not already judged.

> Both rows are uncalibrated and evaluated on the same test split, so the delta is like-for-like. It measures how much of the headline ranking skill came from reproducing the lender's own risk tiering; a system that must score applicants the lender has not already judged should expect the lower number.

## 10. Out-of-population robustness

The dataset has no timestamp, so a temporal split is not possible. Holding out an entire income segment is the closest available proxy: it shows how ranking skill changes on applicants drawn from a part of the population the model never trained on. The random stratified split used for the headline metrics does not capture this.

| Evaluation | ROC-AUC | PR-AUC |
| --- | --- | --- |
| In-population (n=5,190) | 0.9568 | 0.9255 |
| Out-of-population — top income quintile (person_income > q80) (n=6,464) | 0.8826 | 0.7168 |

Ranking skill drops by **0.0743 ROC-AUC** on the held-out population. The headline test metrics come from a random stratified split, which shares the training distribution; they are not a forecast of performance on future or different applicants.

## 11. Recourse and explanation limitations

- Recommendations are limited to fields an applicant actually controls (requested amount, loan purpose). Income is surfaced only as an explicitly-labelled informational option.
- Immutable factors (age, tenure, employment length, prior default, credit history length, lender-assigned grade/rate) are never suggested, and the API lists them explicitly so it is visible what was *not* used.
- Recommendations are constrained to plausible ranges; there is no unbounded optimiser that will propose a 40x income increase.
- When no change in the applicant-controlled fields reaches a better band, the API says so explicitly instead of inventing a marginal suggestion.
- Every scenario carries an explicit non-guarantee disclaimer. A route is a model-generated estimate, not a promise and not a condition any lender has agreed to.

## 12. Deployment constraints

- The production artifact is served with **native LightGBM only**: no scikit-learn, SciPy, SHAP or matplotlib at runtime, so it fits a serverless bundle. Explainability is computed from LightGBM's own prediction contributions.
- The default deployment is a lightweight API plus a web front end on the free tier. Async jobs are mirrored to durable storage when a database is configured; without one, job state is in-process and a recycled instance loses it (documented, not hidden).
- Governance logging is **best-effort and anonymised**: a failure to write never blocks an applicant, and only derived/non-identifier fields are stored.
- Tracking of live outcomes, live drift against a live label stream, and real population monitoring are **not** implemented, because the public dataset has no live outcome stream. Drift is monitored on input distributions only.

## 13. Limitations

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

## 14. Reproduction

```
python -m training.src.train
```

Seeded with `SEED = 42`. Produces `api/artifacts/*`, `reports/*.json`, `reports/MODEL_CARD.md` and this report.
