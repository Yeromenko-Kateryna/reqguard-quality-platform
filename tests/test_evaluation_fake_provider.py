"""Byte fixture and provider boundary tests, entirely offline."""

from dataclasses import FrozenInstanceError, fields, replace
from hashlib import sha256

import pytest

from reqguard.evaluation.dataset import EXAMPLE_IDS, load_dataset
from reqguard.evaluation.execution import AttemptContext, ExecutionRuntime
from reqguard.evaluation.fake_provider import (
    DeterministicFakeProvider, FakeRequest, FakeResponse, ProviderContractError,
    ProviderTimeout, ProviderTransportError, TRUSTED_POLICY, fixtures, validate_response,
)
from reqguard.evaluation.hard_fail import trusted_task_hash


def request(example="F01", scenario="nominal"):
    record = next(r for r in load_dataset() if r.example_id == example)
    return FakeRequest("run", f"request-{example}", example, record.requirement_text,
                       sha256(record.requirement_text.encode()).hexdigest(), fixtures(scenario).sha256)


def context():
    runtime = ExecutionRuntime()
    return AttemptContext(runtime, runtime.monotonic_ms() + 60_000)


@pytest.mark.parametrize("scenario", ["nominal", "timeout", "transport_error", "malformed", "empty", "mixed"])
def test_fixtures_complete_immutable_and_deterministic(scenario):
    fixture = fixtures(scenario)
    assert tuple(f.example_id for f in fixture.entries) == EXAMPLE_IDS
    assert fixture.to_bytes() == fixtures(scenario).to_bytes()
    assert fixture.sha256 == sha256(fixture.to_bytes()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        fixture.scenario = "changed"
    provider = DeterministicFakeProvider(fixture)
    for item in fixture.entries:
        req = request(item.example_id, scenario)
        if item.outcome != "received":
            fault = ProviderTimeout if item.outcome == "timeout" else ProviderTransportError
            with pytest.raises(fault):
                provider.invoke(req, context())
        else:
            first = provider.invoke(req, context())
            assert first == provider.invoke(req, context())
            assert first.raw == item.raw
            validate_response(first, req)
            with pytest.raises(FrozenInstanceError):
                first.raw = b"changed"


@pytest.mark.parametrize("field,value", [
    ("evaluation_run_id", "../bad"), ("request_id", "request-F02"), ("example_id", "X01"),
    ("requirement_text", "changed"), ("input_sha256", "0" * 64),
    ("fixture_sha256", "A" * 64), ("trusted_task_policy", "changed"), ("version", "future"),
])
def test_invalid_requests_rejected(field, value):
    with pytest.raises(ProviderContractError):
        DeterministicFakeProvider(fixtures()).invoke(replace(request(), **{field: value}), context())


@pytest.mark.parametrize("field,value", [
    ("revision", "future"), ("entries", ()), ("scenario", "unknown"),
    ("entries", (replace(fixtures().entries[0], raw=b"wrong"), *fixtures().entries[1:])),
    ("entries", (replace(fixtures().entries[0], raw=bytearray(fixtures().entries[0].raw)),
                 *fixtures().entries[1:])),
])
def test_invalid_fixtures_rejected(field, value):
    with pytest.raises(ProviderContractError):
        DeterministicFakeProvider(replace(fixtures(), **{field: value}))


@pytest.mark.parametrize("field,value", [
    ("request_id", "other"), ("example_id", "F02"), ("correlation_id", "other"),
    ("raw", "text"), ("raw", bytearray(b"x")), ("raw", None), ("version", "future"),
])
def test_invalid_response_fields(field, value):
    req = request()
    response = DeterministicFakeProvider(fixtures()).invoke(req, context())
    with pytest.raises(ProviderContractError):
        validate_response(replace(response, **{field: value}), req)


@pytest.mark.parametrize("response", [None, b"x", {}, object()])
def test_invalid_response_types(response):
    with pytest.raises(ProviderContractError):
        validate_response(response, request())


def test_request_surface_and_policy():
    assert {f.name for f in fields(FakeRequest)} == {
        "evaluation_run_id", "request_id", "example_id", "requirement_text", "input_sha256",
        "fixture_sha256", "trusted_task_policy", "version"}
    assert sha256(TRUSTED_POLICY.encode()).hexdigest() == trusted_task_hash()
    with pytest.raises(FrozenInstanceError):
        request().example_id = "F02"
    assert {f.name for f in fields(FakeResponse)} == {
        "request_id", "example_id", "correlation_id", "raw", "version"}


@pytest.mark.parametrize("scenario,expected", [
    ("nominal", "80955b383cbb48d32f8ea32bba23a095214ef17643407256ec3bf627b95f71fc"),
    ("timeout", "9c89669565fca056dcdc404de5396bd6d6c52edf405d514a8f1a2a5731b0c3fe"),
    ("transport_error", "0d427ad8cd1cfdc778d44543acb195cce4fcad99d5190f27d2e931558d1901ac"),
    ("malformed", "3bfdb92a291f26ea18d1352f55226b4ed3838bc187292001e17ae44013ee0667"),
    ("empty", "b7f510ae65a78cc047de10ced049a5e6640ef7b545928cd82c4134b63f80947c"),
    ("mixed", "2edc40bfd9035ca4cc0084809c724c4a625c5d32557868b643e027f083d757db"),
])
def test_pinned_v1_fixture_hashes(scenario, expected):
    assert fixtures(scenario).sha256 == expected
