"""Pydantic request/response models — the HTTP contract.

Validation ranges are the shields from the requirements: an out-of-range or
malformed applicant is rejected with a 422 before it ever reaches the model.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

DISCLAIMER = (
    "TrustScore is a demonstration. The decision shown is SIMULATED, is not a "
    "loan offer, and is not financial advice. Do not rely on it for any real "
    "credit decision."
)

HomeOwnership = Literal["RENT", "OWN", "MORTGAGE", "OTHER"]
LoanIntent = Literal[
    "DEBTCONSOLIDATION", "EDUCATION", "HOMEIMPROVEMENT", "MEDICAL", "PERSONAL", "VENTURE"
]
LoanGrade = Literal["A", "B", "C", "D", "E", "F", "G"]
YesNo = Literal["Y", "N"]


class Applicant(BaseModel):
    """The eleven applicant fields. Everything else the model needs is derived."""

    model_config = ConfigDict(extra="forbid")

    person_age: int = Field(..., ge=18, le=100, description="Age in years")
    person_income: float = Field(..., ge=1_000, le=10_000_000, description="Annual income")
    person_home_ownership: HomeOwnership
    person_emp_length: Optional[float] = Field(
        default=None, ge=0, le=60, description="Employment length in years (optional)"
    )
    loan_intent: LoanIntent
    loan_grade: LoanGrade
    loan_amnt: float = Field(..., ge=500, le=40_000, description="Requested amount")
    loan_int_rate: Optional[float] = Field(
        default=None, ge=0, le=40, description="Interest rate percent (optional)"
    )
    cb_person_default_on_file: YesNo
    cb_person_cred_hist_length: int = Field(
        ..., ge=0, le=60, description="Credit history length in years"
    )

    def as_model_row(self) -> dict:
        return self.model_dump()


class Thresholds(BaseModel):
    approve_max_pd: float
    decline_min_pd: float


class ReasonItem(BaseModel):
    factor: str
    detail: str
    direction: Literal["increases", "reduces"]
    text: str


class PredictResponse(BaseModel):
    prediction_id: str
    model_version: str
    probability_of_default: float
    band: Literal["approve", "refer", "decline"]
    band_label: Literal["low", "medium", "high"]
    thresholds: Thresholds
    created_at: str
    disclaimer: str = DISCLAIMER


class ExplainResponse(BaseModel):
    model_version: str
    probability_of_default: float
    band: Literal["approve", "refer", "decline"]
    reasons: list[ReasonItem]
    disclaimer: str = DISCLAIMER


class DecisionResponse(BaseModel):
    decision: Literal["approve", "refer", "decline"]
    band_label: Literal["low", "medium", "high"]
    simulated: bool = True
    probability_of_default: float
    thresholds: Thresholds
    cost_matrix: dict
    expected_cost: float
    model_version: str
    disclaimer: str = DISCLAIMER


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant: Applicant
    # Optional policy override so the lender view can explore thresholds safely.
    approve_max_pd: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    decline_min_pd: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CounterfactualScenario(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_type: str
    changeability: str
    feature: str
    from_value: float | str = Field(alias="from")
    to_value: float | str = Field(alias="to")
    description: str
    new_pd: float
    new_band: Literal["approve", "refer", "decline"]


class CounterfactualResponse(BaseModel):
    model_version: str
    current_pd: float
    current_band: Literal["approve", "refer", "decline"]
    target_band: Literal["approve", "refer", "decline"]
    scenarios: list[CounterfactualScenario]
    disclaimer: str = DISCLAIMER


class HealthResponse(BaseModel):
    status: str
    model_version: str | None
    model_loaded: bool
    database_configured: bool
    time: str


class StatsResponse(BaseModel):
    enabled: bool
    total_predictions: int
    mean_pd: float | None
    high_risk_share: float | None
    bands: dict
    window: str
    note: str | None = None
