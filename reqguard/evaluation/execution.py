"""Sequential cooperative D2 execution using only the public D1 storage API."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import time

from .dataset import DATASET_PATH, DATASET_SHA256, DATASET_VERSION, EXAMPLE_IDS, load_dataset
from .evidence import CaptureRecord, EvidenceError, EvidencePackage, PackageIdentity, serialize_metadata
from .fake_provider import (
    REQUEST_TEMPLATE, TRUSTED_POLICY, DeterministicFakeProvider, FakeProvider, FakeRequest,
    FixtureSet, ProviderContractError, ProviderTimeout, ProviderTransportError,
    correlation_id, fixtures, validate_fixtures, validate_request, validate_response,
)
from .hard_fail import RULE_VERSION, trusted_task_hash


EXECUTION_VERSION = "rg07d-execution-v1"
PLAN_VERSION = "rg07d-plan-v1"
DISPATCH_VERSION = "rg07d-dispatch-v1"
CAPTURE_VERSION = "rg07d-capture-v2"
TERMINAL_VERSION = "rg07d-terminal-v1"
DEADLINE_MS = 60_000


class ExecutionCancelled(Exception):
    """Cooperative cancellation, never a provider timeout."""


class ExecutionRuntime:
    """Override clock and cancellation methods for virtual time or cancellation.

    A provider must call context.checkpoint() while working. This cannot forcibly
    terminate arbitrary blocking code. The coordinator also checks upon return.
    """

    def monotonic_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000

    def utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def check_cancelled(self) -> None:
        pass


@dataclass(frozen=True)
class AttemptContext:
    runtime: ExecutionRuntime
    deadline_ms: int

    def checkpoint(self) -> None:
        self.runtime.check_cancelled()  # Cancellation takes precedence over timeout.
        if self.runtime.monotonic_ms() >= self.deadline_ms:
            raise ProviderTimeout()


@dataclass(frozen=True)
class ExecutionConfig:
    root: Path
    package_id: str
    evaluation_run_id: str
    dataset_path: Path = DATASET_PATH
    fixture_set: FixtureSet = fixtures()
    deadline_ms: int = DEADLINE_MS
    baseline_commit: str = "unavailable"
    evaluated_commit: str = "unavailable"
    dirty_state: str = "unavailable"


@dataclass(frozen=True)
class ExecutionResult:
    root: Path
    state: str
    termination: str
    captures: tuple[CaptureRecord, ...]
    dispatched: tuple[str, ...]
    unresolved: tuple[str, ...]
    verified: bool
    failure: str | None = None


def _validate_config(config):
    if type(config) is not ExecutionConfig:
        raise ValueError("Expected ExecutionConfig")
    for token in (config.package_id, config.evaluation_run_id):
        if type(token) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", token) is None:
            raise ValueError("Invalid execution identity")
    if type(config.root) is not Path and not isinstance(config.root, Path):
        raise ValueError("Root must be a Path")
    if not isinstance(config.dataset_path, Path):
        raise ValueError("Dataset path must be a Path")
    if type(config.deadline_ms) is not int or config.deadline_ms != DEADLINE_MS:
        raise ValueError("Deadline must be exactly 60000 ms")
    for commit in (config.baseline_commit, config.evaluated_commit):
        if type(commit) is not str or (commit != "unavailable" and
                                     re.fullmatch(r"[a-f0-9]{40}", commit) is None):
            raise ValueError("Invalid commit provenance")
    if type(config.dirty_state) is not str or not config.dirty_state.strip():
        raise ValueError("Dirty-state provenance required")
    validate_fixtures(config.fixture_set)
    if sha256(TRUSTED_POLICY.encode()).hexdigest() != trusted_task_hash():
        raise ValueError("Frozen policy mismatch")


def _clock(runtime):
    value = runtime.monotonic_ms()
    if type(value) is not int or value < 0:
        raise ValueError("Clock must supply nonnegative integer milliseconds")
    return value


def _utc(runtime):
    value = runtime.utc_now()
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("Clock must supply UTC with Z suffix")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def execute(config: ExecutionConfig, *, provider: FakeProvider | None = None,
            runtime: ExecutionRuntime | None = None) -> ExecutionResult:
    """Create a fresh package and execute once. Validation errors precede creation.

    Operational failures return partial results; an intent without a committed
    capture forces state=unresolved, with termination=failed/interrupted. A failed
    final verification is never a completed execution. No resume or repair occurs.
    """
    _validate_config(config)
    records = load_dataset(config.dataset_path)
    dataset_raw = config.dataset_path.read_bytes()
    # Validate the bytes actually registered, including a possible read race.
    if sha256(dataset_raw).hexdigest().upper() != DATASET_SHA256:
        raise ValueError("Dataset changed during validation")
    provider = provider if provider is not None else DeterministicFakeProvider(config.fixture_set)
    if not callable(getattr(provider, "invoke", None)):
        raise ProviderContractError("Provider must implement invoke")
    runtime = runtime if runtime is not None else ExecutionRuntime()
    start_utc = _utc(runtime)
    _clock(runtime)
    root = config.root.absolute()
    package = None
    dispatched = []
    captures = ()
    verified = False
    phase = "storage"
    termination = "failed"
    failure = None

    def source(name, value, *, example=None, role="provenance", raw=False):
        return package.register_source(name, value if raw else serialize_metadata(value),
                                       role=role, example_id=example)

    try:
        runtime.check_cancelled()
        package = EvidencePackage.create(root, PackageIdentity(config.package_id, config.evaluation_run_id))
        source("dataset.json", dataset_raw, role="source", raw=True)
        source("trusted-policy.txt", TRUSTED_POLICY.encode(), role="source", raw=True)
        source("request-template.txt", REQUEST_TEMPLATE, role="source", raw=True)
        source("fixtures.json", config.fixture_set.to_bytes(), role="source", raw=True)
        manifest = {
            "version": EXECUTION_VERSION, "evaluation_run_id": config.evaluation_run_id,
            "start_utc": start_utc, "specification_version": RULE_VERSION,
            "dataset_version": DATASET_VERSION, "dataset_sha256": DATASET_SHA256,
            "input_sha256": {r.example_id: sha256(r.requirement_text.encode()).hexdigest() for r in records},
            "baseline_commit": config.baseline_commit, "evaluated_commit": config.evaluated_commit,
            "dirty_state": config.dirty_state, "evaluator_revision": "not-invoked-D2",
            "adapter_revision": sha256(Path(__file__).read_bytes()).hexdigest(),
            "provider": "dedicated-deterministic-fake", "model_revision": config.fixture_set.revision,
            "fixture_sha256": config.fixture_set.sha256, "scenario": config.fixture_set.scenario,
            "generation_settings": {"temperature": None, "token_limit": None, "defaults": "none-offline"},
            "seed_support": {"seed": None, "supported": False}, "trusted_task_policy": TRUSTED_POLICY,
            "trusted_task_sha256": trusted_task_hash(),
            "request_template_sha256": sha256(REQUEST_TEMPLATE).hexdigest(),
            "category_order": ["functional", "ambiguous", "safety"], "deadline_ms": DEADLINE_MS,
            "disabled_tool_capabilities": True, "rule_version": RULE_VERSION,
            "rubric_version": RULE_VERSION, "threshold_version": RULE_VERSION,
            "annotator_identifiers": [],
        }
        source("manifest.json", manifest)
        source("execution-plan.json", {"version": PLAN_VERSION, "example_ids": list(EXAMPLE_IDS),
            "attempts_per_example": 1, "retries": 0, "deadline_ms": DEADLINE_MS,
            "fixture_sha256": config.fixture_set.sha256})
        inputs = {r.example_id: source("input.txt", r.requirement_text.encode(),
                  example=r.example_id, role="input", raw=True).path for r in records}

        for ordinal, record in enumerate(records, 1):
            phase = "coordinator"
            runtime.check_cancelled()
            request = FakeRequest(config.evaluation_run_id, f"request-{record.example_id}",
                record.example_id, record.requirement_text,
                sha256(record.requirement_text.encode()).hexdigest(), config.fixture_set.sha256)
            validate_request(request, config.fixture_set)
            phase = "storage"
            request_source = source("request.json", asdict(request), example=record.example_id,
                                    role="source")
            phase = "coordinator"
            dispatch_ms, dispatch_utc = _clock(runtime), _utc(runtime)
            context = AttemptContext(runtime, dispatch_ms + DEADLINE_MS)
            phase = "storage"
            intent = source("dispatch.json", {"version": DISPATCH_VERSION, "ordinal": ordinal,
                "example_id": record.example_id, "request_reference": request_source.path,
                "dispatch_utc": dispatch_utc, "dispatch_monotonic_ms": dispatch_ms,
                "deadline_monotonic_ms": context.deadline_ms, "attempt": 1}, example=record.example_id)
            dispatched.append(record.example_id)
            phase = "provider"
            response = None
            outcome = "received"
            provider_return_status = "response_returned"
            try:
                response = provider.invoke(request, context)
            except ProviderTimeout:
                outcome = "timeout"
                provider_return_status = "timeout_raised"
            except ProviderTransportError:
                outcome = "transport_error"
                provider_return_status = "transport_error_raised"
            # Invalid types/identities remain contract errors even at the deadline.
            if response is not None or outcome == "received":
                validate_response(response, request)
            phase = "coordinator"
            runtime.check_cancelled()
            end_ms, end_utc = _clock(runtime), _utc(runtime)
            if end_ms < dispatch_ms:
                raise ValueError("Monotonic clock moved backwards")
            late = end_ms >= context.deadline_ms
            if late:
                outcome = "timeout"
            timeout_origin = ("observed_deadline_expiry" if late else
                              "simulated_provider_timeout" if outcome == "timeout" else None)
            raw = response.raw if response is not None and outcome == "received" else None
            phase = "storage"
            late_reference = None
            if response is not None and late:
                # Timeout capture has no raw artifact, but late received bytes must survive.
                late_reference = source("late-response.bin", response.raw, role="source",
                                        example=record.example_id, raw=True).path
            provenance = source("capture.json", {"version": CAPTURE_VERSION,
                "example_id": record.example_id, "request_reference": request_source.path,
                "dispatch_reference": intent.path, "dispatch_utc": dispatch_utc, "end_utc": end_utc,
                "dispatch_monotonic_ms": dispatch_ms, "end_monotonic_ms": end_ms,
                "elapsed_ms": end_ms - dispatch_ms, "deadline_ms": DEADLINE_MS,
                "provider_return_status": provider_return_status,
                "deadline_expired": late, "timeout_origin": timeout_origin,
                "expected_correlation_id": correlation_id(request),
                "returned_correlation_id": None if response is None else response.correlation_id,
                "outcome": outcome,
                "raw_sha256": None if raw is None else sha256(raw).hexdigest(),
                "raw_byte_length": None if raw is None else len(raw),
                "late_response_reference": late_reference,
                "received_sha256": None if response is None else sha256(response.raw).hexdigest(),
                "received_byte_length": None if response is None else len(response.raw)},
                example=record.example_id)
            capture = package.register_capture(f"capture-{ordinal:02}-{record.example_id}",
                record.example_id, raw, outcome=outcome, input_reference=inputs[record.example_id],
                provenance_references=(intent.path, provenance.path))
            captures = (*captures, capture)

        runtime.check_cancelled()
        source("terminal.json", {"version": TERMINAL_VERSION, "state": "completed",
            "capture_ids": [c.capture_id for c in captures], "committed_capture_count": len(captures),
            "end_utc": _utc(runtime)})
        state = package.verify()
        if len(state.captures) != 12 or tuple(c.example_id for c in state.captures) != EXAMPLE_IDS:
            raise EvidenceError("Incomplete or unordered execution package")
        captures, verified, termination = state.captures, True, "completed"
    except (ExecutionCancelled, KeyboardInterrupt):
        termination, failure = "interrupted", "cancellation"
    except ProviderContractError:
        failure = "provider_contract"
    except (EvidenceError, OSError):
        failure = "provider_failure" if phase == "provider" else "storage"
    except Exception:
        # Unknown provider exceptions are operational failures, never transport errors.
        failure = "provider_failure" if phase == "provider" else "coordinator"

    if termination != "completed" and package is not None:
        try:
            # Read-only reconciliation handles exceptions occurring after a D1 commit.
            state = package.verify()
            captures, verified = state.captures, True
            dispatched = [e for e in EXAMPLE_IDS if any(
                a.example_id == e and a.path.endswith("/dispatch.json") for a in state.inventory)]
        except Exception:
            verified = False  # Existing evidence is never repaired or overwritten.
    committed = {c.example_id for c in captures}
    unresolved = tuple(e for e in dispatched if e not in committed)
    return ExecutionResult(root, "unresolved" if unresolved else termination, termination,
                           captures, tuple(dispatched), unresolved, verified, failure)
