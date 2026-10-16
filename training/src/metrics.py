"""Metrics and calibration measurement.

Thin, explicit wrappers so the numbers in the reports are traceable to one place.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.metrics import average_precision_score


def classification_metrics(y_true: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> dict:
    """Standard metrics treating default (1) as the positive class."""
    y = np.asarray(y_true)
    p = np.asarray(p, dtype=float)
    yhat = (p >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "threshold": float(threshold),
        "precision": float(precision_score(y, yhat, zero_division=0)),
        "recall": float(recall_score(y, yhat, zero_division=0)),
        "f1": float(f1_score(y, yhat, zero_division=0)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


def calibration_curve_data(y_true: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict:
    """Reliability curve plus expected calibration error."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    ece = 0.0
    n = len(p)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(
                {"bin_lower": float(lo), "bin_upper": float(hi), "count": 0,
                 "mean_predicted": None, "observed_rate": None}
            )
            continue
        mean_pred = float(p[mask].mean())
        observed = float(y[mask].mean())
        ece += (count / n) * abs(observed - mean_pred)
        bins.append(
            {
                "bin_lower": float(lo),
                "bin_upper": float(hi),
                "count": count,
                "mean_predicted": mean_pred,
                "observed_rate": observed,
            }
        )
    return {"bins": bins, "ece": float(ece), "n_bins": n_bins}
