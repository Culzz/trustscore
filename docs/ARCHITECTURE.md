# Architecture

TrustScore is a small monorepo with a clean split between the offline ML
pipeline and the online decision service.

```
        Browser: Applicant view (light)  |  Auditor console (dark)
                            |
                        fetch (JSON) / WebSocket
                            v
   web/  Next.js (React + TypeScript + Tailwind + Recharts)
        ModeProvider -> AppShell (persona toggle + simulation watermark)
                            |
                 /api/*  (same origin on Vercel)
                            v
   api/  FastAPI  --->  model.joblib / model_fair.joblib
     |   |                 (preprocessor + LightGBM + calibration curve)
     |   |                    ^
     |   |                    |
     |   |            committed, versioned artifacts + registry.json
     |   |
     |   +--> job bus (in-process asyncio, or Celery + Redis)
     |   |        \-> WS /ws/jobs/{id}  (polling fallback on Vercel)
     |   |
     |   +--> anonymised prediction log + binned feature summary
     |            \-->  Postgres (Supabase / Aiven / Neon / Render)
     |                  or SQLite locally, or disabled
     |
     +--> audit services: portfolio.json, reference.json, registry.json
             (policy sim, A/B, bias injector, PSI/KS drift, ReportLab PDF)

  OFFLINE (training/): raw CSV -> clean -> features
                       -> split 60/20/20 (train / validation / test)
                       -> train booster + cross-fitted isotonic calibration on train
                       -> analytic cost thresholds, grid-verified on validation
                       -> one-time evaluation on test
                       -> fairness audit + equalized-odds mitigation (fit on train)
                       -> ablation + out-of-population stress test
                       -> drift reference -> audit portfolio (validation = tuning set)
                       -> registry
                       -> model card + evaluation report -> export artifacts + reports
```

The three-way protocol is the point of that pipeline. Fitting, policy tuning and
final reporting happen on **different** rows, so no reported number is a fit to
itself. See [`docs/EVALUATION.md`](EVALUATION.md).

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
| Equalized-odds engine | `api/app/services/mitigation.py` | training + API |
| PSI/KS drift statistics | `api/app/services/psi.py` | training + API |
| Portfolio policy simulation | `api/app/services/portfolio.py` | API routes (audit console) |
| Model registry reader | `api/app/core/registry.py` | training + API |
| Shared scoring pipeline | `api/app/services/pipeline.py` | API routes |

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

All of the scoring routes share one implementation,
`services/pipeline.py:score_row`, so `/predict`, `/decision`, `/blueprint` and the
asynchronous `/apply` can never disagree about a band.

## Asynchronous application flow

`POST /apply` returns `202` immediately. The work runs through
`services/apply_flow.py:run_application`, which emits milestones
(`validated → scored → explained → recourse → complete`) into a job bus:

| Backend | When | Streaming |
| --- | --- | --- |
| `memory` | default, and the Vercel default | in-process `asyncio` task; `WS /ws/jobs/{id}` relays live |
| `celery` | `CELERY_BROKER_URL` or `REDIS_URL` set | Celery worker publishes to Redis pub/sub; the API relays |

`JOB_BACKEND=auto` picks between them. Both paths call the **same**
`run_application`, so the events are identical and there is no second code path
to keep in sync.

Serverless functions cannot hold a WebSocket open, so the frontend
(`web/lib/api.ts:watchJob`) attempts the socket, then degrades to polling
`GET /jobs/{id}`. The applicant UI is written against the event stream, not the
transport.

Recourse plans and narratives are cached by feature hash
(`services/cache.py`), because the counterfactual search calls the model many
times for a single application.

## Fairness mitigation

`training/src/train.py` fits an **equalized-odds post-processor** on the
validation split for every derivable attribute (`age_band`,
`person_home_ownership`, `loan_intent`, `income_band`) using
`api/app/services/mitigation.py`. The parameters (per-group strict/permissive
thresholds and mixing weights) are stored inside the `trustscore-1.1.0`
artifact.

At serving time `services/pipeline.py` applies them when
`apply_fairness=true`, and the response always reports whether the decision
changed. The registry records the measured impact of each variant, and the
default is chosen by *fewest guardrail breaches, then largest disparate-impact
gain* — not by hand.

The honest caveat, repeated in the UI: equalized odds targets true/false-positive
parity on **one** attribute, so mitigation improves fairness substantially without
making the model compliant. Three guardrail breaches remain in the default
configuration.

## Privacy gateway

`middleware/pii.py` is a pure-ASGI middleware. For JSON bodies it walks the
document and **removes** any key that looks like a direct identifier
(`name`, `email`, `ssn`, `card_number`, …), then replays the rewritten body
downstream. Keys are dropped rather than replaced, so the request still validates
against the strict applicant schema and nothing derived from the identifier
reaches a handler; a salted SHA-256 digest is recorded in request state only, for
the audit count. It forwards the redaction count in the `x-pii-redactions`
header, so the behaviour is observable and testable rather than silent.

For drift analysis, only **bin indices and category codes** are persisted
(`db.log_prediction_features`) — never raw feature values. That makes
"monitor the input distribution" and "do not retain applicant data" compatible.

## Drift and adversarial monitoring

`services/drift_monitor.py` compares recent traffic against
`artifacts/reference.json` (the training distribution) using PSI, plus KS where a
reference sample exists. A cheap adversarial-validation proxy — a single-feature
separability score, not a trained classifier — flags covariate shift.

If a database is configured the panel reads real logged traffic. If not (the
Vercel default), it runs a clearly-labelled synthetic window and says so
(`simulated: true`, `storage_enabled: false`). It never pretends to have data it
does not have.

## Compliance report

`services/report_pdf.py` builds the PDF with **ReportLab**, drawing the
reliability curve from ReportLab primitives. This keeps `matplotlib` out of the
runtime bundle entirely: it is an offline-only dependency of
`scripts/figures.py`.

## Deliberate deviations

Recording these matters more than hiding them:

* **Macro feature store is seeded, not live.** `services/feature_store.py`
  contains an honest mock with a `note` field saying so. Its context is shown to
  applicants and can tilt a cut-off for the policy lab, but it is **not** an
  input to the model, so a score is always reproducible from the eleven
  applicant fields alone.
* **Narration is template-based, not an LLM call.** Reason codes come from
  deterministic templates in `services/narrative.py` behind a denylist +
  length guardrail. No external API key, no nondeterminism, and the guardrail
  result is reported in the response.
* **Lineage lives in `registry.json`**, written by the training pipeline,
  deliberately avoiding an MLflow dependency.
* **A/B is two artifacts, not two live traffic splits.** Alpha vs Beta is scored
  on the same portfolio at the same policy, which isolates the effect of
  mitigation.
* **The audit console runs on the policy tuning set, not the final test set.**
  `portfolio.json` is the public **validation** split (n = 6,483, key prefix
  `tuning`), with calibrated scores stored verbatim and deterministic tie-break
  keys. The row-level test split is never shipped, so the final evaluation cannot
  be inspected and re-tuned interactively by accident. Two consequences: the
  console can exercise the four-fifths guardrail for **any** audited attribute
  rather than one pre-sliced grouping, and its figures are **expected to differ**
  from the model card (which reports the one-time test evaluation). Every surface
  that shows a tuning-set number labels it as such, and the numbers themselves
  carry the provenance (`evaluation_protocol` in `metadata.json` and
  `registry.json`).
* **Fairness mitigation is fitted on train, scored on validation and test.** The
  equalized-odds rule is fitted on out-of-fold training predictions, so both the
  console's improvement and the card's improvement are out-of-sample. The
  console also reports what the intervention **cost** (realized cost per loan,
  approval-rate change, and how many attributes still breach), not just the ratio
  it improved.
* **Trustee note.** `GET /model`'s `fairness.guardrail` is the *global* check
  (every audited attribute at once, four breaches on this model), while
  `/policy/simulate` reports the guardrail for the **selected** attribute. Both
  are correct; they answer different questions.

## Deployment shapes

1. **Vercel (single project).** `vercel.json` builds `web/` with the Next.js
   builder and `api/index.py` as a Python function, routing `/api/*` to the
   function. `StripApiPrefix` middleware removes `/api` so the same route table
   resolves. Jobs run in-process (`memory`) and progress degrades to polling.
2. **Split (robust fallback).** The Next app on Vercel and the API as a Docker
   service on Render/Railway/Fly (`render.yaml`, `api/Dockerfile`). This removes
   any serverless bundle-size limit, and the long-lived process means WebSocket
   progress works. The frontend points at the API via
   `NEXT_PUBLIC_API_BASE_URL`.
3. **Docker Compose, with real workers.** `docker compose --profile async up`
   starts the API, Redis and a Celery worker
   (`app.worker.celery_app`). `JOB_BACKEND` resolves to `celery` because the
   broker URL is set.

## Frontend structure

```
web/app/
  layout.tsx        ModeProvider -> AppShell (wraps every page)
  page.tsx          applicant flow (async /apply, progressive disclosure)
  auditor/page.tsx  dark governance console
  model-card/page.tsx
web/components/
  mode-provider.tsx  persona context (persisted)
  app-shell.tsx      header, banner, mode toggle, watermark, footer
  progress-steps.tsx, blueprint-card.tsx, notice-card.tsx,
  risk-disclosure.tsx, whatif-sandbox.tsx            (# applicant)
  policy-lab.tsx, ab-compare-grid.tsx, bias-injector.tsx,
  drift-alert.tsx, lineage-timeline.tsx,
  compliance-report-button.tsx                       (# auditor)
```

The shell is the single place that knows about personas; pages only declare
which persona they belong to on mount. The simulation watermark lives in the
shell, so it cannot be scrolled away or omitted from a new page.
