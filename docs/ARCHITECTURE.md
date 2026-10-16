# Architecture

TrustScore is a small monorepo with a clean split between the offline ML
pipeline and the online decision service.

```
                    Browser: Applicant view | Lender view
                                  |
                              fetch (JSON)
                                  v
   web/  Next.js (React + TypeScript + Tailwind + Recharts)
                                  |
                       /api/*  (same origin on Vercel)
                                  v
   api/  FastAPI  --->  model.joblib  (preprocessor + LightGBM + calibration curve)
     |                    ^
     |                    |
     |             committed, versioned artifact
     |
     +--> anonymised prediction log  --->  Postgres (Supabase / Aiven / Neon / Render)
                                                  or SQLite locally

   OFFLINE (training/):  raw CSV -> clean -> features -> train -> calibrate
                         -> evaluate -> contribute (SHAP) -> fairness -> drift
                         -> export artifact + JSON reports -> commit
```

## Why the model and the decision are separate

The model answers one question: *what is the probability of default?* Everything
else — approve / refer / decline, cost, thresholds — is policy, owned by
`api/app/services/decision.py`. Changing the policy never means retraining the
model, and the policy is visible and tunable in the lender view.

## Single source of truth

Two pieces of logic are used by **both** training and serving, so they can never
drift:

| Logic | Module | Used by |
| --- | --- | --- |
| Feature schema, engineering, preprocessor | `api/app/core/features.py` | training + API |
| Cost matrix, thresholds, band decisions | `api/app/services/decision.py` | training + API |
| Reason vocabulary and mapping | `api/app/services/reasons.py` | training + API |
| Counterfactual search | `api/app/services/counterfactual.py` | training + API |

Training imports them by putting `api/` on `sys.path` (see
`training/src/__init__.py`), exactly as Vercel imports them.

## The artifact

`training/src/train.py` writes `api/artifacts/model.joblib`, a plain dict:

```python
{
  "preprocessor": TabularPreprocessor,   # NumPy + pandas only
  "booster":        lightgbm.Booster,    # native API
  "calibration":    {"x": [...], "y": [...]},  # isotonic curve
  "feature_names":  [...],
  "version":        "trustscore-1.0.0",
  "thresholds":     {...},
  "cost_matrix":    {...},
}
```

Deliberate choices:

* **No scikit-learn in production.** `TabularPreprocessor` reimplements the
  `ColumnTransformer(SimpleImputer + StandardScaler / OneHotEncoder)` layout in
  NumPy/pandas, and calibration is a stored isotonic curve applied with
  `numpy.interp`. This keeps the serverless bundle small and the cold start short
  (a named risk in the project plan).
* **No `shap` in production.** Contributions come from LightGBM's built-in
  `pred_contrib`. `shap` is only used offline, if at all.
* **Native `lightgbm.Booster`.** `LGBMClassifier` would pull scikit-learn in.

## Request path

```
POST /predict
  -> validate (Pydantic)
  -> TabularPreprocessor.transform
  -> booster.predict                (raw score)
  -> isotonic curve                 (calibrated PD)
  -> decision.decide(thresholds)    (band)
  -> db.log_prediction (best-effort, anonymised)
  -> response: PD, band, model version, prediction ID
```

`/explain` adds `booster.predict(pred_contrib=True)` and maps the contributions
through the reason vocabulary. `/decision` applies the cost-based policy.
`/counterfactual` runs the bounded greedy search over changeable features only.

## Deployment shapes

1. **Vercel (single project).** `vercel.json` builds `web/` with the Next.js
   builder and `api/index.py` as a Python function, routing `/api/*` to the
   function. `StripApiPrefix` middleware removes `/api` so the same route table
   resolves.
2. **Split (robust fallback).** The Next app on Vercel and the API as a Docker
   service on Render/Railway/Fly (`render.yaml`, `api/Dockerfile`). This removes
   any serverless bundle-size limit. The frontend points at the API via
   `NEXT_PUBLIC_API_BASE_URL`.
