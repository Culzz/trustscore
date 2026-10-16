# Training pipeline

Offline only. Nothing here ships to the API runtime — the output is a small,
versioned artifact plus JSON reports that are committed to the repo.

```bash
pip install -r requirements.txt
python -m training.src.train          # from the repo root
```

Runtime: a few minutes on a laptop. Fixed seed (`SEED = 42`) throughout, so the
split, the model and every reported number are reproducible.

## Stages

```
training/src/
  config.py    paths, model version, seed, target, feature lists
  data.py      load -> clean -> stratified train/val/test split
  features.py  thin wrapper over api/app/core/features.py (shared schema)
  train.py     orchestrator: baseline, LightGBM, calibration, thresholds,
               reasons, fairness, drift, model card, artifact export
  metrics.py   ROC-AUC, PR-AUC, Brier, precision/recall/F1, calibration curve/ECE
  fairness.py  group metrics + selection-rate ratio / parity gaps
  drift.py     population stability index vs a reference split
  modelcard.py writes reports/MODEL_CARD.md
```

## What each phase produces

| Phase | Output |
| --- | --- |
| 1. Baseline | Logistic regression + LightGBM compared on ROC-AUC / PR-AUC |
| 2. Evaluation & calibration | Calibrated PU the calibration curve, Brier, ECE; cost-based thresholds |
| 3. Explainability | Feature → plain-language reason map (`api/app/data/reason_map.json`) |
| 4. Fairness & model card | `reports/fairness_v1.json`, `reports/MODEL_CARD.md` |
| 7. Monitoring | `reports/drift_v1.json` (PSI per feature) |

## Artifacts written

```
api/artifacts/model.joblib     preprocessor + LightGBM + isotonic curve
api/artifacts/metadata.json    everything the /model endpoint serves
reports/metrics_v1.json
reports/calibration_v1.json
reports/fairness_v1.json
reports/drift_v1.json
reports/model_card_v1.json
reports/MODEL_CARD.md
```

The artifact and reports are **committed** so the API runs with no data present.

## Deliberate deviations from the original plan

These are choices, not omissions — each is recorded here so the reasoning is
auditable.

* **Dataset.** The plan named Home Credit. It requires Kaggle competition access
  and is very large. The build uses the public, self-contained **Credit Risk
  Dataset** (`laotse`), which has the same modelling shape (tabular, binary
  default target) and a fraction of the weight. The UI and Model Card say so
  plainly.
* **No scikit-learn in production.** The preprocessor is reimplemented in
  NumPy/pandas and calibration is a stored isotonic curve, so the served artifact
  needs no scikit-learn, SciPy or shap. This directly mitigates the Vercel bundle
  and cold-start risk.
* **Fairness instead of `fairlearn`.** The audit is a small, explicit
  implementation (approval rate, TPR, FPR, precision, selection-rate ratio,
  parity gaps) so every metric is inspectable and there is no extra runtime
  dependency.
* **Drift instead of `Evidently`.** PSI per feature, computed against the
  training split, written to JSON. Lighter and deterministic.
* **No MLflow server.** The committed artifact + JSON reports serve the same
  "versioned experiment record" purpose. `mlflow` stays optional in
  `requirements.txt`; the pipeline does not import it.
