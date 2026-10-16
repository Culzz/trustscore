# TrustScore

**An explainable and fairness-aware AI credit decisioning platform.**

An applicant fills a short form and gets a calibrated probability of default, a
plain-language explanation of *why*, a **simulated** decision, and feasible
changes that could improve their band. A lender/auditor gets the portfolio view:
calibration, a fairness audit, a decision-policy simulator and a model card.

> **Positioning.** A responsible-AI credit *decision simulation*. It is **not a
> real lending tool**, not a loan offer and not financial advice. Every decision
> is labelled *simulated*.

---

## Headline results

Trained and evaluated on the public **Kaggle Credit Risk Dataset** (32,416 rows
after cleaning, 21.9% default rate). Test split, stratified, seed 42.

| Model | ROC-AUC | PR-AUC | Brier | Precision | Recall |
| --- | --- | --- | --- | --- | --- |
| Logistic regression (baseline) | 0.8775 | 0.7294 | 0.1007 | 0.765 | 0.566 |
| LightGBM (uncalibrated) | 0.9495 | 0.9064 | 0.0527 | 0.957 | 0.731 |
| **LightGBM (calibrated)** | **0.9490** | **0.8984** | **0.0527** | 0.958 | 0.731 |

* Calibration: **Brier 0.0527**, **expected calibration error 0.0053** across 10 bins.
* Target exceeded: ROC-AUC ≥ 0.75 required, **0.949 achieved**.
* Cost-based bands chosen by minimising expected cost: **approve ≤ 0.055**,
  **decline ≥ 0.676** (`refer` between). Expected cost **0.0266** per unit of
  loan exposure. Approval rate on test: **45.3%** (2,936 approve / 2,536 refer /
  1,012 decline).
* The measured AUC is optimistic for a real credit setting — see
  [Limitations](#limitations).

## Figures

All figures are generated from the committed reports by `python scripts/figures.py`.

![Test-set performance](docs/figures/performance.png)

![Calibration](docs/figures/calibration.png)

![Score distribution](docs/figures/score_distribution.png)

![Fairness audit](docs/figures/fairness.png)

## Two views

* **Applicant view** (`/`) — a validated form (or one-click sample applicants),
  a risk gauge with the estimated band, top-5 plain-language reasons, a live
  what-if slider on the requested amount, and feasible counterfactual scenarios.
  No jargon, no raw scores.
* **Lender / auditor view** (`/lender`) — portfolio stats, live counters,
  the calibration curve, the score distribution, a fairness explorer, an
  input-drift (PSI) panel, and a decision-policy simulator that changes the
  thresholds and recomputes the band mix and expected cost.
* **Model Card** (`/model-card`) — intended use, data, performance, calibration,
  policy, influential features, fairness, and limitations, rendered live from
  `/model`.

UI screenshots and a short demo GIF are the last portfolio step: capture them
from the deployed URL once Vercel is connected.

---

## How it works

The model and the *decision* are deliberately separate:

1. **Retrieval-free scoring** — eleven applicant fields become a feature vector
   (a self-contained NumPy/pandas preprocessor; no scikit-learn at runtime).
2. **Calibrated PD** — LightGBM → isotonic calibration curve → a probability
   you can read directly as a default rate.
3. **Policy, not the model, decides** — a cost matrix turns PD into
   approve / refer / decline. Thresholds are configurable in the lender view.
4. **Explanations** — LightGBM `pred_contrib` values mapped to plain-language
   reasons. Applicants never see raw numbers.
5. **Counterfactuals** — a bounded greedy search over *changeable* features only
   (requested amount, loan purpose). Protected attributes are never suggested.
6. **Governance** — anonymised prediction logging, live counters, a fairness
   audit, an offline drift report and a model card.

Details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```
trustscore/
  web/        Next.js (React + TypeScript + Tailwind + Recharts) — two views
  api/        FastAPI service + the bundled, versioned model artifact
  training/   offline pipeline: clean -> train -> calibrate -> explain -> audit
  reports/    fairness, calibration, metrics, drift JSON + MODEL_CARD.md
  docs/       architecture, API, deployment
  data/       raw data (git-ignored; never committed)
  .github/    CI workflows
```

## Quickstart

```bash
# 1. API
cd api
python -m venv .venv && .venv\Scripts\activate        # or: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env.example .env                              # STORAGE_BACKEND=sqlite by default
uvicorn app.main:app --reload --port 8000

# 2. Web (new terminal)
cd web
npm install
copy .env.example .env.local
npm run dev        # http://localhost:3000
```

Or everything at once:

```bash
docker compose up --build
```

The model artifact is committed, so the API runs immediately. Retrain with:

```bash
pip install -r training/requirements.txt
python -m training.src.train
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/predict` | Calibrated PD, band, model version, prediction ID |
| POST | `/explain` | Top plain-language reasons |
| POST | `/decision` | Cost-based policy → approve / refer / decline (simulated) |
| POST | `/counterfactual` | Feasible changes to a better band |
| GET | `/model` | Model-card data: metrics, calibration, thresholds, fairness, drift |
| GET | `/health` | Service status |
| GET | `/stats` | Live anonymised counters |

Full contract in [`docs/API.md`](docs/API.md).

## Fairness

Audited on the held-out test split. **Statistical disparities exist**, and the
dashboard reports them rather than hiding them:

| Attribute | Selection-rate ratio | Demographic-parity gap | Equal-opportunity gap |
| --- | --- | --- | --- |
| Home ownership | 0.375 | 0.557 | 0.489 |
| Age band | 0.844 | 0.081 | 0.095 |
| Income band | 0.380 | 0.427 | 0.329 |
| Loan purpose | 0.546 | 0.304 | 0.301 |
| Prior default on file | 0.270 | 0.381 | 0.411 |

The dataset has **no gender, race or geography**, so those are reported as *not
available*, not estimated. These figures are statistical disparities, not a
legal compliance verdict — the Model Card says so explicitly.

## Deployment

Full-stack on **Vercel** (Next.js + FastAPI serverless + any Postgres), or split
(Next.js on Vercel, API on Render). Storage is provider-agnostic Postgres —
**Supabase** and **Aiven** both have free, no-card tiers — with a **SQLite**
mode for local use and a **disabled** mode that needs no database at all.

Step-by-step in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Limitations

* Trained on a public, non-African dataset. It demonstrates the system; it is not
  a production score for any real market.
* The dataset's loan grade and interest rate are lender-assigned fields that
  already encode an underwriting judgement, so the headline AUC is optimistic.
* Fairness is audited only for attributes present in the data; gender, race and
  geography are absent.
* Counterfactuals are model-generated scenarios, not guaranteed approval
  conditions.
* Monitoring is offline/simulated: the public dataset has no live outcome stream.
* Fairness figures are statistical disparities, not proof of legal compliance.

## Data

[Kaggle "Credit Risk Dataset"](https://www.kaggle.com/datasets/laotse/credit-risk-dataset)
(public). Raw data is **never committed** (`data/` is git-ignored). No real
personal data is used.

## Licence / attribution

Code: MIT-style demonstration project. Dataset: per its Kaggle licence.
