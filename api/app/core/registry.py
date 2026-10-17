"""Model registry: versions, lineage and mitigation options.

``training/src/train.py`` writes ``api/artifacts/registry.json`` describing every
model it produced. This module is the runtime reader. If the registry is missing
(an older checkout), it degrades to a single-model view built from settings so
the API still answers.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .config import get_settings
from .model import get_predictor

TIER3_ATTRIBUTE_LABELS = {
    "age_band": "Age band",
    "income_band": "Income band",
    "person_home_ownership": "Home ownership",
    "loan_intent": "Loan purpose",
}


@lru_cache(maxsize=1)
def load_registry() -> dict:
    settings = get_settings()
    path = settings.registry_path
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Fallback: a one-model registry so /models still works.
    return {
        "default": settings.model_version,
        "fair": settings.fair_model_version,
        "group_attribute": "age_band",
        "disparate_impact_floor": 0.80,
        "mitigation_options": [
            {"id": "none", "label": "No mitigation"},
            {
                "id": "equalized_odds",
                "label": "Equalized odds (post-processing)",
                "attribute": "age_band",
            },
        ],
        "mitigation_attributes": [
            {"id": "age_band", "label": "Age band"},
        ],
        "models": [
            {
                "version": settings.model_version,
                "label": "Alpha — baseline",
                "role": "baseline",
                "artifact": "model.joblib",
                "metadata": "metadata.json",
                "mitigation": {"method": "none"},
            }
        ],
        "lineage": [],
    }


def default_version() -> str:
    return load_registry().get("default") or get_settings().model_version


def fair_version() -> str:
    return load_registry().get("fair") or get_settings().fair_model_version


def group_attribute() -> str:
    return load_registry().get("group_attribute", "age_band")


def disparate_impact_floor() -> float:
    return float(load_registry().get("disparate_impact_floor", 0.80))


def list_models() -> list[dict]:
    return list(load_registry().get("models", []))


def get_model(version: str) -> dict | None:
    for model in list_models():
        if model.get("version") == version:
            return model
    return None


def lineage() -> list[dict]:
    return list(load_registry().get("lineage", []))


def mitigation_options() -> list[dict]:
    return list(load_registry().get("mitigation_options", []))


def default_mitigation_attribute() -> str:
    """The attribute the training run chose as the default mitigation variant.

    Falls back to the registry's audit attribute when no explicit choice was
    recorded (an older single-variant registry).
    """
    for option in mitigation_options():
        if option.get("id") == "equalized_odds" and option.get("attribute"):
            return str(option["attribute"])
    return group_attribute()


def mitigation_attributes() -> list[dict]:
    """The derivable attributes mitigation can target, for the UI selector."""
    reg = load_registry()
    attributes = reg.get("mitigation_attributes")
    if attributes:
        return list(attributes)
    return [{"id": group_attribute(), "label": TIER3_ATTRIBUTE_LABELS.get(group_attribute(), group_attribute())}]


def income_cutpoints() -> list[float] | None:
    return (
        load_registry()
        .get("group_definitions", {})
        .get("income_band", {})
        .get("cutpoints")
    )


def age_band_definitions() -> list[dict]:
    return load_registry().get("group_definitions", {}).get("age_band", [])


def mitigation_params_for(version: str | None, attribute: str | None = None) -> dict | None:
    """Fitted equalized-odds params for a model version and attribute.

    Falls back to the fairness-tuned model's params when a baseline version is
    asked to "apply fairness".
    """
    for candidate in (version, fair_version()):
        try:
            predictor = get_predictor(candidate)
        except Exception:
            continue
        mitigation = predictor.mitigation
        if not mitigation:
            continue
        variants = mitigation.get("variants") or {}
        chosen = attribute or mitigation.get("attribute")
        if chosen and chosen in variants:
            return variants[chosen].get("params")
        if mitigation.get("params"):
            return mitigation["params"]
    return None


def variant_summaries(version: str | None = None) -> dict:
    """Per-attribute mitigation summaries (for the audit UI)."""
    try:
        predictor = get_predictor(version or fair_version())
    except Exception:
        return {}
    mitigation = predictor.mitigation or {}
    out = {}
    for attr, block in (mitigation.get("variants") or {}).items():
        out[attr] = {
            "label": TIER3_ATTRIBUTE_LABELS.get(attr, attr),
            "summary": block.get("summary"),
            "impact": block.get("impact"),
        }
    return out


def registry_summary() -> dict:
    reg = load_registry()
    return {
        "default": default_version(),
        "fair": fair_version(),
        "group_attribute": group_attribute(),
        "disparate_impact_floor": disparate_impact_floor(),
        "mitigation_options": mitigation_options(),
        "mitigation_attributes": mitigation_attributes(),
        "n_models": len(list_models()),
        "generated_at": reg.get("generated_at"),
    }
