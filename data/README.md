# Data

This directory is **not committed**. It holds the raw and derived datasets used
for training. The trained artifact and the JSON reports **are** committed, so the
API runs without any data present.

## Getting the dataset

TrustScore trains on the public Kaggle **Credit Risk Dataset** by `laotse`:

* https://www.kaggle.com/datasets/laotse/credit-risk-dataset

Download `credit_risk_dataset.csv` (32,581 rows) and place it here:

```
data/raw/credit_risk_dataset.csv
```

Via the Kaggle CLI:

```bash
pip install kaggle           # requires ~/.kaggle/kaggle.json
kaggle datasets download -d laotse/credit-risk-dataset -p data/raw --unzip
```

## Schema

| Column | Type | Notes |
| --- | --- | --- |
| `person_age` | int | Age in years |
| `person_income` | int | Annual income |
| `person_home_ownership` | category | RENT / OWN / MORTGAGE / OTHER |
| `person_emp_length` | float | May be missing |
| `loan_intent` | category | Purpose of the loan |
| `loan_grade` | category | A–G, lender-assigned |
| `loan_amnt` | int | Requested amount |
| `loan_int_rate` | float | May be missing (grades F/G) |
| `loan_status` | int | **Target**: 1 = default, 0 = repaid |
| `loan_percent_income` | float | Derived; recreated as `loan_amnt / person_income` |
| `cb_person_default_on_file` | category | Y / N |
| `cb_person_cred_hist_length` | int | Years of credit history |

`loan_percent_income` is **not** an API input; it is derived so results are
reproducible.

## Retraining

```bash
pip install -r training/requirements.txt
python -m training.src.train
```

This rewrites `api/artifacts/*` and the `reports/*.json` files, plus
`reports/MODEL_CARD.md` and `reports/EVALUATION.md`. The split is a three-way
fit / tune / report partition; the validation slice is what ships as the audit
*policy tuning set* (`api/artifacts/portfolio.json`) and the test slice is never
shipped. See [`docs/EVALUATION.md`](../docs/EVALUATION.md).

> Licence note. The dataset is distributed under its own Kaggle licence and is
> **not** included in this repository. TrustScore's code is MIT (see the root
> [`LICENSE`](../LICENSE)); this project is a demonstration and is not a real
> lending tool.
