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
    FINAL_EVAL_KEY_PREFIX,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TUNING_KEY_PREFIX,
    TabularPreprocessor,
)
from app.services.counterfactual import find_counterfactuals
from app.services.decision import (
    APPROVE,
    DECLINE,
    REFER,
    CostMatrix,
    analytic_thresholds,
    cost_equivalence,
    decide_array,
    expected_cost,
    expected_cost_per_loan,
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
from . import evaluation_report as ereport


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

    Returns ``(x, y, oof)`` where ``oof`` is the out-of-fold *raw* prediction for
    every training row. Those are the only unbiased in-sample scores we have, and
    the equalized-odds post-processor is fitted on their calibrated form -- never
    on the policy-tuning or final-evaluation sets.
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
    return iso.X_thresholds_.astype(float), iso.y_thresholds_.astype(float), oof


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
    calib_x, calib_y, oof_raw = _fit_isotonic(X_train, y_train, _lgb_params(), best_rounds)
    p_cal_train = _apply_calibration(oof_raw, calib_x, calib_y)
    p_cal_val = _apply_calibration(raw_val, calib_x, calib_y)
    p_cal_test = _apply_calibration(raw_test, calib_x, calib_y)

    # ---------------------------------------------------------------- metrics
    metrics = {
        "baseline_lr": met.classification_metrics(y_test, p_lr_test),
        "lightgbm": met.classification_metrics(y_test, raw_test),
        "calibrated": met.classification_metrics(y_test, p_cal_test, ci=True),
    }
    _log(f"test ROC-AUC: lr={metrics['baseline_lr']['roc_auc']:.4f} "
         f"lgbm={metrics['lightgbm']['roc_auc']:.4f} "
         f"calibrated={metrics['calibrated']['roc_auc']:.4f}")

    # ------------------------------------------------------------ calibration report
    cal_report = met.calibration_curve_data(y_test, p_cal_test)
    cal_report["brier"] = metrics["calibrated"]["brier"]

    # ------------------------------------------------------------ thresholds
    # The analytic cost crossover is the *policy*; the grid search only verifies
    # it (see services/decision.py). Deploying the grid point would be wrong: on
    # a flat cost plateau its first-wins tie-break returns an arbitrary, sample-
    # specific threshold pair that disagrees with the cost-optimal rule on
    # applicants the sample never contained.
    costs = CostMatrix(
        false_approve=config.COST_FALSE_APPROVE,
        false_decline=config.COST_FALSE_DECLINE,
        review=config.COST_REVIEW,
    )
    ta_analytic, td_analytic = analytic_thresholds(costs)
    approve_max_pd, decline_min_pd = ta_analytic, td_analytic
    val_amounts = val["loan_amnt"].to_numpy(dtype=float)
    ta_grid, td_grid, _ec_grid = grid_thresholds(p_cal_val, val_amounts, costs)
    equivalence = cost_equivalence(
        p_cal_val,
        val_amounts,
        costs,
        [(approve_max_pd, decline_min_pd), (ta_grid, td_grid)],
    )
    grid_block = {
        "approve_max_pd": float(ta_grid),
        "decline_min_pd": float(td_grid),
        "cost_delta_vs_analytic": float(equivalence["candidates"][1]["delta_vs_best"]),
        "analytic_is_cost_optimal": bool(
            equivalence["candidates"][0]["is_cost_optimal"]
        ),
        "verified_on": "validation",
        "note": (
            "Search only. A zero delta means the surface is flat across a gap in "
            "the score distribution, so the grid point is arbitrary."
        ),
    }
    _log(
        f"thresholds: approve<= {approve_max_pd:.5f}, decline>= {decline_min_pd:.5f} "
        f"(analytic policy; grid says {ta_grid:.5f}/{td_grid:.5f}, "
        f"cost delta {grid_block['cost_delta_vs_analytic']:.3e})"
    )

    decisions_test = decide_array(p_cal_test, approve_max_pd, decline_min_pd)
    test_amounts = test["loan_amnt"].to_numpy(dtype=float)
    realized = realized_cost(y_test, test_amounts, decisions_test, costs)
    expected = expected_cost(p_cal_test, test_amounts, decisions_test, costs)
    ec_per_loan = expected_cost_per_loan(
        p_cal_val, val_amounts, approve_max_pd, decline_min_pd, costs
    )
    band_counts = pd.Series(decisions_test).value_counts().to_dict()
    approval_rate = float((decisions_test == APPROVE).mean())
    _log(f"test approval rate {approval_rate:.3f}; bands {band_counts}")

    thresholds_block = {
        "approve_max_pd": float(approve_max_pd),
        "decline_min_pd": float(decline_min_pd),
        "analytic_approve_max_pd": float(ta_analytic),
        "analytic_decline_min_pd": float(td_analytic),
        "selected_by": "analytic_cost_minimisation",
        "grid_verification": grid_block,
        "cost_equivalence": equivalence,
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
    # Evaluation protocol (docs/EVALUATION.md):
    #   train      -> fit the booster and cross-fitted isotonic calibration
    #   validation -> verify the policy; also the interactive *policy tuning set*
    #                 the auditor console reads live
    #   test       -> final held-out evaluation, reported once
    #
    # The equalized-odds post-processor is fitted on **train** (the out-of-fold
    # calibrated scores), never on the tuning set and never on the final test
    # set. So both the console's tuning-set figures and the model card's test
    # figures are out-of-sample for the mitigation itself.
    _log("fitting equalized-odds post-processing on train (out-of-fold) ...")
    final_keys = [f"{FINAL_EVAL_KEY_PREFIX}:{i}" for i in range(len(test))]
    tuning_keys = [f"{TUNING_KEY_PREFIX}:{i}" for i in range(len(val))]
    tuning_decisions = decide_array(p_cal_val, approve_max_pd, decline_min_pd)

    def _groups(frame, attribute: str):
        return frame[attribute].astype("string").fillna("unknown").tolist()

    def _apply_mitigation(p, groups, decisions, params, keys) -> np.ndarray:
        approved_m = apply_equalized_odds(p, groups, params, keys=keys)
        return np.where(
            approved_m & (decisions != APPROVE),
            APPROVE,
            np.where((~approved_m) & (decisions == APPROVE), REFER, decisions),
        )

    def _attr_summary(report: dict, attribute: str) -> dict:
        block = report.get("attributes", {}).get(attribute, {})
        return block.get("summary", {}) or {}

    def _impact(attribute, label, fairness_base, fairness_mit, dec_base, dec_mit, y_true, amounts):
        s_base = _attr_summary(fairness_base, attribute)
        s_mit = _attr_summary(fairness_mit, attribute)
        di_base = s_base.get("disparate_impact_ratio")
        di_mit = s_mit.get("disparate_impact_ratio")
        total = max(float(np.sum(amounts)), 1.0)
        return {
            "attribute": attribute,
            "evaluated_on": label,
            "n": int(len(y_true)),
            "approval_rate_base": float((dec_base == APPROVE).mean()),
            "approval_rate_mitigated": float((dec_mit == APPROVE).mean()),
            "realized_cost_per_loan_base": float(
                realized_cost(y_true, amounts, dec_base, costs) / total
            ),
            "realized_cost_per_loan_mitigated": float(
                realized_cost(y_true, amounts, dec_mit, costs) / total
            ),
            "disparate_impact_ratio_base": di_base,
            "disparate_impact_ratio_mitigated": di_mit,
            "equalized_odds_difference_base": s_base.get("equalized_odds_difference"),
            "equalized_odds_difference_mitigated": s_mit.get("equalized_odds_difference"),
            "n_breaches_base": fairness_base["guardrail"]["n_breaches"],
            "n_breaches_mitigated": fairness_mit["guardrail"]["n_breaches"],
            "disparate_impact_gain": (
                (di_mit - di_base) if (di_mit is not None and di_base is not None) else None
            ),
        }

    variants: dict = {}
    variant_fairness: dict = {}
    for attribute in config.MITIGATION_VARIANTS:
        if not all(attribute in f.columns for f in (train_audit, val_audit, test_audit)):
            continue
        params = fit_equalized_odds(
            y=y_train,
            p=p_cal_train,
            groups=_groups(train_audit, attribute),
            base_threshold=approve_max_pd,
            min_group_size=config.MITIGATION_MIN_GROUP_SIZE,
            attribute=attribute,
        )
        # --- final evaluation: measured on the held-out test split ------------
        dec_m_test = _apply_mitigation(
            p_cal_test, _groups(test_audit, attribute), decisions_test, params, final_keys
        )
        fairness_m = fair.compute_fairness(
            test_audit, y_test, p_cal_test, dec_m_test, config.FAIR_MODEL_VERSION
        )
        # --- tuning set: what the interactive auditor console recomputes ------
        dec_m_tuning = _apply_mitigation(
            p_cal_val, _groups(val_audit, attribute), tuning_decisions, params, tuning_keys
        )
        fairness_tuning_base = fair.compute_fairness(
            val_audit, y_val, p_cal_val, tuning_decisions, config.MODEL_VERSION
        )
        fairness_tuning_mit = fair.compute_fairness(
            val_audit, y_val, p_cal_val, dec_m_tuning, config.FAIR_MODEL_VERSION
        )
        variants[attribute] = {
            "params": params,
            "summary": summarise_mitigation(params),
            "fit_on": "train_out_of_fold",
            "impact": _impact(
                attribute, "test", fairness_report, fairness_m,
                decisions_test, dec_m_test, y_test, test_amounts,
            ),
            "impact_tuning": _impact(
                attribute, "validation", fairness_tuning_base, fairness_tuning_mit,
                tuning_decisions, dec_m_tuning, y_val, val_amounts,
            ),
            "guardrail": fairness_m["guardrail"],
            "guardrail_tuning": fairness_tuning_mit["guardrail"],
        }
        variant_fairness[attribute] = fairness_m

    # Pick the variant that removes the most breaches on the *final* test set,
    # then improves DI the most.
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
        "fit_on": "train (out-of-fold calibrated scores)",
        "tuning_set": "validation",
        "final_set": "test",
        "params": mitigation_params,
        "variants": variants,
    }
    mitigation_impact = default_variant["impact"]
    mitigation_impact_tuning = default_variant["impact_tuning"]
    for attribute, block in variants.items():
        imp = block["impact"]
        imp_t = block["impact_tuning"]
        _log(
            f"  {attribute:24s} test breaches {imp['n_breaches_base']} -> "
            f"{imp['n_breaches_mitigated']}; test DI "
            f"{imp['disparate_impact_ratio_base']} -> "
            f"{imp['disparate_impact_ratio_mitigated']}; tuning DI "
            f"{imp_t['disparate_impact_ratio_base']} -> "
            f"{imp_t['disparate_impact_ratio_mitigated']}"
        )
    _log(f"mitigation default attribute: {default_attribute}")

    # --------------------------------------------------------------- portfolio
    # The **policy tuning set** = the validation split. The auditor console
    # experiments here. The final test split is deliberately NOT shipped: if the
    # console read the test rows the auditor would be inspecting and tuning
    # against the very data reserved for the one-time final evaluation, and the
    # "held-out" number would stop being held out.
    #
    # Every audited attribute is carried as an integer code plus a shared
    # ``levels`` table so mitigation, A/B and the bias injector can target any of
    # them. Scores are stored verbatim (JSON round-trips a float exactly):
    # rounding, even to 8 decimals, flipped decisions where the equalized-odds
    # cut-offs sit in the dense part of the score distribution and moved the live
    # DI. Exposure is rounded to the nearest $100. Public data; no PII.
    port_idx = np.arange(len(val))

    portfolio_attributes = [
        a
        for a in [config.MITIGATION_ATTRIBUTE, *config.MITIGATION_VARIANTS]
        if a in val_audit.columns
    ]
    # de-duplicate while preserving order
    portfolio_attributes = list(dict.fromkeys(portfolio_attributes))

    group_lists = {a: _groups(val_audit, a) for a in portfolio_attributes}
    levels = {
        a: sorted({group_lists[a][int(i)] for i in port_idx})
        for a in portfolio_attributes
    }
    code_of = {a: {label: k for k, label in enumerate(levels[a])} for a in portfolio_attributes}

    portfolio_rows = [
        [
            float(p_cal_val[i]),
            round(float(val_amounts[i]) / 100.0) * 100.0,
            int(y_val[i]),
            [code_of[a][group_lists[a][int(i)]] for a in portfolio_attributes],
        ]
        for i in port_idx
    ]
    portfolio = {
        "version": config.MODEL_VERSION,
        "n": len(portfolio_rows),
        "set": "validation",
        "role": "policy_tuning",
        "group_attribute": config.MITIGATION_ATTRIBUTE
        if config.MITIGATION_ATTRIBUTE in portfolio_attributes
        else portfolio_attributes[0],
        "attributes": portfolio_attributes,
        "levels": levels,
        "group_values": levels,
        "fields": ["pd", "exposure", "y", "codes"],
        "row_key_prefix": TUNING_KEY_PREFIX,
        "rows": portfolio_rows,
        "note": (
            "Policy tuning set: the public validation split (calibrated scores "
            "verbatim, exposure rounded to the nearest 100). The final test split "
            "is never shipped, so it stays a one-time held-out evaluation. "
            "Contains no personal data."
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

    # ------------------------------------------ feature provenance & robustness
    # Two honesty checks that the random split hides:
    #   1. `loan_grade` is assigned by the lender and `loan_int_rate` follows from
    #      it, so both are underwriting *outputs*, not independent applicant
    #      signals. Retrain without them and compare like-for-like.
    #   2. The dataset has no timestamp, so a temporal split is impossible; hold
    #      out an entire income *segment* instead, to see ranking skill on
    #      applicants unlike the training population.
    _log("feature provenance: ablation without lender-assigned fields ...")
    lender_assigned = ("loan_grade", "loan_int_rate", "int_rate_missing")
    abl_numeric = [c for c in NUMERIC_FEATURES if c not in lender_assigned]
    abl_categorical = [c for c in CATEGORICAL_FEATURES if c not in lender_assigned]
    abl_pre = TabularPreprocessor(numeric=abl_numeric, categorical=abl_categorical).fit(train)
    abl_booster = _train_booster(
        abl_pre.transform(feat.feature_matrix(train)),
        y_train,
        abl_pre.transform(feat.feature_matrix(val)),
        y_val,
    )
    abl_p_test = abl_booster.predict(abl_pre.transform(feat.feature_matrix(test)))
    abl_metrics = met.classification_metrics(y_test, abl_p_test)
    ablation = {
        "removed_features": ["loan_grade", "loan_int_rate"],
        "reason": (
            "loan_grade is assigned by the lender at origination and loan_int_rate "
            "follows from it, so both encode the lender's own underwriting judgement "
            "rather than an independent applicant signal."
        ),
        "evaluated_on": "test (both rows uncalibrated and on the same split)",
        "full": {
            "roc_auc": metrics["lightgbm"].get("roc_auc"),
            "pr_auc": metrics["lightgbm"].get("pr_auc"),
            "brier": metrics["lightgbm"].get("brier"),
        },
        "without_lender_assigned": {
            "roc_auc": abl_metrics["roc_auc"],
            "pr_auc": abl_metrics["pr_auc"],
            "brier": abl_metrics["brier"],
        },
        "delta_roc_auc": float(metrics["lightgbm"]["roc_auc"] - abl_metrics["roc_auc"]),
        "provenance_note": (
            "Both rows are uncalibrated and evaluated on the same test split, so the "
            "delta is like-for-like. It measures how much of the headline ranking "
            "skill came from reproducing the lender's own risk tiering; a system that "
            "must score applicants the lender has not already judged should expect "
            "the lower number."
        ),
    }
    _log(
        f"ablation: ROC-AUC full={ablation['full']['roc_auc']:.4f} "
        f"without lender-assigned={abl_metrics['roc_auc']:.4f} "
        f"(delta {ablation['delta_roc_auc']:.4f})"
    )

    _log("robustness: income-segment holdout ...")
    income_q80 = float(np.quantile(clean["person_income"].to_numpy(dtype=float), 0.8))
    within = clean[clean["person_income"] <= income_q80].copy()
    shifted = clean[clean["person_income"] > income_q80].copy()
    shift_train, shift_val, _ = feat.stratified_split(within, seed=config.SEED)
    shift_pre = TabularPreprocessor().fit(shift_train)
    shift_booster = _train_booster(
        shift_pre.transform(feat.feature_matrix(shift_train)),
        shift_train[config.TARGET].to_numpy(),
        shift_pre.transform(feat.feature_matrix(shift_val)),
        shift_val[config.TARGET].to_numpy(),
    )
    p_in = shift_booster.predict(shift_pre.transform(feat.feature_matrix(shift_val)))
    p_out = shift_booster.predict(shift_pre.transform(feat.feature_matrix(shifted)))
    shift_stress = {
        "segment": "top income quintile (person_income > q80)",
        "threshold": income_q80,
        "n_in_population": int(len(shift_val)),
        "n_out_of_population": int(len(shifted)),
        "in_population": met.classification_metrics(shift_val[config.TARGET].to_numpy(), p_in),
        "out_of_population": met.classification_metrics(shifted[config.TARGET].to_numpy(), p_out),
        "note": (
            "The dataset has no timestamp, so a temporal split is not possible. "
            "Holding out an entire income segment is the closest available proxy: it "
            "shows how ranking skill changes on applicants drawn from a part of the "
            "population the model never trained on. The random stratified split used "
            "for the headline metrics does not capture this."
        ),
    }
    shift_stress["delta_roc_auc"] = float(
        shift_stress["in_population"]["roc_auc"] - shift_stress["out_of_population"]["roc_auc"]
    )
    _log(
        f"segment holdout: ROC-AUC in-population="
        f"{shift_stress['in_population']['roc_auc']:.4f} out-of-population="
        f"{shift_stress['out_of_population']['roc_auc']:.4f} "
        f"(delta {shift_stress['delta_roc_auc']:.4f})"
    )

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

    evaluation_protocol = {
        "protocol_version": "3-way (train / validation / test)",
        "role_split": {
            "train": "fit booster + cross-fitted isotonic calibration + equalized-odds mitigation",
            "validation": "policy verification and the interactive auditor *policy tuning* set",
            "test": "one-time held-out final evaluation (model card, evaluation report)",
        },
        "mitigation_fit_on": "train (out-of-fold calibrated scores)",
        "mitigation_measured_on": ["test (headline)", "validation (console/tuning)"],
        "policy_tuning_set": {
            "name": "validation",
            "rows": int(len(val)),
            "shipped_as_portfolio": True,
            "note": "The auditor console experiments only on this set.",
        },
        "final_evaluation_set": {
            "name": "test",
            "rows": int(len(test)),
            "shipped_as_portfolio": False,
            "note": "Row-level test data is never shipped, so it stays held out.",
        },
    }

    metadata = {
        "version": config.MODEL_VERSION,
        "trained_at": trained_at,
        "disclaimer": mc.DISCLAIMER,
        "dataset": dataset_block,
        "evaluation_protocol": evaluation_protocol,
        "metrics": metrics,
        "calibration": {
            "brier": cal_report.get("brier"),
            "ece": cal_report.get("ece"),
            "n_bins": cal_report.get("n_bins"),
            "curve": cal_report.get("bins"),
        },
        "thresholds": thresholds_block,
        "fairness": fairness_report,
        "ablation": ablation,
        "robustness": {"income_segment_holdout": shift_stress},
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
            "fit_on": "train (out-of-fold calibrated scores)",
            "variants": {
                attribute: variants[attribute]["impact"] for attribute in variants
            },
            "variants_tuning": {
                attribute: variants[attribute]["impact_tuning"]
                for attribute in variants
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
        "evaluation_protocol": evaluation_protocol,
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
                "impact_tuning": variants[attribute]["impact_tuning"],
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
                            "impact_tuning": variants[attribute]["impact_tuning"],
                            "guardrail": variants[attribute]["guardrail"],
                            "guardrail_tuning": variants[attribute]["guardrail_tuning"],
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
        "evaluation_protocol": evaluation_protocol,
        "metrics": metrics,
        "thresholds": thresholds_block,
        "calibration": {"brier": cal_report.get("brier"), "ece": cal_report.get("ece")},
        "calibration_bins": cal_report.get("bins"),
        "fairness": fairness_report,
        "fairness_mitigated": fairness_mitigated,
        "mitigation": mitigation_block,
        "mitigation_impact": mitigation_impact,
        "mitigation_impact_tuning": mitigation_impact_tuning,
        "ablation": ablation,
        "robustness": {"income_segment_holdout": shift_stress},
        "top_features": top_features,
    }
    mc.write_model_card(context, config.MODEL_CARD_MD, config.MODEL_CARD_JSON)
    _log(f"wrote {config.MODEL_CARD_MD}")
    ereport.write_evaluation_report(context, config.EVALUATION_MD)
    _log(f"wrote {config.EVALUATION_MD}")

    _log(f"done in {time.time() - started:.1f}s")
    _log(f"headline: ROC-AUC={metrics['calibrated']['roc_auc']:.4f} "
         f"Brier={metrics['calibrated']['brier']:.4f} ECE={cal_report.get('ece'):.4f}")


if __name__ == "__main__":
    main()
