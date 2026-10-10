"""What the API accepts and returns. Pydantic checks every incoming value BEFORE it reaches the model.

Rules: unknown fields are rejected, values must have the right type (strict: the text "700" is not a number), and
numbers must lie in the valid ranges of the Freddie Mac data dictionary (wider than what was seen in training, so that a
valid loan is never refused; loans outside the TRAINING range are accepted but flagged in the response).
Every field is required; use null when a value is unknown (the model has a band for missing values).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    credit_score: int | None = Field(..., ge=300, le=850, description="FICO score at origination (300-850), null if unknown")
    dti: float | None = Field(..., ge=0, le=65, description="Debt-to-income ratio in PERCENT (0-65), for example 41 for 41%")
    ltv: float | None = Field(..., ge=1, le=300, description="Loan-to-value in PERCENT (for example 80 for 80%)")
    cltv: float | None = Field(..., ge=1, le=300, description="Combined loan-to-value in PERCENT")
    interest_rate: float | None = Field(..., ge=0, le=20, description="Note rate of the loan in percent (for example 3.75)")
    reference_rate: float | None = Field(
        ..., ge=0, le=20,
        description="Typical rate of loans of the same quarter and term (the caller must provide a reliable reference); "
                    "the model uses the spread interest_rate - reference_rate")
    number_of_borrowers: int | None = Field(..., ge=1, le=10, description="Number of borrowers on the loan")
    mi_pct: float | None = Field(..., ge=0, le=60, description="Mortgage insurance coverage in percent (0 = none)")
    term_months: int | None = Field(..., ge=60, le=600, description="Original loan term in months (360 = 30 years)")
    purpose: Literal["P", "C", "N", "R"] | None = Field(
        ..., description="P purchase, C refinance with cash out, N refinance without cash out, R refinance not specified")


class Reason(BaseModel):
    code: str
    feature: str
    phrase: str
    band: str
    points_lost: float


class ScoreResponse(BaseModel):
    model_id: str
    model_version: str
    score: float = Field(description="Total points: higher is safer (600 points = 50:1 odds, +20 points doubles the odds)")
    probability_of_default: float = Field(description="Through-the-cycle probability of a flagged serious delinquency within 24 months")
    outside_training_range: list[str] = Field(description="Inputs outside the range seen in training: treat the score with caution")
    caution: str


class ExplainResponse(ScoreResponse):
    reasons: list[Reason]
    points: dict[str, float]
    bands: dict[str, str]


class HealthResponse(BaseModel):
    status: str
    model_id: str
    model_version: str


class ModelInfoResponse(BaseModel):
    model: str
    model_id: str
    model_version: str
    trained_on: str
    adopted_by: str
    scaling: dict
    features: dict[str, list[str]]
    training_ranges: dict[str, list[float]]
    known_limits: list[str]
