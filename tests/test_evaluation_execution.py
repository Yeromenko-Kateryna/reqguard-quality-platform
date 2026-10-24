"""D2 execution and D1 registration failures, using virtual time only."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from reqguard.evaluation.dataset import EXAMPLE_IDS, DatasetValidationError
from reqguard.evaluation.evidence import EvidenceError, EvidencePackage, parse_metadata
from reqguard.evaluation.execution import (
    ExecutionCancelled, ExecutionConfig, ExecutionRuntime, execute,
)
from reqguard.evaluation.fake_provider import (
    DeterministicFakeProvider, ProviderTransportError, correlation_id, fixtures,
)


class VirtualRuntime(ExecutionRuntime):
    def __init__(self):
        self.ms = 0
        self.cancelled = False

    def monotonic_ms(self):
        return self.ms

    def utc_now(self):
        return (datetime(2026, 10, 25, tzinfo=timezone.utc) + timedelta(
            milliseconds=self.ms)).isoformat().replace("+00:00", "Z")

    def check_cancelled(self):
        if self.cancelled:
            raise ExecutionCancelled()


class SpyProvider:
    def __init__(self, fixture_set, action=None):
        self.inner = DeterministicFakeProvider(fixture_set)
        self.requests = []
        self.contexts = []
        self.action = action

    def invoke(self, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        if self.action is not None:
            return self.action(self, request, context)
        return self.inner.invoke(request, context)


def setup(tmp_path, scenario="nominal", action=None):
    config = ExecutionConfig(tmp_path / "package", "package", "run", fixture_set=fixtures(scenario))
    runtime = VirtualRuntime()
    provider = SpyProvider(config.fixture_set, action)
    return config, runtime, provider


def run(config, runtime, provider):
    return execute(config, runtime=runtime, provider=provider)


def test_complete_run_and_exact_byte_roundtrip(tmp_path):
    config, runtime, spy = setup(tmp_path)
    result = run(config, runtime, spy)
    assert (result.state, result.termination, result.failure, result.verified) == (
        "completed", "completed", None, True)
    assert tuple(r.example_id for r in spy.requests) == result.dispatched == EXAMPLE_IDS
    assert len({id(r) for r in spy.requests}) == len({id(c) for c in spy.contexts}) == 12
    assert len(result.captures) == len({c.capture_id for c in result.captures}) == 12
    package = EvidencePackage(result.root)
    state = package.verify()
    assert state.captures == result.captures
    assert tuple(c.example_id for c in state.captures) == EXAMPLE_IDS
    assert state.snapshots == ()
    assert all(a.role != "derived" and a.snapshot_id is None for a in state.inventory)
    assert len(state.inventory) == 67  # 6 run sources + 12 inputs + 36 per-case + 12 raw + terminal
    for capture, fixture, request in zip(result.captures, config.fixture_set.entries, spy.requests, strict=True):
        assert package.read_artifact(capture.artifact_reference) == fixture.raw
        input_raw = package.read_artifact(capture.input_reference)
        assert input_raw == request.requirement_text.encode()
        assert request.input_sha256 == sha256(input_raw).hexdigest()
        request_path = f"sources/run/{capture.example_id}/request.json"
        assert parse_metadata(package.read_artifact(request_path)) == asdict(request)
    manifest = parse_metadata(package.read_artifact("sources/run/_run/manifest.json"))
    assert manifest["fixture_sha256"] == config.fixture_set.sha256
    assert manifest["deadline_ms"] == 60_000
    assert not result.unresolved
    terminal = parse_metadata(package.read_artifact("sources/run/_run/terminal.json"))
    assert terminal["committed_capture_count"] == 12


def test_all_prerequisites_precede_first_invocation(tmp_path):
    def action(spy, req, ctx):
        state = EvidencePackage(config.root).verify()
        if len(spy.requests) == 1:
            assert sum(a.role == "input" for a in state.inventory) == 12
            names = {a.path.rsplit("/", 1)[-1] for a in state.inventory}
            assert {"dataset.json", "trusted-policy.txt", "request-template.txt", "fixtures.json",
                    "manifest.json", "execution-plan.json", "request.json", "dispatch.json"} <= names
        return spy.inner.invoke(req, ctx)
    config, runtime, spy = setup(tmp_path, action=action)
    assert run(config, runtime, spy).state == "completed"


def test_mixed_missing_empty_and_malformed_outputs(tmp_path):
    config, runtime, spy = setup(tmp_path, "mixed")
    result = run(config, runtime, spy)
    assert result.state == "completed" and len(spy.requests) == 12
    package = EvidencePackage(result.root)
    state = package.verify()
    for capture, fixture in zip(state.captures, config.fixture_set.entries, strict=True):
        assert capture.outcome == fixture.outcome
        raw_artifacts = [a for a in state.inventory if a.example_id == capture.example_id and a.role == "raw"]
        if fixture.raw is None:
            assert capture.artifact_reference is None and not raw_artifacts
        else:
            assert len(raw_artifacts) == 1
            assert package.read_artifact(capture.artifact_reference) == fixture.raw
    empty = next(a for a in state.inventory if a.role == "raw" and a.example_id == "S02")
    assert empty.byte_length == 0 and (package.root / empty.path).stat().st_size == 0
    assert sum(c.outcome == "timeout" for c in state.captures) == 1
    assert sum(c.outcome == "transport_error" for c in state.captures) == 1


@pytest.mark.parametrize("elapsed,expected", [(59_999, "received"), (60_000, "timeout"), (60_001, "timeout")])
@pytest.mark.parametrize("checkpoint", [False, True])
def test_deadline_boundary(tmp_path, elapsed, expected, checkpoint):
    def action(spy, req, ctx):
        runtime.ms += elapsed
        if checkpoint:
            ctx.checkpoint()
        # Bypass provider checkpoint to exercise coordinator's return-time enforcement.
        fixture = spy.inner.fixture_set.entries[EXAMPLE_IDS.index(req.example_id)]
        from reqguard.evaluation.fake_provider import FakeResponse, correlation_id
        return FakeResponse(req.request_id, req.example_id, correlation_id(req), fixture.raw)
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert result.state == "completed" and len(spy.requests) == 12
    assert all(c.outcome == expected for c in result.captures)
    package = EvidencePackage(result.root)
    late = [a for a in package.verify().inventory if a.path.endswith("late-response.bin")]
    assert len(late) == (12 if expected == "timeout" and not checkpoint else 0)
    fixture_bytes = {f.example_id: f.raw for f in config.fixture_set.entries}
    for artifact in late:
        assert package.read_artifact(artifact.path) == fixture_bytes[artifact.example_id]


@pytest.mark.parametrize("response", [None, b"", {}, "wrong", object()])
def test_invalid_provider_returns_are_unresolved_contract_errors(tmp_path, response):
    config, runtime, spy = setup(tmp_path, action=lambda *_: response)
    result = run(config, runtime, spy)
    assert (result.state, result.termination, result.failure) == ("unresolved", "failed", "provider_contract")
    assert result.unresolved == ("F01",) and not result.captures
    assert len(spy.requests) == 1 and result.verified


def test_invalid_response_identity_at_deadline_is_contract_failure(tmp_path):
    def action(spy, req, ctx):
        response = spy.inner.invoke(req, ctx)
        runtime.ms += 60_000
        return replace(response, example_id="F02")
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert result.failure == "provider_contract" and len(spy.requests) == 1


@pytest.mark.parametrize("error", [RuntimeError("private diagnostic"), TypeError(), OSError()])
def test_undeclared_provider_exception_stops_without_transport_capture(tmp_path, error):
    def action(spy, req, ctx):
        if req.example_id == "F02":
            raise error
        return spy.inner.invoke(req, ctx)
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert result.state == "unresolved" and result.termination == "failed"
    assert len(spy.requests) == 2 and len(result.captures) == 1
    assert result.unresolved == ("F02",)
    assert "private diagnostic" not in str(result)
    assert result.failure == "provider_failure"


@pytest.mark.parametrize("moment", ["before", "during", "after_response", "between"])
def test_cancellation_partial_reporting(tmp_path, monkeypatch, moment):
    def action(spy, req, ctx):
        if moment == "during":
            runtime.ms += 60_000
            runtime.cancelled = True
            ctx.checkpoint()
        response = spy.inner.invoke(req, ctx)
        if moment == "after_response":
            runtime.cancelled = True
        return response
    config, runtime, spy = setup(tmp_path, action=action)
    if moment == "before":
        runtime.cancelled = True
    if moment == "between":
        original = EvidencePackage.register_capture
        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            runtime.cancelled = True
            return result
        monkeypatch.setattr(EvidencePackage, "register_capture", capture)
    result = run(config, runtime, spy)
    assert result.termination == "interrupted" and result.failure == "cancellation"
    assert result.state == ("unresolved" if moment in ("during", "after_response") else "interrupted")
    assert len(spy.requests) == (0 if moment == "before" else 1)
    assert len(result.captures) == (1 if moment == "between" else 0)
    assert not any(c.outcome == "timeout" for c in result.captures)


@pytest.mark.parametrize("field,value", [("deadline_ms", 59_999), ("deadline_ms", True),
    ("package_id", "../bad"), ("evaluation_run_id", ""), ("dirty_state", ""),
    ("evaluated_commit", "main"), ("fixture_set", replace(fixtures(), revision="changed"))])
def test_invalid_configuration_no_creation_or_dispatch(tmp_path, field, value):
    config, runtime, spy = setup(tmp_path)
    with pytest.raises(ValueError):
        run(replace(config, **{field: value}), runtime, spy)
    assert not config.root.exists() and not spy.requests


def test_invalid_dataset_no_creation_or_dispatch(tmp_path):
    config, runtime, spy = setup(tmp_path)
    bad = tmp_path / "dataset.json"
    bad.write_bytes(b"[]")
    with pytest.raises(DatasetValidationError):
        run(replace(config, dataset_path=bad), runtime, spy)
    assert not config.root.exists() and not spy.requests


@pytest.mark.parametrize("boundary", [1, 2, 3, 4, 5, 6, 7, 18, 19, 20, 21, 22, 23, 24, 55])
def test_source_registration_failures(tmp_path, monkeypatch, boundary):
    config, runtime, spy = setup(tmp_path)
    original = EvidencePackage.register_source
    calls = 0
    def register(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == boundary:
            raise EvidenceError("injected registration failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(EvidencePackage, "register_source", register)
    result = run(config, runtime, spy)
    assert calls == boundary and result.termination == "failed" and result.failure == "storage"
    state = EvidencePackage(result.root).verify()
    assert result.captures == state.captures and not state.snapshots
    assert len(spy.requests) == len(set(r.example_id for r in spy.requests))
    assert set(c.example_id for c in state.captures) <= set(r.example_id for r in spy.requests)
    assert set(result.unresolved) == set(result.dispatched) - {c.example_id for c in state.captures}
    if boundary <= 20:
        assert not spy.requests
    if boundary == 55:
        assert len(state.captures) == 12 and result.state == "failed"


@pytest.mark.parametrize("after_commit", [False, True])
def test_capture_registration_failure_preserves_commits(tmp_path, monkeypatch, after_commit):
    config, runtime, spy = setup(tmp_path)
    original = EvidencePackage.register_capture
    def register(self, *args, **kwargs):
        if args[1] == "F02":
            if after_commit:
                original(self, *args, **kwargs)
            raise EvidenceError("injected")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(EvidencePackage, "register_capture", register)
    result = run(config, runtime, spy)
    assert result.termination == "failed" and len(spy.requests) == 2
    assert len(result.captures) == (2 if after_commit else 1)
    assert result.unresolved == (() if after_commit else ("F02",))
    assert EvidencePackage(result.root).verify().captures == result.captures


def test_no_resume_or_existing_root_adoption(tmp_path):
    config, runtime, spy = setup(tmp_path)
    first = run(config, runtime, spy)
    before = {p.relative_to(config.root): p.read_bytes() for p in config.root.rglob("*") if p.is_file()}
    second_spy = SpyProvider(config.fixture_set)
    second = run(config, runtime, second_spy)
    assert first.state == "completed" and second.state == "failed" and not second_spy.requests
    assert before == {p.relative_to(config.root): p.read_bytes() for p in config.root.rglob("*") if p.is_file()}


def test_duplicate_and_cross_example_protection(tmp_path):
    config, runtime, spy = setup(tmp_path)
    result = run(config, runtime, spy)
    package = EvidencePackage(result.root)
    first = result.captures[0]
    before = package.verify()
    for capture_id, example in (("different", "F01"), (first.capture_id, "F02"), ("cross", "F03")):
        with pytest.raises(EvidenceError):
            package.register_capture(capture_id, example, b"", outcome="received",
                input_reference=first.input_reference, provenance_references=first.provenance_references)
    assert package.verify() == before


def test_final_verification_failure_never_reports_completion(tmp_path, monkeypatch):
    config, runtime, spy = setup(tmp_path)
    original = EvidencePackage.verify
    def verify(self):
        if (self.root / "sources/run/_run/terminal.json").exists():
            raise EvidenceError("injected final verification failure")
        return original(self)
    with monkeypatch.context() as patch:
        patch.setattr(EvidencePackage, "verify", verify)
        result = run(config, runtime, spy)
    assert result.state == "failed" and not result.verified and len(result.captures) == 12
    assert len(EvidencePackage(result.root).verify().captures) == 12


def test_fixture_mismatch_stops_without_capture(tmp_path):
    config, runtime, spy = setup(tmp_path)
    spy.inner = DeterministicFakeProvider(fixtures("empty"))
    result = run(config, runtime, spy)
    assert result.state == "unresolved" and result.failure == "provider_contract"
    assert len(spy.requests) == 1 and not result.captures


def test_transport_error_at_deadline_becomes_timeout(tmp_path):
    def action(spy, req, ctx):
        if req.example_id == "F01":
            runtime.ms += 60_000
            raise ProviderTransportError()
        return spy.inner.invoke(req, ctx)
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert result.state == "completed" and result.captures[0].outcome == "timeout"
    assert len(spy.requests) == 12


def test_keyboard_interrupt_retains_partial_package(tmp_path):
    def action(spy, req, ctx):
        if req.example_id == "F02":
            raise KeyboardInterrupt()
        return spy.inner.invoke(req, ctx)
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert (result.state, result.termination, result.unresolved) == ("unresolved", "interrupted", ("F02",))
    assert len(result.captures) == 1 and len(spy.requests) == 2


def test_dispatch_exception_after_commit_is_unresolved_without_invocation(tmp_path, monkeypatch):
    config, runtime, spy = setup(tmp_path)
    original = EvidencePackage.register_source
    def register(self, name, *args, **kwargs):
        result = original(self, name, *args, **kwargs)
        if name == "dispatch.json":
            raise EvidenceError("after dispatch commit")
        return result
    monkeypatch.setattr(EvidencePackage, "register_source", register)
    result = run(config, runtime, spy)
    assert result.unresolved == ("F01",) and result.verified and not spy.requests
    assert not result.captures and result.state == "unresolved"


def test_create_failure_has_no_dispatch(tmp_path, monkeypatch):
    config, runtime, spy = setup(tmp_path)
    def fail(*args, **kwargs):
        raise EvidenceError("create failure")
    monkeypatch.setattr(EvidencePackage, "create", fail)
    result = run(config, runtime, spy)
    assert result.state == "failed" and result.failure == "storage"
    assert not result.captures and not result.dispatched and not spy.requests


def test_coordinator_clock_failure_after_provider(tmp_path):
    def action(spy, req, ctx):
        response = spy.inner.invoke(req, ctx)
        runtime.ms = -1
        return response
    config, runtime, spy = setup(tmp_path, action=action)
    result = run(config, runtime, spy)
    assert result.state == "unresolved" and result.failure == "coordinator"
    assert not result.captures and len(spy.requests) == 1


@pytest.mark.parametrize("signal,elapsed,outcome,origin", [
    ("timeout_raised", 0, "timeout", "simulated_provider_timeout"),
    ("timeout_raised", 59_999, "timeout", "simulated_provider_timeout"),
    ("checkpoint", 60_000, "timeout", "observed_deadline_expiry"),
    ("response_returned", 60_000, "timeout", "observed_deadline_expiry"),
    ("response_returned", 60_001, "timeout", "observed_deadline_expiry"),
    ("transport_error_raised", 0, "transport_error", None),
    ("transport_error_raised", 60_000, "timeout", "observed_deadline_expiry"),
    ("response_returned", 0, "received", None),
])
def test_timeout_and_correlation_provenance(tmp_path, signal, elapsed, outcome, origin):
    returned = []

    def action(spy, req, ctx):
        if req.example_id != "F01":
            return spy.inner.invoke(req, ctx)
        if signal == "response_returned":
            response = spy.inner.invoke(req, ctx)
            returned.append(response)
            runtime.ms += elapsed
            return response
        runtime.ms += elapsed
        if signal == "checkpoint":
            ctx.checkpoint()
            pytest.fail("Checkpoint must expire at the deadline")
        if signal == "timeout_raised":
            return spy.inner.invoke(req, ctx)
        raise ProviderTransportError()

    config, runtime, spy = setup(tmp_path, "timeout" if signal == "timeout_raised" else "nominal", action)
    result = run(config, runtime, spy)
    assert result.state == "completed" and result.verified and len(spy.requests) == 12
    assert len(result.captures) == 12 and result.captures[0].outcome == outcome
    package = EvidencePackage(result.root)
    provenance = parse_metadata(package.read_artifact("sources/run/F01/capture.json"))
    assert provenance["version"] == "rg07d-capture-v2"
    assert provenance["provider_return_status"] == ("timeout_raised" if signal == "checkpoint" else signal)
    assert provenance["elapsed_ms"] == elapsed
    assert provenance["deadline_expired"] is (elapsed >= 60_000)
    assert provenance["timeout_origin"] == origin
    assert provenance["outcome"] == outcome
    assert provenance["expected_correlation_id"] == correlation_id(spy.requests[0])
    assert provenance["returned_correlation_id"] == (returned[0].correlation_id if returned else None)
    assert "correlation_id" not in provenance  # No ambiguous legacy field in v2.
    if outcome != "received":
        assert result.captures[0].artifact_reference is None
    if returned and outcome == "timeout":
        assert package.read_artifact(provenance["late_response_reference"]) == returned[0].raw
