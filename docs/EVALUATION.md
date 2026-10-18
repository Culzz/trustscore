# Evaluation protocol

This document fixes **how TrustScore is evaluated**, so that every number quoted
anywhere in the product can be traced to one set of data and one procedure. It is
the contract that `training/src/train.py` implements; the generated results live in
[`reports/EVALUATION.md`](../reports/EVALUATION.md) and
[`reports/MODEL_CARD.md`](../reports/MODEL_CARD.md).

## Why a protocol at all

The easiest way to publish flattering numbers is to evaluate and tune on the same
data. Three specific failure modes are easy to fall into and are ruled out here:

1. **Tuning on the final test set.** If the auditor console inspects row-level test
   data and a human then changes the policy, the "held-out" test set has silently
   become a validation set, and its numbers are no longer an unbiased estimate.
2. **Fitting a fairness correction on the set you advertise it on.** A mitigation
   rule fitted on the same rows it is reported on looks better than it is.
3. **Reporting a point estimate as if it were certain.** Disparate-impact ratios on
   groups of very different sizes move a lot under resampling, and a bare number
   invites over-reading.

## The role split

Data is split **60 / 20 / 20**, stratified on the target, `seed = 42`
(`training/src/features.py::stratified_split`).

| Split | Rows | Fits | Used for |
| --- | --- | --- | --- |
| **train** | 19,449 | booster, isotonic calibration (5-fold out-of-fold), equalized-odds mitigation | model fitting only |
| **validation** | 6,483 | — (already fitted on train) | policy verification **and** the interactive *policy tuning set* |
| **test** | 6,484 | — | **one-time** final evaluation; quoted in the model card and the report |

Rules that follow from the table:

* **Booster.** Trained on `train`, early-stopped on `validation` (a legitimate use:
  the stopping point is a hyper-parameter, and `validation` is not the final set).
* **Calibration.** The isotonic map is fitted on 5-fold **out-of-fold** predictions
  *within* `train`, so the calibration curve is not fitted on in-sample scores and
  not fitted on `validation` or `test`.
* **Equalized-odds mitigation.** Fitted on `train`, using those out-of-fold
  calibrated scores. It is therefore *not* fitted on the tuning set and *not*
  fitted on the final test set: both the console's tuning-set figures and the
  card's test figures are out-of-sample for the mitigation itself.
* **Decision thresholds.** Derived analytically from the cost matrix (see below),
  then **verified** on `validation` by an independent brute-force search.
* **The auditor console.** Reads only the tuning set. The row-level test split is
  never shipped as an artifact (`api/artifacts/portfolio.json` is the validation
  split), so the final set cannot be inspected interactively by accident.
* **Tuning-set figures are not published test figures.** They are labelled as such
  everywhere they appear. They are expected to differ from the card.

The role split is written into `api/artifacts/metadata.json` under
`evaluation_protocol`, and into `registry.json`, so the API and any external reader
can state which set a number came from.

## The decision policy (and why it is analytic, not grid-searched)

For one applicant with default probability `p` and exposure `A`, with the cost
matrix `false_approve = FA`, `false_decline = FD`, `review = R`:

```
cost(approve) = p · FA · A
cost(review)  = R · A
cost(decline) = (1 − p) · FD · A
```

`A` is a common positive factor, so the cheapest action depends only on `p`. The
crossover points are:

```
approve → refer   at  p = R / FA                  = 0.05
refer   → decline at  p = 1 − R / FD              = 0.75
```

**These analytic crossovers are the deployed policy.** They minimise expected cost
for *every* applicant, including ones the training sample never contained; they are
not a fit to the sample.

A numeric grid search (`decision.grid_thresholds`) is also run, purely as a check.
On the validation split it returns `approve ≤ 0.05534 / decline ≥ 0.67619` — a
*different-looking* pair at **exactly the same cost** (`delta = 0.000e+00`). The
reason is a hard gap in the score distribution (no validation applicant sits between
0.667 and 0.811), which makes the expected-cost surface perfectly flat across a wide
interval; the grid's first-wins tie-break then returns the lowest point of that
plateau.

Deploying the grid point would be a mistake: it is an artifact of the sample's
gaps, and it disagrees with the cost-optimal rule on unseen applicants (e.g. a PD of
0.052 or 0.70). So the protocol is:

* **analytic** thresholds decide the policy;
* **grid** + `cost_equivalence` prove the analytic policy is cost-optimal on the
  observed data, or flag a real disagreement.

`metadata.thresholds` records both, plus `selected_by`, `grid_verification` and the
full `cost_equivalence` block, so the two can never be silently conflated again.

## Uncertainty

Every headline figure that a reader might act on is reported with an interval:

* **Rates** (selection rate, TPR, FPR, calibration bins): 95% **Wilson** score
  intervals, which stay sane at small `n`.
* **Disparity ratios** (disparate-impact ratio, equalized-odds gap): 95% **percentile
  bootstrap**, resampling *applicants* with replacement (400 draws offline).
* **Ranking metrics** (ROC-AUC, PR-AUC, Brier): percentile bootstrap on the test
  split.

These intervals capture **sampling noise only**. They do **not** cover dataset shift,
label noise, group-definition choices, metric choice or model-selection uncertainty.
An interval that contains 0.80 does not mean the floor is met.

## What is deliberately *not* claimed

* Passing the four-fifths ratio for one attribute is not evidence of overall
  fairness and is not a legal-compliance finding.
* Mitigation is an experimental policy intervention targeting **one** attribute at a
  time. Other audited attributes can and do remain below the floor with it enabled;
  those remaining breaches are listed explicitly rather than hidden.
* Counterfactual "routes to approval" are model-generated estimates, not promises
  and not conditions any lender has agreed to.
* The random stratified split measures performance on a similar distribution. It is
  not a forecast for future applicants or a different population; the
  out-of-population check in the report exists precisely because the random split
  hides that difference.
* `loan_grade` and `loan_int_rate` are lender-assigned fields that already encode an
  underwriting judgement. Part of the headline skill is the model reproducing the
  lender's own risk tiering; the ablation in the report quantifies it.

## Reproducing

```
python -m training.src.train
```

writes `api/artifacts/*`, `reports/*.json`, `reports/MODEL_CARD.md` and
`reports/EVALUATION.md`. The run is seeded (`SEED = 42`); the only nondeterminism is
whatever the LightGBM build itself introduces.
