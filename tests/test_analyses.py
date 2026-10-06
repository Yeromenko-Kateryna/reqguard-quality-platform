from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from reqguard.main import app


client = TestClient(app)
EXAMPLE = "The user can quickly reset their password"


def post(text):
    return client.post("/analyses", json={"requirement_text": text})


def test_fixture_analysis():
    response = post(EXAMPLE)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["status"] == "completed"
    assert UUID(body["run_id"]).version == 4
    assert body["analysis"] == {
        "ambiguities": [{
            "term": "quickly",
            "explanation": "The word 'quickly' does not specify a measurable duration.",
        }],
        "missing_measurable_criteria": [
            "Define the maximum allowed password-reset duration and its start/end events."
        ],
        "candidate_test_scenarios": [{
            "title": "Reset a password within the agreed time limit",
            "steps": [
                "Start a password reset for a synthetic user and record the start time.",
                "Complete the reset using a valid reset link and record the end time.",
                "Compare elapsed time with the agreed maximum duration.",
            ],
            "expected_result": "The password is reset within the agreed limit; the limit must first be specified.",
        }],
    }


def test_repeatable_analysis_with_distinct_run_ids():
    responses = [post(EXAMPLE) for _ in range(3)]
    assert all(response.status_code == 200 for response in responses)
    bodies = [response.json() for response in responses]
    assert all(body["analysis"] == bodies[0]["analysis"] for body in bodies)
    assert len({body["run_id"] for body in bodies}) == 3


@pytest.mark.parametrize("text", ["", "   ", "\t\n", "x" * 2001])
def test_invalid_text(text):
    response = post(text)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "requirement_text"]


@pytest.mark.parametrize("text", ["A synthetic unsupported requirement", "x" * 2000])
def test_unsupported_fixture(text):
    response = post(text)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["status"] == "unsupported_fixture"
    assert body["analysis"] is None
    assert UUID(body["run_id"]).version == 4


@pytest.mark.parametrize("payload", [{}, {"requirement_text": None}, {"requirement_text": 123}])
def test_missing_or_non_string_input(payload):
    assert client.post("/analyses", json=payload).status_code == 422


def test_openapi_request_and_response_contracts():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    operation = schema["paths"]["/analyses"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/AnalysisRequest")
    variants = operation["responses"]["200"]["content"]["application/json"]["schema"]["anyOf"]
    assert {v["$ref"].split("/")[-1] for v in variants} == {"CompletedResponse", "UnsupportedResponse"}
    models = schema["components"]["schemas"]
    field = models["AnalysisRequest"]["properties"]["requirement_text"]
    assert field["minLength"] == 1
    assert field["maxLength"] == 2000
    assert models["CompletedResponse"]["properties"]["run_id"]["format"] == "uuid"
    assert models["CompletedResponse"]["properties"]["analysis"]["$ref"].endswith("/Analysis")
