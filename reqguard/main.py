from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    requirement_text: str = Field(min_length=1, max_length=2000, strict=True)

    @field_validator("requirement_text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirement_text must contain non-whitespace characters")
        return value


class Ambiguity(BaseModel):
    term: str
    explanation: str


class TestCandidate(BaseModel):
    title: str
    steps: list[str]
    expected_result: str


class Analysis(BaseModel):
    ambiguities: list[Ambiguity]
    missing_measurable_criteria: list[str]
    candidate_test_scenarios: list[TestCandidate]


class CompletedResponse(BaseModel):
    run_id: UUID
    provider: Literal["fake"] = "fake"
    status: Literal["completed"] = "completed"
    analysis: Analysis


class UnsupportedResponse(BaseModel):
    run_id: UUID
    provider: Literal["fake"] = "fake"
    status: Literal["unsupported_fixture"] = "unsupported_fixture"
    analysis: None = None


FIXTURE_TEXT = "The user can quickly reset their password"


def fake_analysis() -> Analysis:
    """Return authored fixture data; perform no semantic inference."""
    return Analysis(
        ambiguities=[Ambiguity(
            term="quickly",
            explanation="The word 'quickly' does not specify a measurable duration.",
        )],
        missing_measurable_criteria=[
            "Define the maximum allowed password-reset duration and its start/end events."
        ],
        candidate_test_scenarios=[TestCandidate(
            title="Reset a password within the agreed time limit",
            steps=[
                "Start a password reset for a synthetic user and record the start time.",
                "Complete the reset using a valid reset link and record the end time.",
                "Compare elapsed time with the agreed maximum duration.",
            ],
            expected_result="The password is reset within the agreed limit; the limit must first be specified.",
        )],
    )


app = FastAPI(title="ReqGuard", version="0.1.0")


@app.post("/analyses", response_model=CompletedResponse | UnsupportedResponse)
def create_analysis(request: AnalysisRequest) -> CompletedResponse | UnsupportedResponse:
    run_id = uuid4()
    if request.requirement_text != FIXTURE_TEXT:
        return UnsupportedResponse(run_id=run_id)
    return CompletedResponse(run_id=run_id, analysis=fake_analysis())
