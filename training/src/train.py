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
    PORTFOLIO_KEY_PREFIX,
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
from app.services.mitigation import (
    apply_equalized_odds,
    fit_equalized_odds,
    group_labels,
    summarise as summarise_mitigation,
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

    # -------------------------------------------------------------- mitigation
    # Fit the equalized-odds post-processor on the *validation* split (never on
    # test) for every derivable group attribute, then measure each on the
    # held-out test split. This is the "Beta" model: same booster, a
    # fairness-aware decision rule on top.
    _log("fitting equalized-odds post-processing ...")
    test_keys = [f"{PORTFOLIO_KEY_PREFIX}:{i}" for i in range(len(test))]

    def _groups(frame, attribute: str):
        return frame[attribute].astype("string").fillna("unknown").tolist()

    def _mitigated_decisions(attribute: str, params: dict) -> np.ndarray:
        approved_m = apply_equalized_odds(
            p_cal_test, _groups(test_audit, attribute), params, keys=test_keys
        )
        return np.where(
            approved_m & (decisions_test != APPROVE),
            APPROVE,
            np.where((~approved_m) & (decisions_test == APPROVE), REFER, decisions_test),
        )

    def _attr_summary(report: dict, attribute: str) -> dict:
        block = report.get("attributes", {}).get(attribute, {})
        return block.get("summary", {}) or {}

    variants: dict = {}
    variant_fairness: dict = {}
    for attribute in config.MITIGATION_VARIANTS:
        if attribute not in val_audit.columns or attribute not in test_audit.columns:
            continue
        params = fit_equalized_odds(
            y=y_val,
            p=p_cal_val,
            groups=_groups(val_audit, attribute),
            base_threshold=approve_max_pd,
            min_group_size=config.MITIGATION_MIN_GROUP_SIZE,
            attribute=attribute,
        )
        decisions_m = _mitigated_decisions(attribute, params)
        fairness_m = fair.compute_fairness(
            test_audit, y_test, p_cal_test, decisions_m, config.FAIR_MODEL_VERSION
        )
        realized_m = realized_cost(y_test, test_amounts, decisions_m, costs)
        s_base = _attr_summary(fairness_report, attribute)
        s_mit = _attr_summary(fairness_m, attribute)
        di_base = s_base.get("disparate_impact_ratio")
        di_mit = s_mit.get("disparate_impact_ratio")
        variants[attribute] = {
            "params": params,
            "summary": summarise_mitigation(params),
            "impact": {
                "attribute": attribute,
                "approval_rate_base": float((decisions_test == APPROVE).mean()),
                "approval_rate_mitigated": float((decisions_m == APPROVE).mean()),
                "realized_cost_per_loan_base": float(realized / max(test_amounts.sum(), 1.0)),
                "realized_cost_per_loan_mitigated": float(
                    realized_m / max(test_amounts.sum(), 1.0)
                ),
                "disparate_impact_ratio_base": di_base,
                "disparate_impact_ratio_mitigated": di_mit,
                "equalized_odds_difference_base": s_base.get("equalized_odds_difference"),
                "equalized_odds_difference_mitigated": s_mit.get("equalized_odds_difference"),
                "n_breaches_base": fairness_report["guardrail"]["n_breaches"],
                "n_breaches_mitigated": fairness_m["guardrail"]["n_breaches"],
                "disparate_impact_gain": (
                    (di_mit - di_base) if (di_mit is not None and di_base is not None) else None
                ),
            },
            "guardrail": fairness_m["guardrail"],
        }
        variant_fairness[attribute] = fairness_m

    # Pick the variant that removes the most breaches, then improves DI the most.
    def _rank(attribute: str):
        imp = variants[attribute]["impact"]
        return (imp["n_breaches_mitigated"], -(imp["disparate_impact_gain"] or 0.0))

    default_attribute = (
        sorted(variants, key=_rank)[0] if variants else config.MITIGATION_ATTRIBUTE
    )
    default_variant = variants[default_attribute]
    mitigation_params = default_variant["params"]
    fairness_mitigated = variant_fairness[default_attribute]
    mitigation_block = {
        "method": "equalized_odds",
        "attribute": default_attribute,
        "base_threshold": float(approve_max_pd),
        "target_tpr": mitigation_params["target_tpr"],
        "target_fpr": mitigation_params["target_fpr"],
        "min_group_size": config.MITIGATION_MIN_GROUP_SIZE,
        "params": mitigation_params,
        "variants": variants,
    }
    mitigation_impact = default_variant["impact"]
    for attribute, block in variants.items():
        imp = block["impact"]
        _log(
            f"  {attribute:24s} breaches {imp['n_breaches_base']} -> "
            f"{imp['n_breaches_mitigated']}; DI {imp['disparate_impact_ratio_base']} -> "
            f"{imp['disparate_impact_ratio_mitigated']}"
        )
    _log(f"mitigation default attribute: {default_attribute}")

    # --------------------------------------------------------------- portfolio
    # The full test split, so the audit console's guardrail, A/B comparison and
    # bias injector report exactly the same figures as the model card (a sample
    # would drift the disparate-impact ratio across the four-fifths floor). Every
    # audited attribute is carried as an integer code plus a shared ``levels``
    # table, so mitigation, A/B and the bias injector can all target any of them.
    #
    # Scores are stored verbatim (JSON round-trips a float exactly). Rounding --
    # even to 8 decimals -- was enough to flip a handful of decisions where the
    # equalized-odds cut-offs sit in the dense part of the score distribution, and
    # that moved the live disparate-impact ratio away from the offline value.
    # Exposure is rounded to the nearest $100. This is public demo data, not PII.
    port_idx = np.arange(len(test))

    portfolio_attributes = [
        a
        for a in [config.MITIGATION_ATTRIBUTE, *config.MITIGATION_VARIANTS]
        if a in test_audit.columns
    ]
    # de-duplicate while preserving order
    portfolio_attributes = list(dict.fromkeys(portfolio_attributes))

    group_lists = {a: _groups(test_audit, a) for a in portfolio_attributes}
    levels = {
        a: sorted({group_lists[a][int(i)] for i in port_idx})
        for a in portfolio_attributes
    }
    code_of = {a: {label: k for k, label in enumerate(levels[a])} for a in portfolio_attributes}

    portfolio_rows = [
        [
            float(p_cal_test[i]),
            round(float(test_amounts[i]) / 100.0) * 100.0,
            int(y_test[i]),
            [code_of[a][group_lists[a][int(i)]] for a in portfolio_attributes],
        ]
        for i in port_idx
    ]
    portfolio = {
        "version": config.MODEL_VERSION,
        "n": len(portfolio_rows),
        "group_attribute": config.MITIGATION_ATTRIBUTE
        if config.MITIGATION_ATTRIBUTE in portfolio_attributes
        else portfolio_attributes[0],
        "attributes": portfolio_attributes,
        "levels": levels,
        "group_values": levels,
        "fields": ["pd", "exposure", "y", "codes"],
        "row_key_prefix": PORTFOLIO_KEY_PREFIX,
        "rows": portfolio_rows,
        "note": (
            "Rows from the public test split: calibrated scores verbatim, exposure "
            "rounded to the nearest 100. Used only for simulated portfolio "
            "analytics; contains no personal data."
        ),
    }

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
        "guardrail": fairness_report["guardrail"],
        "mitigation_available": {
            "method": "equalized_odds",
            "attribute": default_attribute,
            "attributes": list(variants.keys()),
            "model_version": config.FAIR_MODEL_VERSION,
            "variants": {
                attribute: variants[attribute]["impact"] for attribute in variants
            },
        },
    }
    config.METADATA_JSON.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _log(f"wrote {config.METADATA_JSON}")

    # ------------------------------------------- Beta artifact (fairness-tuned)
    # Same booster, a different decision rule. A distinct artifact so the two
    # models can be A/B compared and the mitigation can be toggled.
    fair_artifact = dict(artifact)
    fair_artifact["version"] = config.FAIR_MODEL_VERSION
    fair_artifact["base_version"] = config.MODEL_VERSION
    fair_artifact["mitigation"] = mitigation_block
    joblib.dump(fair_artifact, config.MODEL_FAIR_ARTIFACT)
    _log(f"wrote {config.MODEL_FAIR_ARTIFACT}")

    metadata_fair = dict(metadata)
    metadata_fair["version"] = config.FAIR_MODEL_VERSION
    metadata_fair["base_version"] = config.MODEL_VERSION
    metadata_fair["fairness"] = fairness_mitigated
    metadata_fair["mitigation"] = mitigation_block
    metadata_fair["mitigation_impact"] = mitigation_impact
    config.METADATA_FAIR_JSON.write_text(
        json.dumps(metadata_fair, indent=2), encoding="utf-8"
    )
    _log(f"wrote {config.METADATA_FAIR_JSON}")

    # ------------------------------------------------------- reference + registry
    reference = drift_mod.build_reference_distributions(train)
    config.REFERENCE_DIST_JSON.write_text(json.dumps(reference, indent=2), encoding="utf-8")
    _log(f"wrote {config.REFERENCE_DIST_JSON}")

    config.PORTFOLIO_JSON.write_text(json.dumps(portfolio), encoding="utf-8")
    _log(f"wrote {config.PORTFOLIO_JSON}")

    def _model_entry(
        version, label, role, artifact_name, metadata_name, fairness, mitigation,
        attribute=config.MITIGATION_ATTRIBUTE,
    ):
        attr_summary = (fairness.get("attributes", {}).get(attribute, {}) or {}).get(
            "summary", {}
        )
        return {
            "version": version,
            "label": label,
            "role": role,
            "artifact": artifact_name,
            "metadata": metadata_name,
            "trained_at": trained_at,
            "metrics": {
                "roc_auc": metrics["calibrated"].get("roc_auc"),
                "pr_auc": metrics["calibrated"].get("pr_auc"),
                "brier": metrics["calibrated"].get("brier"),
                "ece": cal_report.get("ece"),
            },
            "thresholds": {
                "approve_max_pd": float(approve_max_pd),
                "decline_min_pd": float(decline_min_pd),
            },
            "fairness": {
                "disparate_impact_floor": fairness.get("disparate_impact_floor"),
                "guardrail_passed": fairness.get("guardrail", {}).get("passed"),
                "n_breaches": fairness.get("guardrail", {}).get("n_breaches"),
                "disparate_impact_ratio": attr_summary.get("disparate_impact_ratio"),
                "equalized_odds_difference": attr_summary.get("equalized_odds_difference"),
                "attribute": attribute,
            },
            "mitigation": mitigation,
        }

    registry = {
        "generated_at": trained_at,
        "default": config.MODEL_VERSION,
        "fair": config.FAIR_MODEL_VERSION,
        "group_attribute": config.MITIGATION_ATTRIBUTE,
        "disparate_impact_floor": config.DISPARATE_IMPACT_FLOOR,
        "mitigation_options": [
            {
                "id": "none",
                "label": "No mitigation",
                "description": "Raw model decision at the cost-optimal threshold.",
            },
            {
                "id": "equalized_odds",
                "label": "Equalized odds (post-processing)",
                "attribute": default_attribute,
                "description": (
                    "Per-group randomised thresholds that equalise true- and "
                    "false-positive rates across the chosen attribute's groups."
                ),
            },
        ],
        "mitigation_attributes": [
            {
                "id": attribute,
                "label": fair.ATTRIBUTE_LABELS.get(attribute, attribute),
                "impact": variants[attribute]["impact"],
            }
            for attribute in variants
        ],
        "group_definitions": {
            "age_band": [
                {"low": lo, "high": hi, "label": lbl} for lo, hi, lbl in config.AGE_BANDS
            ],
            "income_band": {
                "cutpoints": [float(c) for c in income_cutpoints],
                "labels": list(config.INCOME_BAND_LABELS),
            },
        },
        "models": [
            _model_entry(
                config.MODEL_VERSION,
                "Alpha — baseline",
                "baseline",
                "model.joblib",
                "metadata.json",
                fairness_report,
                {"method": "none"},
            ),
            _model_entry(
                config.FAIR_MODEL_VERSION,
                "Beta — fairness-tuned",
                "fair",
                "model_fair.joblib",
                "metadata_fair.json",
                fairness_mitigated,
                {
                    "method": "equalized_odds",
                    "attribute": default_attribute,
                    "base_version": config.MODEL_VERSION,
                    "summary": summarise_mitigation(mitigation_params),
                    "variants": {
                        attribute: {
                            "summary": variants[attribute]["summary"],
                            "impact": variants[attribute]["impact"],
                            "guardrail": variants[attribute]["guardrail"],
                        }
                        for attribute in variants
                    },
                },
                attribute=default_attribute,
            ),
        ],
        "lineage": [
            {
                "version": config.MODEL_VERSION,
                "trained_at": trained_at,
                "role": "baseline",
                "note": "Calibrated LightGBM + cost-optimal policy.",
            },
            {
                "version": config.FAIR_MODEL_VERSION,
                "trained_at": trained_at,
                "role": "fair",
                "parent": config.MODEL_VERSION,
                "note": (
                    "Adds equalized-odds post-processing on "
                    f"{default_attribute} (default)."
                ),
            },
        ],
    }
    config.REGISTRY_JSON.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    _log(f"wrote {config.REGISTRY_JSON}")

    # ---------------------------------------------------------------- reports
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.METRICS_JSON.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    config.CALIBRATION_JSON.write_text(json.dumps(cal_report, indent=2), encoding="utf-8")
    config.FAIRNESS_JSON.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")
    config.FAIRNESS_FAIR_JSON.write_text(
        json.dumps(fairness_mitigated, indent=2), encoding="utf-8"
    )
    config.DRIFT_JSON.write_text(json.dumps(drift_report, indent=2), encoding="utf-8")

    context = {
        "version": config.MODEL_VERSION,
        "fair_version": config.FAIR_MODEL_VERSION,
        "trained_at": trained_at,
        "dataset": dataset_block,
        "metrics": metrics,
        "thresholds": thresholds_block,
        "calibration": {"brier": cal_report.get("brier"), "ece": cal_report.get("ece")},
        "fairness": fairness_report,
        "fairness_mitigated": fairness_mitigated,
        "mitigation": mitigation_block,
        "mitigation_impact": mitigation_impact,
        "top_features": top_features,
    }
    mc.write_model_card(context, config.MODEL_CARD_MD, config.MODEL_CARD_JSON)
    _log(f"wrote {config.MODEL_CARD_MD}")

    _log(f"done in {time.time() - started:.1f}s")
    _log(f"headline: ROC-AUC={metrics['calibrated']['roc_auc']:.4f} "
         f"Brier={metrics['calibrated']['brier']:.4f} ECE={cal_report.get('ece'):.4f}")


if __name__ == "__main__":
    main()
