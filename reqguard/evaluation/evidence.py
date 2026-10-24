"""Offline file evidence, independent of the accepted evaluator manifest.

Single cooperating writer; readers fail closed during incomplete transactions.
Checksums detect inconsistency, not authenticity against a party replacing both
evidence and checksums. No model dispatch, interpretation or annotation occurs.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

from .dataset import DATASET_SHA256, DATASET_VERSION, load_dataset


PACKAGE_VERSION = "rg-evidence-package-v1"


class EvidenceError(ValueError):
    """Invalid, unavailable, inconsistent or immutable evidence operation."""


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def serialize_metadata(value: object) -> bytes:
    """Canonical package JSON: sorted keys, compact, UTF-8, no BOM/newline.

    Only JSON values are accepted; no key coercion, NaN, tuples or surrogates.
    This is NOT the frozen dataset's different serialization protocol.
    """
    def check(item):
        if isinstance(item, dict):
            _require(all(type(k) is str for k in item), "JSON keys must be strings")
            for key, child in item.items():
                key.encode("utf-8", "strict")
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        else:
            _require(item is None or type(item) in (str, int, float, bool),
                     "Expected JSON values")
    try:
        check(value)
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise EvidenceError("Cannot serialize strict JSON metadata") from exc


def parse_metadata(raw: bytes) -> object:
    """Strict UTF-8 JSON, rejecting duplicate keys at every depth and NaN."""
    _require(type(raw) is bytes, "Metadata must be UTF-8 bytes")
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def constant(_):
        raise EvidenceError("Nonfinite JSON number")

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                           parse_constant=constant)
        serialize_metadata(value)  # Also reject overflowed floats and escaped surrogates.
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise EvidenceError("Invalid strict UTF-8 JSON metadata") from exc


def _token(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value),
             "Invalid identity token")


def _relative(value):
    _require(type(value) is str and bool(value), "Invalid relative path")
    for part in value.split("/"):
        _require(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}", part)
                 and not part.endswith(".") and
                 part.split(".")[0].upper() not in
                 {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)),
                  *(f"LPT{i}" for i in range(10))}, "Unsafe package-relative path")


@dataclass(frozen=True)
class PackageIdentity:
    package_id: str
    evaluation_run_id: str
    dataset_version: str = DATASET_VERSION
    dataset_sha256: str = DATASET_SHA256
    version: str = PACKAGE_VERSION


@dataclass(frozen=True)
class Artifact:
    path: str
    sha256: str
    byte_length: int
    evaluation_run_id: str
    example_id: str | None
    role: str
    snapshot_id: str | None = None


@dataclass(frozen=True)
class CaptureRecord:
    capture_id: str
    evaluation_run_id: str
    example_id: str
    input_reference: str
    provenance_references: tuple[str, ...]
    outcome: str
    artifact_reference: str | None


@dataclass(frozen=True)
class DerivedSnapshot:
    snapshot_id: str
    replay_id: str
    evaluation_run_id: str
    parent_snapshot_id: str | None
    supersedes_snapshot_id: str | None
    capture_ids: tuple[str, ...]
    artifact_paths: tuple[str, ...] = ()
    finalized: bool = False
    seal: Artifact | None = None


@dataclass(frozen=True)
class PackageMetadata:
    identity: PackageIdentity
    inventory: tuple[Artifact, ...] = ()
    captures: tuple[CaptureRecord, ...] = ()
    snapshots: tuple[DerivedSnapshot, ...] = ()


def _record(cls, value):
    _require(type(value) is dict and set(value) == {f.name for f in fields(cls)},
             f"Unexpected fields for {cls.__name__}")
    return cls(**value)


def _array(value):
    _require(type(value) is list, "Expected JSON array")
    return value


def _decode(value):
    _record(PackageMetadata, value)
    captures = []
    for item in _array(value["captures"]):
        record = _record(CaptureRecord, item)
        captures.append(CaptureRecord(**{
            **asdict(record), "provenance_references": tuple(_array(item["provenance_references"]))}))
    snapshots = []
    for item in _array(value["snapshots"]):
        record = _record(DerivedSnapshot, item)
        snapshots.append(DerivedSnapshot(**{
            **asdict(record), "capture_ids": tuple(_array(item["capture_ids"])),
            "artifact_paths": tuple(_array(item["artifact_paths"])),
            "seal": _record(Artifact, item["seal"]) if item["seal"] is not None else None}))
    return PackageMetadata(_record(PackageIdentity, value["identity"]),
                           tuple(_record(Artifact, x) for x in _array(value["inventory"])),
                           tuple(captures), tuple(snapshots))


def _json_record(record):
    """Convert dataclass tuple fields to JSON arrays without custom encoders."""
    def convert(item):
        if isinstance(item, dict):
            return {key: convert(value) for key, value in item.items()}
        if isinstance(item, (tuple, list)):
            return [convert(value) for value in item]
        return item
    return convert(asdict(record))


class EvidencePackage:
    """Storage lifecycle. Paths and IDs are portable, case-insensitively unique.

    Source registration freezes after the first finalized snapshot. Derived
    snapshots may then be appended, each with an independent replay identity.
    API immutability is not OS access control. Hostile concurrent filesystem
    replacement and power-loss durability require a stronger storage backend.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()
        self._path("package.json")

    def _path(self, relative):
        _relative(relative)
        target = self.root.joinpath(*relative.split("/"))
        for part in (*reversed(target.parents), target):
            _require(not part.is_symlink() and not part.is_junction(),
                     "Symlinks/junctions are forbidden")
        _require(target.resolve().is_relative_to(self.root.resolve()), "Path escape")
        return target

    @classmethod
    def create(cls, root: str | Path, identity: PackageIdentity):
        package = cls(root)
        state = PackageMetadata(identity)
        package._validate(state)
        try:
            package.root.mkdir()  # Existing directories are never adopted or overwritten.
            package._atomic("package.json", serialize_metadata(_json_record(state)), replace=False)
        except OSError as exc:
            raise EvidenceError("Cannot create new package") from exc
        return package

    def _atomic(self, relative, raw, *, replace=False):
        """Flush a same-directory temporary file, then publish complete bytes."""
        target = self._path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".staging-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._path(relative)
            if replace:
                os.replace(temporary, target)
            else:
                os.link(temporary, target)  # Atomic create-if-absent; never replace evidence.
        finally:
            Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def _writer(self):
        lock = self._path("writer.lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as exc:
            raise EvidenceError("Package writer unavailable (possibly stale lock)") from exc
        os.close(fd)
        try:
            yield
        finally:
            lock.unlink()

    def _validate(self, state):
        identity = state.identity
        _require(type(identity) is PackageIdentity, "Expected package identity")
        _require(identity.version == PACKAGE_VERSION, "Unsupported package version")
        _token(identity.package_id)
        _token(identity.evaluation_run_id)
        _require(identity.dataset_version == DATASET_VERSION and
                 identity.dataset_sha256 == DATASET_SHA256, "Inconsistent frozen dataset identity")
        inputs = {r.example_id: r.requirement_text.encode("utf-8") for r in load_dataset()}
        inventory = {}
        for artifact in state.inventory:
            _relative(artifact.path)
            _require(artifact.path.casefold() not in {p.casefold() for p in inventory},
                     "Duplicate inventory path")
            _require(type(artifact.sha256) is str and
                     re.fullmatch(r"[0-9a-f]{64}", artifact.sha256), "Invalid SHA-256")
            _require(type(artifact.byte_length) is int and artifact.byte_length >= 0,
                     "Invalid byte length")
            _require(artifact.evaluation_run_id == identity.evaluation_run_id, "Cross-run artifact")
            _require(artifact.example_id is None or artifact.example_id in inputs,
                     "Unknown example identity")
            _require(artifact.role in ("input", "provenance", "source", "raw", "derived"),
                     "Unknown artifact role")
            if artifact.role == "derived":
                _token(artifact.snapshot_id)
                prefix = f"derived/{artifact.snapshot_id}"
            else:
                _require(artifact.snapshot_id is None, "Source cannot belong to a snapshot")
                prefix = "sources"
            prefix += f"/{identity.evaluation_run_id}/{artifact.example_id or '_run'}/"
            _require(artifact.path.startswith(prefix) and "/" not in artifact.path[len(prefix):],
                     "Artifact path identity mismatch")
            if artifact.role == "input":
                _require(artifact.example_id in inputs, "Input needs an example")
                raw = inputs[artifact.example_id]
                _require(artifact.sha256 == sha256(raw).hexdigest() and
                         artifact.byte_length == len(raw), "Frozen input mismatch")
            inventory[artifact.path] = artifact
        captures = {}
        captured_examples = set()
        for capture in state.captures:
            _token(capture.capture_id)
            _require(capture.capture_id.casefold() not in {c.casefold() for c in captures},
                     "Duplicate capture identity")
            _require(capture.evaluation_run_id == identity.evaluation_run_id and
                     capture.example_id in inputs, "Cross-run/example capture")
            _require(capture.example_id not in captured_examples, "Duplicate example capture")
            captured_examples.add(capture.example_id)
            _require(capture.outcome in ("received", "timeout", "transport_error"),
                     "Unknown capture outcome")
            _require(bool(capture.provenance_references) and
                     len(set(capture.provenance_references)) == len(capture.provenance_references),
                     "Missing/duplicate provenance references")
            refs = [(capture.input_reference, "input"),
                    *((p, "provenance") for p in capture.provenance_references)]
            if capture.outcome == "received":
                _require(capture.artifact_reference ==
                         f"sources/{identity.evaluation_run_id}/{capture.example_id}/{capture.capture_id}.bin",
                         "Received output must retain its capture identity")
                refs.append((capture.artifact_reference, "raw"))
            else:
                _require(capture.artifact_reference is None, "Missing output cannot have bytes")
            for path, role in refs:
                _relative(path)
                artifact = inventory.get(path)
                _require(artifact is not None and artifact.role == role and
                         (artifact.example_id == capture.example_id or
                          (role == "provenance" and artifact.example_id is None)),
                         "Broken/cross-example capture reference")
            captures[capture.capture_id] = capture
        raw_refs = [c.artifact_reference for c in captures.values() if c.artifact_reference is not None]
        _require(len(raw_refs) == len(set(raw_refs)) and set(raw_refs) ==
                 {a.path for a in state.inventory if a.role == "raw"}, "Unowned/duplicate raw output")
        snapshots = {}
        replays = set()
        derived_refs = []
        for snapshot in state.snapshots:
            _token(snapshot.snapshot_id)
            _token(snapshot.replay_id)
            _require(snapshot.snapshot_id.casefold() not in
                     {s.casefold() for s in snapshots} and snapshot.replay_id.casefold() not in replays,
                     "Duplicate snapshot/replay identity")
            _require(snapshot.replay_id.casefold() != identity.evaluation_run_id.casefold() and
                     snapshot.replay_id.casefold() not in {c.casefold() for c in captures},
                     "Capture and replay identities must be independent")
            _require(snapshot.evaluation_run_id == identity.evaluation_run_id, "Cross-run snapshot")
            for ref in (snapshot.parent_snapshot_id, snapshot.supersedes_snapshot_id):
                if ref is not None:
                    _token(ref)
                    _require(ref in snapshots and snapshots[ref].finalized,
                             "Broken snapshot lineage; references must precede and be finalized")
            _require(len(set(snapshot.capture_ids)) == len(snapshot.capture_ids) and
                     all(c in captures for c in snapshot.capture_ids), "Broken/duplicate snapshot capture")
            for path in snapshot.artifact_paths:
                _relative(path)
                artifact = inventory.get(path)
                _require(artifact is not None and artifact.snapshot_id == snapshot.snapshot_id and
                         (artifact.example_id is None or artifact.example_id in
                          {captures[c].example_id for c in snapshot.capture_ids}),
                         "Broken/cross-example derived reference")
                derived_refs.append(path)
            _require(type(snapshot.finalized) is bool and
                     snapshot.finalized == (snapshot.seal is not None), "Inconsistent snapshot seal")
            if snapshot.seal is not None:
                seal = snapshot.seal
                _require(seal.path == f"seals/{snapshot.snapshot_id}.json" and
                         seal.role == "seal" and seal.example_id is None and
                         seal.snapshot_id == snapshot.snapshot_id and
                         seal.evaluation_run_id == identity.evaluation_run_id and
                         type(seal.byte_length) is int and seal.byte_length >= 0 and
                         type(seal.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", seal.sha256),
                         "Invalid integrity seal descriptor")
            snapshots[snapshot.snapshot_id] = snapshot
            replays.add(snapshot.replay_id.casefold())
        _require(len(derived_refs) == len(set(derived_refs)) and set(derived_refs) ==
                 {a.path for a in state.inventory if a.role == "derived"},
                 "Unowned/duplicate derived inventory")

    def _seal_bytes(self, state, snapshot):
        # No seal descriptor is hashed into itself; unrelated snapshots are excluded.
        record = _json_record(snapshot)
        record.pop("seal")
        record["finalized"] = True
        return serialize_metadata({
            "identity": asdict(state.identity),
            "inventory": [_json_record(a) for a in state.inventory
                          if a.snapshot_id is None or a.snapshot_id == snapshot.snapshot_id],
            "captures": [_json_record(c) for c in state.captures], "snapshot": record})

    def _checked_bytes(self, artifact):
        raw = self._path(artifact.path).read_bytes()
        _require(len(raw) == artifact.byte_length and sha256(raw).hexdigest() == artifact.sha256,
                 f"Artifact integrity mismatch: {artifact.path}")
        return raw

    def verify(self) -> PackageMetadata:
        """Read-only full verification. Never repairs, creates or normalizes files."""
        try:
            state = _decode(parse_metadata(self._path("package.json").read_bytes()))
            self._validate(state)
            _require(self._path("package.json").read_bytes() ==
                     serialize_metadata(_json_record(state)), "Noncanonical package metadata")
            expected = {"package.json"}
            for artifact in state.inventory:
                self._checked_bytes(artifact)
                expected.add(artifact.path)
            for snapshot in state.snapshots:
                if snapshot.seal is not None:
                    raw = self._checked_bytes(snapshot.seal)
                    parse_metadata(raw)
                    _require(raw == self._seal_bytes(state, snapshot), "Modified finalized evidence")
                    expected.add(snapshot.seal.path)
            def walk_error(exc):
                raise EvidenceError("Cannot inspect package inventory") from exc

            for directory, dirs, files in os.walk(self.root, followlinks=False, onerror=walk_error):
                for name in dirs + files:
                    path = Path(directory, name).relative_to(self.root).as_posix()
                    target = self._path(path)
                    if not target.is_dir():
                        _require(target.is_file() and (path in expected or path == "writer.lock"),
                                 "Unexpected package file")
            return state
        except (OSError, TypeError, KeyError, RecursionError) as exc:
            raise EvidenceError("Cannot verify evidence package") from exc

    def read_artifact(self, path: str) -> bytes:
        _relative(path)
        state = self.verify()
        artifact = next((a for a in state.inventory if a.path == path), None)
        if artifact is None:
            artifact = next((s.seal for s in state.snapshots if s.seal and s.seal.path == path), None)
        _require(artifact is not None, "Artifact not in inventory")
        try:
            return self._checked_bytes(artifact)
        except OSError as exc:
            raise EvidenceError("Cannot read artifact") from exc

    def _commit(self, state, additions):
        try:
            self._validate(state)
            metadata = serialize_metadata(_json_record(state))
        except (TypeError, KeyError) as exc:
            raise EvidenceError("Invalid evidence registration") from exc
        created = []
        try:
            for artifact, raw in additions:
                self._atomic(artifact.path, raw)
                created.append(artifact.path)
            self._atomic("package.json", metadata, replace=True)
        except (OSError, EvidenceError) as exc:
            for path in created:
                self._path(path).unlink()
            raise EvidenceError("Atomic evidence transaction failed") from exc

    def _artifact(self, path, raw, state, example_id, role, snapshot_id=None):
        _require(type(raw) is bytes, "Artifact must be untouched bytes")
        return Artifact(path, sha256(raw).hexdigest(), len(raw),
                        state.identity.evaluation_run_id, example_id, role, snapshot_id)

    def register_source(self, name: str, raw: bytes, *, role: str = "source",
                        example_id: str | None = None) -> Artifact:
        _relative(name)
        _require("/" not in name and role in ("source", "input", "provenance"),
                 "Invalid source registration")
        with self._writer():
            state = self.verify()
            _require(not any(s.finalized for s in state.snapshots), "Source evidence is frozen")
            path = f"sources/{state.identity.evaluation_run_id}/{example_id or '_run'}/{name}"
            artifact = self._artifact(path, raw, state, example_id, role)
            updated = PackageMetadata(state.identity, tuple(sorted((*state.inventory, artifact),
                                     key=lambda a: a.path)), state.captures, state.snapshots)
            self._commit(updated, [(artifact, raw)])
            return artifact

    def register_capture(self, capture_id: str, example_id: str, raw: bytes | None, *,
                         outcome: str, input_reference: str,
                         provenance_references: tuple[str, ...]) -> CaptureRecord:
        _token(capture_id)
        _require((outcome == "received" and type(raw) is bytes) or
                 (outcome in ("timeout", "transport_error") and raw is None),
                 "Inconsistent capture outcome versus bytes")
        with self._writer():
            state = self.verify()
            _require(not any(s.finalized for s in state.snapshots), "Source evidence is frozen")
            path = None
            additions = []
            inventory = state.inventory
            if raw is not None:
                path = f"sources/{state.identity.evaluation_run_id}/{example_id}/{capture_id}.bin"
                artifact = self._artifact(path, raw, state, example_id, "raw")
                additions.append((artifact, raw))
                inventory = tuple(sorted((*inventory, artifact), key=lambda a: a.path))
            capture = CaptureRecord(capture_id, state.identity.evaluation_run_id, example_id,
                                    input_reference, tuple(provenance_references), outcome, path)
            updated = PackageMetadata(state.identity, inventory,
                                      tuple(sorted((*state.captures, capture), key=lambda c: c.capture_id)),
                                      state.snapshots)
            self._commit(updated, additions)
            return capture

    def create_snapshot(self, snapshot_id: str, replay_id: str, *, capture_ids: tuple[str, ...],
                        parent_snapshot_id: str | None = None,
                        supersedes_snapshot_id: str | None = None) -> DerivedSnapshot:
        with self._writer():
            state = self.verify()
            snapshot = DerivedSnapshot(snapshot_id, replay_id, state.identity.evaluation_run_id,
                                       parent_snapshot_id, supersedes_snapshot_id, tuple(capture_ids))
            self._commit(PackageMetadata(state.identity, state.inventory, state.captures,
                                         (*state.snapshots, snapshot)), [])
            return snapshot

    def _snapshot(self, state, snapshot_id):
        snapshot = next((s for s in state.snapshots if s.snapshot_id == snapshot_id), None)
        _require(snapshot is not None and not snapshot.finalized, "Unknown/finalized snapshot")
        return snapshot

    def register_derived(self, snapshot_id: str, name: str, raw: bytes, *,
                         example_id: str | None = None) -> Artifact:
        _relative(name)
        _require("/" not in name, "Expected artifact basename")
        with self._writer():
            state = self.verify()
            snapshot = self._snapshot(state, snapshot_id)
            path = f"derived/{snapshot_id}/{state.identity.evaluation_run_id}/{example_id or '_run'}/{name}"
            artifact = self._artifact(path, raw, state, example_id, "derived", snapshot_id)
            updated_snapshot = DerivedSnapshot(**{**asdict(snapshot),
                "artifact_paths": tuple(sorted((*snapshot.artifact_paths, path)))})
            updated = PackageMetadata(state.identity,
                tuple(sorted((*state.inventory, artifact), key=lambda a: a.path)), state.captures,
                tuple(updated_snapshot if s == snapshot else s for s in state.snapshots))
            self._commit(updated, [(artifact, raw)])
            return artifact

    def finalize_snapshot(self, snapshot_id: str) -> Artifact:
        with self._writer():
            state = self.verify()
            snapshot = self._snapshot(state, snapshot_id)
            raw = self._seal_bytes(state, snapshot)
            seal = self._artifact(f"seals/{snapshot_id}.json", raw, state, None, "seal", snapshot_id)
            updated_snapshot = DerivedSnapshot(**{**asdict(snapshot), "finalized": True, "seal": seal})
            updated = PackageMetadata(state.identity, state.inventory, state.captures,
                tuple(updated_snapshot if s == snapshot else s for s in state.snapshots))
            self._commit(updated, [(seal, raw)])
            return seal
