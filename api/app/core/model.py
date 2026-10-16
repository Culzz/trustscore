"""Model loading and prediction.

The artifact is a plain dict produced by ``training/src/train.py``::

    {
      "preprocessor": TabularPreprocessor,   # NumPy + pandas only
      "booster": lightgbm.Booster,           # native API, no scikit-learn
      "calibration": {"x": [...], "y": [...]},  # isotonic mapping
      "feature_names": [...],
      "version": "...", "thresholds": {...}, "cost_matrix": {...}, ...
    }

Native LightGBM is used on purpose: ``LGBMClassifier`` drags in scikit-learn,
which we do not ship to the serverless runtime. Contributions come from
LightGBM's built-in ``pred_contrib``, so the heavy ``shap`` package is never
needed in production either.
"""
from __future__ import annotations

import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from .config import get_settings
from .features import RAW_INPUT_COLUMNS, engineer_features, feature_matrix


def _normalise_row(row: dict) -> dict:
    """Coerce a caller's dict into the exact raw-input shape the model expects."""
    out = {col: row.get(col, np.nan) for col in RAW_INPUT_COLUMNS}
    for col in ("person_home_ownership", "loan_intent", "loan_grade",
                "cb_person_default_on_file"):
        if isinstance(out[col], str):
            out[col] = out[col].strip().upper()
    return out


class Predictor:
    """Wraps the artifact with the few operations the API needs."""

    def __init__(self, artifact: dict):
        self.preprocessor = artifact["preprocessor"]
        self.booster = artifact["booster"]
        calib = artifact.get("calibration") or {}
        self._calib_x = np.asarray(calib.get("x", [0.0, 1.0]), dtype=float)
        self._calib_y = np.asarray(calib.get("y", [0.0, 1.0]), dtype=float)
        self.feature_names: list[str] = list(artifact["feature_names"])
        self.version: str = artifact.get("version", "unknown")
        self.thresholds: dict = artifact.get("thresholds", {})
        self.cost_matrix: dict = artifact.get("cost_matrix", {})

    # -- internals ---------------------------------------------------------
    def _transform(self, rows: list[dict]) -> np.ndarray:
        frame = pd.DataFrame([_normalise_row(r) for r in rows])
        frame = engineer_features(frame)
        return self.preprocessor.transform(feature_matrix(frame))

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        calibrated = np.interp(raw, self._calib_x, self._calib_y)
        return np.clip(calibrated, 0.0, 1.0)

    # -- public ------------------------------------------------------------
    def raw_proba_many(self, rows: list[dict]) -> np.ndarray:
        xt = self._transform(rows)
        return np.asarray(self.booster.predict(xt), dtype=float)

    def predict_proba_many(self, rows: list[dict]) -> np.ndarray:
        """Calibrated probability of default for each row."""
        return self._calibrate(self.raw_proba_many(rows))

    def predict_proba(self, row: dict) -> float:
        return float(self.predict_proba_many([row])[0])

    def contributions(self, row: dict) -> tuple[np.ndarray, list[str]]:
        """SHAP-style contributions for one row (bias term dropped)."""
        xt = self._transform([row])
        contribs = np.asarray(self.booster.predict(xt, pred_contrib=True))[0]
        # LightGBM appends the base value as the final column.
        return contribs[:-1], self.feature_names


def load_metadata() -> dict:
    path = get_settings().metadata_path
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_predictor() -> Predictor:
    """Load the artifact once per process. Raises a clear error if missing."""
    settings = get_settings()
    path = settings.model_artifact_path
    if not path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {path}. Run "
            "'python -m training.src.train' first."
        )
    return Predictor(joblib.load(path))
