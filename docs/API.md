# API

Base URL:

* local: `http://localhost:8000`
* Vercel: `https://<your-app>.vercel.app/api`
* Docker: `http://localhost:8000`

Interactive docs (OpenAPI) are served at `/docs` when `ENABLE_DOCS=true`.

Every response in this API is a **simulation**. Nothing is a loan offer.

## Endpoints

### Scoring

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/predict` | Calibrated probability of default, band, model version, prediction ID |
| POST | `/explain` | Top plain-language reasons, each with an ECOA-style code |
| POST | `/decision` | Apply the cost-based policy → approve / refer / decline (simulated) |
| POST | `/counterfactual` | Feasible changes that could move the applicant to a better band |
| POST | `/blueprint` | Contrastive "how to get approved" roadmap, with dual-target routes |

### Asynchronous application

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/apply` | Queue a full application → `202` + `job_id` |
| GET | `/jobs/{job_id}` | Status, milestone events and the final result |
| WS | `/ws/jobs/{job_id}` | Live milestone stream |

### Registry, governance and portfolio

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/model` | Model-card data: version, metrics, calibration, thresholds, fairness, drift, mitigation |
| GET | `/models` | Registry: versions with metrics/fairness, lineage, mitigation variants |
| GET | `/models/{version}` | Registry entry + full metadata for one version |
| GET | `/registry` | Raw registry (group definitions, mitigation parameters) |
| GET | `/mitigation` | Mitigation options, per-attribute variants and their measured impact |
| GET | `/context` | Macro feature-store context for a region (`?region=`) |
| GET | `/portfolio` | The policy tuning set (public validation split) the audit tools run on |
| POST | `/policy/simulate` | Cut-offs → approval rate, cost, profit, fairness, sweep curve |
| POST | `/ab/compare` | Alpha vs Beta on the same portfolio at the same policy |
| POST | `/bias/inject` | Adversarially skew one group and test the controls |
| GET | `/drift/live` | PSI/KS drift + adversarial-validation proxy (`?shift=`) |
| POST | `/alerts/test` | Generate (optionally deliver) a drift alert payload |
| GET | `/report.pdf` | Compliance Alignment & Fair Lending PDF |

### Service

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Service status |
| GET | `/stats` | Live anonymised counters (volume, mean PD, high-risk share) |
| GET | `/cache/stats` | Explainer cache and job-bus counters |

## Applicant payload

Eleven fields. `loan_percent_income` is **not** accepted: it is derived from
`loan_amnt / person_income` so results are reproducible.

```json
{
  "person_age": 31,
  "person_income": 42000,
  "person_home_ownership": "RENT",
  "person_emp_length": 4,
  "loan_intent": "MEDICAL",
  "loan_grade": "E",
  "loan_amnt": 10000,
  "loan_int_rate": 15.5,
  "cb_person_default_on_file": "N",
  "cb_person_cred_hist_length": 6
}
```

Validation ranges and allowed categorical values are enforced; bad input returns
`422` before the model is touched.

### Example

```bash
curl -s http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"person_age":31,"person_income":42000,"person_home_ownership":"RENT",
       "person_emp_length":4,"loan_intent":"MEDICAL","loan_grade":"E",
       "loan_amnt":10000,"loan_int_rate":15.5,"cb_person_default_on_file":"N",
       "cb_person_cred_hist_length":6}'
```

```json
{
  "prediction_id": "…",
  "model_version": "trustscore-1.0.0",
  "probability_of_default": 0.43,
  "band": "refer",
  "band_label": "medium",
  "thresholds": { "approve_max_pd": 0.05, "decline_min_pd": 0.75 },
  "created_at": "…",
  "disclaimer": "…"
}
```

## Policy overrides

`/decision`, `/predict`, `/explain`, `/counterfactual` and `/blueprint` take
optional query/policy arguments so you can explore without retraining:

```json
{
  "applicant": { "...": "..." },
  "approve_max_pd": 0.08,
  "decline_min_pd": 0.55,
  "model": "trustscore-1.1.0",
  "apply_fairness": true,
  "mitigation_attribute": "loan_intent",
  "region": "west",
  "use_macro_tilt": false
}
```

`model` selects a registry version (default `trustscore-1.0.0`, "Alpha").
`apply_fairness` switches on the equalized-odds post-processor; the response's
`scoring.mitigation` block reports whether it changed the band.

`use_macro_tilt` is **off by default**: the macro feature store is a seeded mock
and is deliberately not an input to the model. Turning the tilt on nudges the
*cut-offs*, never the score.

## `POST /apply` (asynchronous)

```bash
curl -s -X POST http://localhost:8000/apply \
  -H 'Content-Type: application/json' \
  -d '{"applicant": { ... }, "apply_fairness": true}'
```

```json
{ "job_id": "job_1a2b3c4d5e6f7788", "kind": "apply", "status": "queued", "backend": "memory" }
```

Milestones are `validated → scored → explained → recourse → complete`. Each event
is `{step, status, label, at, ...}` and the terminal `complete` event carries
`result`:

```json
{
  "scoring":    { "probability_of_default": 0.43, "final_band": "refer",
                  "thresholds": {...}, "mitigation": {...}, "group": "MEDICAL" },
  "reasons":    [ { "code": "AA-02", "factor": "...", "reason": "..." } ],
  "narrative":  { "headline": "...", "reason_codes": [...],
                  "guardrail": { "passed": true, "provider": "…" } },
  "blueprint":  { "status": "actionable", "routes": [...], "dual_target": {...} },
  "cache":      { "hits": 1, "misses": 0 }
}
```

Watch it either way:

```js
const ws = new WebSocket("ws://localhost:8000/ws/jobs/job_1a2b3c4d5e6f7788");
```

or poll `GET /jobs/{job_id}` every ~800 ms. On Vercel (no WebSockets in
serverless functions) the client falls back to polling automatically.

**Backends.** `JOB_BACKEND=auto` (default) resolves to `celery` when
`CELERY_BROKER_URL` or `REDIS_URL` is set, otherwise to in-process `memory`. The
events are identical on both paths.

## Audit endpoints

```bash
# Apply a policy and get KPIs + the fairness guardrail
curl -s -X POST http://localhost:8000/policy/simulate \
  -H 'Content-Type: application/json' \
  -d '{"approve_max_pd":0.05,"decline_min_pd":0.75,"include_sweep":true,
       "apply_fairness":true,"mitigation_attribute":"loan_intent"}'
```

```json
{
  "evaluation_set": "validation",
  "evaluation_role": "policy_tuning",
  "group_attribute": "loan_intent",
  "approval_rate": 0.4568, "expected_cost_per_loan": 0.024,
  "realized_cost_per_loan": 0.0276, "profit_per_loan": 4.1,
  "disparate_impact_ratio": 0.8427, "equalized_odds_difference": 0.0664,
  "uncertainty": {
    "method": "nonparametric bootstrap over applicants",
    "n_boot": 400,
    "disparate_impact_ratio_ci": [0.79, 0.90],
    "equalized_odds_difference_ci": [0.04, 0.10]
  },
  "fairness_table": [ { "group": "…", "n": 1059, "selection_rate": 0.45,
                        "selection_rate_ci": [0.42, 0.48],
                        "tpr": 0.52, "tpr_ci": [0.47, 0.57],
                        "fpr": 0.019, "low_sample": false } ],
  "guardrail": { "disparate_impact_floor": 0.8, "passed": true, "n_breaches": 0,
                 "breaches": [] },
  "mitigation_cost": {
    "cost_per_loan_delta": 0.0006, "approval_rate_delta": -0.004,
    "breaches_base": 1, "breaches_mitigated": 0,
    "note": "Measured on the policy tuning set (validation). The model card quotes the same intervention measured on the held-out test split."
  },
  "sweep": { "points": [ { "approve_max_pd": 0.02, "approval_rate": 0.18,
                           "disparate_impact_ratio": 0.71, "profit_per_loan": 1.2 } ] },
  "intercept": { "save_policy_allowed": true,
                 "reason": "Guardrail satisfied for the audited attribute.",
                 "floor": 0.8 }
}
```

The guardrail, the disparate-impact ratio and the fairness table all refer to the
**attribute under audit** (`mitigation_attribute`, defaulting to the registry's
chosen variant). **All of these figures are the policy tuning set (validation
split).** They are not the published test figures, which live in `/model` and the
model card, and they are expected to differ. The response says so explicitly via
`evaluation_set` / `evaluation_role`. When `apply_fairness` is on, the response also
carries `mitigation_cost`, the measured price of the intervention (cost per loan,
approval change, and how many attributes still breach) rather than only the ratio
it improved.

* `GET /portfolio` →
  `{n, set, role, row_key_prefix, group_attribute, attributes[], group_values{attribute: [labels]}, fields, note}`
  — the policy tuning set (validation split, `n` ≈ 6,483, scores stored verbatim).
* `POST /ab/compare` → `{alpha, beta, delta, labels}` (same portfolio, same policy;
  only the mitigation differs).
* `POST /bias/inject` → `{injection, clean, biased, recovered}`; the injected
  group must belong to the attribute under audit, otherwise `400`.
* `GET /drift/live?shift=1.5` → `{available, severity, max_psi, max_ks, features,
  alerts, adversarial_validation, simulated, window, thresholds}`.
  `available: false` with a `note` when no reference exists.
* `POST /alerts/test` → `{delivered, webhook_configured, payload, note}`.
* `GET /report.pdf` → `application/pdf`, `Content-Disposition: inline`.

## Privacy header

`PIIMaskingMiddleware` **removes** direct identifiers from JSON request bodies
(`name`, `email`, `ssn`, `card_number`, …) before routing. Keys are dropped
rather than replaced, so the request still validates against the strict applicant
schema and no derivative of the identifier reaches a handler — a salted digest is
kept in request state only, for the audit count. When it redacts anything, the
response carries:

```
x-pii-redactions: 2
```

Only bin indices and category codes are persisted for drift analysis — never raw
feature values.

## Errors

| Status | Meaning |
| --- | --- |
| 400 | Unknown region, unknown audited attribute, or unknown portfolio group |
| 404 | Unknown model version or job |
| 422 | Validation error (out-of-range or unknown field/category) |
| 429 | Rate limit exceeded |
| 503 | Model metadata or portfolio slice missing (run training) |
