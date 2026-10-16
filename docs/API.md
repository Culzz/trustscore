# API

Base URL:

* local: `http://localhost:8000`
* Vercel: `https://<your-app>.vercel.app/api`

Interactive docs (OpenAPI) are served at `/docs` when `ENABLE_DOCS=true`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/predict` | Calibrated probability of default, band, model version, prediction ID |
| POST | `/explain` | Top plain-language reasons (up/down risk) |
| POST | `/decision` | Apply the cost-based policy → approve / refer / decline (simulated) |
| POST | `/counterfactual` | Feasible changes that could move the applicant to a better band |
| GET | `/model` | Model-card data: version, metrics, calibration, thresholds, fairness, drift |
| GET | `/health` | Service status |
| GET | `/stats` | Live anonymised counters (volume, mean PD, high-risk share) |

### Applicant payload

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
  "thresholds": { "approve_max_pd": 0.055, "decline_min_pd": 0.676 },
  "created_at": "…",
  "disclaimer": "…"
}
```

### `/decision` policy override

The lender view can explore thresholds without retraining:

```json
{
  "applicant": { "...": "..." },
  "approve_max_pd": 0.08,
  "decline_min_pd": 0.55
}
```

### Errors

| Status | Meaning |
| --- | --- |
| 422 | Validation error (out-of-range or unknown field/category) |
| 429 | Rate limit exceeded |
| 503 | Model metadata missing (run training) |
