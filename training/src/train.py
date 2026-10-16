"""Train, calibrate, evaluate, explain and export TrustScore.

Run from the repository root::

    python -m training.src.train

Produces:
  * api/artifacts/model.joblib     -- the bundled production artifact
  * api/artifacts/metadata.json    -- model card data served by GET /model
  * reports/metrics_v1.json
  * reports/calibration_v1.json
  * reports/fairness_v1.json
  * reports/drift_v1.json
  * reports/model_card_v1.json
  * reports/MODEL_CARD.md

It uses native LightGBM (not LGBMClassifier) and a NumPy/pandas-only
preprocessor, so the served artifact needs neither scikit-learn nor SciPy.
scikit-learn is used here, offline, only for the logistic-regression baseline,
the split, isotonic calibration and the metrics.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

# Shared runtime logic (single source of truth).
from app.core.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TabularPreprocessor,
)
from app.services.counterfactual import find_counterfactuals
from app.services.decision import (
    APPROVE,
    DECLINE,
    REFER,
    CostMatrix,
    analytic_thresholds,
    decide_array,
    expected_cost,
    grid_thresholds,
    realized_cost,
)
from app.services.reasons import top_reasons

from . import config
from . import data as data_mod
from . import drift as drift_mod
from . import fairness as fair
from . import features as feat
from . import metrics as met
from . import modelcard as mc


def _log(message: str) -> None:
    print(f"[train] {message}", flush=True)


def _lgb_params() -> dict:
    return {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.03,
        "num_leaves": 31,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "min_data_in_leaf": 40,
        "lambda_l1": 0.1,
        "lambda_l2": 0.1,
        "verbosity": -1,
        "seed": config.SEED,
        "num_threads": 0,
    }


def _train_booster(X_train, y_train, X_val, y_val, num_boost_round=800):
    params = _lgb_params()
    dtrain = lgb.Dataset(X_train, label=y_train)
    dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=num_boost_round,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    return booster


def _fit_isotonic(X_train, y_train, params, rounds: int):
    """Cross-validated isotonic calibration, returned as plain arrays.

    This reproduces ``CalibratedClassifierCV(method="isotonic", cv=5)`` but keeps
    the result portable: the served model only needs the (x, y) curve.
    """
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.SEED)
    oof = np.zeros(len(y_train), dtype=float)
    for tr_idx, va_idx in kf.split(X_train, y_train):
        fold = lgb.train(
            params,
            lgb.Dataset(X_train[tr_idx], label=y_train[tr_idx]),
            num_boost_round=max(50, rounds),
        )
        oof[va_idx] = fold.predict(X_train[va_idx])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(oof, y_train)
    return iso.X_thresholds_.astype(float), iso.y_thresholds_.astype(float)


def _apply_calibration(raw: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.clip(np.interp(raw, x, y), 0.0, 1.0)


def main() -> None:
    started = time.time()
    trained_at = datetime.now(timezone.utc).isoformat()
    _log(f"TrustScore training — model version {config.MODEL_VERSION}")

    # ---------------------------------------------------------------- data
    raw = data_mod.load_raw()
    clean, clean_report = data_mod.clean(raw)
    clean = feat.engineer_features(clean)
    train, val, test = feat.stratified_split(clean, seed=config.SEED)
    _log(f"rows: raw={len(raw):,} cleaned={len(clean):,} "
         f"(train={len(train):,} val={len(val):,} test={len(test):,})")

    y_train = train[config.TARGET].to_numpy()
    y_val = val[config.TARGET].to_numpy()
    y_test = test[config.TARGET].to_numpy()

    # Audit-only groupings, with income cut points learned on train.
    train_audit, income_cutpoints = feat.add_audit_columns(train)
    val_audit, _ = feat.add_audit_columns(val, income_cutpoints)
    test_audit, _ = feat.add_audit_columns(test, income_cutpoints)

    # --------------------------------------------------------- preprocessor
    pre = TabularPreprocessor().fit(train)
    X_train = pre.transform(feat.feature_matrix(train))
    X_val = pre.transform(feat.feature_matrix(val))
    X_test = pre.transform(feat.feature_matrix(test))
    _log(f"features: {len(pre.feature_names_out)} transformed columns")

    # ------------------------------------------------------------- baseline
    _log("training logistic-regression baseline ...")
    lr = LogisticRegression(max_iter=2000, random_state=config.SEED)
    lr.fit(X_train, y_train)
    p_lr_val = lr.predict_proba(X_val)[:, 1]
    p_lr_test = lr.predict_proba(X_test)[:, 1]

    # --------------------------------------------------------------- lightgbm
    _log("training LightGBM ...")
    booster = _train_booster(X_train, y_train, X_val, y_val)
    best_rounds = booster.best_iteration or 400
    raw_val = booster.predict(X_val)
    raw_test = booster.predict(X_test)
    _log(f"LightGBM best iteration: {best_rounds}")

    # ------------------------------------------------------------- calibration
    _log("fitting cross-validated isotonic calibration ...")
    calib_x, calib_y = _fit_isotonic(X_train, y_train, _lgb_params(), best_rounds)
    p_cal_val = _apply_calibration(raw_val, calib_x, calib_y)
    p_cal_test = _apply_calibration(raw_test, calib_x, calib_y)

    # ---------------------------------------------------------------- metrics
    metrics = {
        "baseline_lr": met.classification_metrics(y_test, p_lr_test),
        "lightgbm": met.classification_metrics(y_test, raw_test),
        "calibrated": met.classification_metrics(y_test, p_cal_test),
    }
    _log(f"test ROC-AUC: lr={metrics['baseline_lr']['roc_auc']:.4f} "
         f"lgbm={metrics['lightgbm']['roc_auc']:.4f} "
         f"calibrated={metrics['calibrated']['roc_auc']:.4f}")

    # ------------------------------------------------------------ calibration report
    cal_report = met.calibration_curve_data(y_test, p_cal_test)
    cal_report["brier"] = metrics["calibrated"]["brier"]

    # ------------------------------------------------------------ thresholds
    costs = CostMatrix(
        false_approve=config.COST_FALSE_APPROVE,
        false_decline=config.COST_FALSE_DECLINE,
        review=config.COST_REVIEW,
    )
    ta_analytic, td_analytic = analytic_thresholds(costs)
    val_amounts = val["loan_amnt"].to_numpy(dtype=float)
    ta_grid, td_grid, ec_per_loan = grid_thresholds(p_cal_val, val_amounts, costs)
    approve_max_pd, decline_min_pd = ta_grid, td_grid
    _log(f"thresholds: approve<= {approve_max_pd:.3f}, decline>= {decline_min_pd:.3f} "
         f"(analytic {ta_analytic:.3f}/{td_analytic:.3f})")

    decisions_test = decide_array(p_cal_test, approve_max_pd, decline_min_pd)
    test_amounts = test["loan_amnt"].to_numpy(dtype=float)
    realized = realized_cost(y_test, test_amounts, decisions_test, costs)
    expected = expected_cost(p_cal_test, test_amounts, decisions_test, costs)
    band_counts = pd.Series(decisions_test).value_counts().to_dict()
    approval_rate = float((decisions_test == APPROVE).mean())
    _log(f"test approval rate {approval_rate:.3f}; bands {band_counts}")

    thresholds_block = {
        "approve_max_pd": float(approve_max_pd),
        "decline_min_pd": float(decline_min_pd),
        "analytic_approve_max_pd": float(ta_analytic),
        "analytic_decline_min_pd": float(td_analytic),
        "cost_matrix": costs.as_dict(),
        "expected_cost_per_loan": float(ec_per_loan),
        "test_realized_cost_per_loan": float(realized / max(test_amounts.sum(), 1.0)),
        "test_expected_cost_per_loan": float(expected / max(test_amounts.sum(), 1.0)),
        "test_approval_rate": approval_rate,
        "test_band_counts": {k: int(v) for k, v in band_counts.items()},
    }

    # ---------------------------------------------------------------- fairness
    _log("computing fairness audit ...")
    fairness_report = fair.compute_fairness(
        test_audit, y_test, p_cal_test, decisions_test, config.MODEL_VERSION
    )

    # ------------------------------------------------------------ top features
    contribs = np.asarray(booster.predict(X_test, pred_contrib=True))
    mean_abs = np.abs(contribs[:, :-1]).mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    top_features = [
        {"feature": pre.feature_names_out[i], "mean_abs_contribution": float(mean_abs[i])}
        for i in order[:12]
    ]

    # ---------------------------------------------------- score distribution
    # A small histogram of out-of-sample PDs. The lender dashboard uses it to
    # move thresholds and watch approval rate / expected cost update, with no
    # live database needed.
    def _pd_histogram(p: np.ndarray, amounts: np.ndarray, bins: int = 40) -> list[dict]:
        edges = np.linspace(0.0, 1.0, bins + 1)
        idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
        out = []
        for b in range(bins):
            m = idx == b
            if not m.any():
                continue
            out.append(
                {
                    "pd": float((edges[b] + edges[b + 1]) / 2.0),
                    "count": int(m.sum()),
                    "mean_exposure": float(amounts[m].mean()),
                }
            )
        return out

    pd_hist = _pd_histogram(p_cal_test, test_amounts)

    # -------------------------------------------------- counterfactual sanity
    def predict_fn(row_dict: dict) -> float:
        frame = feat.engineer_features(pd.DataFrame([row_dict]))
        raw_score = float(booster.predict(pre.transform(feat.feature_matrix(frame)))[0])
        return float(_apply_calibration(np.array([raw_score]), calib_x, calib_y)[0])

    decline_idx = np.where(decisions_test == DECLINE)[0][:5]
    cf_examples = []
    for i in decline_idx:
        row = {c: test.iloc[int(i)][c] for c in feat.MODEL_FEATURES if c in test.columns}
        scenarios = find_counterfactuals(
            raw_row=row,
            predict_fn=predict_fn,
            approve_max_pd=approve_max_pd,
            decline_min_pd=decline_min_pd,
            current_pd=float(p_cal_test[int(i)]),
            max_scenarios=3,
        )
        cf_examples.append({"row_index": int(i), "scenarios": scenarios})
    _log(f"counterfactual sanity: {sum(len(c['scenarios']) for c in cf_examples)} "
         f"scenarios over {len(decline_idx)} declined applicants")

    # ------------------------------------------------------------------ drift
    drift_report = drift_mod.build_drift_report(train, test, config.MODEL_VERSION)

    # --------------------------------------------------------------- artifact
    artifact = {
        "preprocessor": pre,
        "booster": booster,
        "calibration": {"x": calib_x.tolist(), "y": calib_y.tolist()},
        "feature_names": pre.feature_names_out,
        "version": config.MODEL_VERSION,
        "seed": config.SEED,
        "trained_at": trained_at,
        "thresholds": {
            "approve_max_pd": float(approve_max_pd),
            "decline_min_pd": float(decline_min_pd),
        },
        "cost_matrix": costs.as_dict(),
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
    }
    config.API_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, config.MODEL_ARTIFACT)
    _log(f"wrote {config.MODEL_ARTIFACT}")

    # ------------------------------------------------------------ metadata
    dataset_block = {
        "name": "Kaggle Credit Risk Dataset (laotse)",
        "source": "https://www.kaggle.com/datasets/laotse/credit-risk-dataset",
        "rows": int(len(clean)),
        "rows_in": int(len(raw)),
        "target_rate": float(clean[config.TARGET].mean()),
        "split_sizes": {
            "train": int(len(train)),
            "validation": int(len(val)),
            "test": int(len(test)),
        },
        "features": list(MODEL_FEATURES),
        "seed": config.SEED,
        "clean_report": clean_report.as_dict(),
    }

    metadata = {
        "version": config.MODEL_VERSION,
        "trained_at": trained_at,
        "disclaimer": mc.DISCLAIMER,
        "dataset": dataset_block,
        "metrics": metrics,
        "calibration": {
            "brier": cal_report.get("brier"),
            "ece": cal_report.get("ece"),
            "n_bins": cal_report.get("n_bins"),
            "curve": cal_report.get("bins"),
        },
        "thresholds": thresholds_block,
        "fairness": fairness_report,
        "top_features": top_features,
        "score_distribution": {
            "bins": pd_hist,
            "n": int(len(p_cal_test)),
            "mean_pd": float(p_cal_test.mean()),
        },
        "policy_simulation": {
            "bins": pd_hist,
            "n": int(len(p_cal_test)),
        },
        "metric_definitions": {
            "roc_auc": "Ranking quality (0.5 = random, 1.0 = perfect).",
            "pr_auc": "Average precision; more informative than ROC-AUC when defaults are rare.",
            "brier": "Mean squared error of the predicted probabilities; lower is better.",
            "ece": "Expected calibration error across 10 probability bins; lower is better.",
            "selection_rate": "Share of a group that is approved.",
            "tpr": "P(approved | repaid) — approval rate among the creditworthy.",
            "fpr": "P(approved | defaulted).",
        },
        "limitations": mc.LIMITATIONS,
        "drift": drift_report,
    }
    config.METADATA_JSON.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _log(f"wrote {config.METADATA_JSON}")

    # ---------------------------------------------------------------- reports
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.METRICS_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    config.CALIBRATION_JSON.write_text(json.dumps(cal_report, indent=2), encoding="utf-8")
    config.FAIRNESS_JSON.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")
    config.DRIFT_JSON.write_text(json.dumps(drift_report, indent=2), encoding="utf-8")

    context = {
        "version": config.MODEL_VERSION,
        "trained_at": trained_at,
        "dataset": dataset_block,
        "metrics": metrics,
        "thresholds": thresholds_block,
        "calibration": {"brier": cal_report.get("brier"), "ece": cal_report.get("ece")},
        "fairness": fairness_report,
        "top_features": top_features,
    }
    mc.write_model_card(context, config.MODEL_CARD_MD, config.MODEL_CARD_JSON)
    _log(f"wrote {config.MODEL_CARD_MD}")

    _log(f"done in {time.time() - started:.1f}s")
    _log(f"headline: ROC-AUC={metrics['calibrated']['roc_auc']:.4f} "
         f"Brier={metrics['calibrated']['brier']:.4f} ECE={cal_report.get('ece'):.4f}")


if __name__ == "__main__":
    main()
