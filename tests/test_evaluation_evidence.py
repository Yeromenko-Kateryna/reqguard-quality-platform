"""Offline storage tests; all evidence lives in pytest's system temporary path."""

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import pytest

from reqguard.evaluation.dataset import load_dataset
from reqguard.evaluation.evidence import (
    PACKAGE_VERSION, EvidenceError, EvidencePackage, PackageIdentity,
    parse_metadata, serialize_metadata,
)


@pytest.fixture
def package(tmp_path):
    assert not tmp_path.resolve().is_relative_to(Path.cwd().resolve())
    return EvidencePackage.create(tmp_path / "package", PackageIdentity("pkg", "run"))


def input_for(package, example="F01"):
    raw = next(r.requirement_text for r in load_dataset() if r.example_id == example).encode()
    return package.register_source("input.txt", raw, role="input", example_id=example)


def capture_for(package, raw=b"response", example="F01", capture_id="capture"):
    source = input_for(package, example)
    provenance = package.register_source(f"{capture_id}.json", b"{}", role="provenance",
                                         example_id=example)
    return package.register_capture(capture_id, example, raw, outcome="received" if raw is not None
                                    else "timeout", input_reference=source.path,
                                    provenance_references=(provenance.path,))


def finalized(package):
    capture_for(package)
    package.create_snapshot("s1", "replay1", capture_ids=("capture",))
    artifact = package.register_derived("s1", "result.json", b'{"synthetic":true}', example_id="F01")
    seal = package.finalize_snapshot("s1")
    return artifact, seal


def state_json(package):
    return json.loads((package.root / "package.json").read_bytes())


def write_state(package, state):
    (package.root / "package.json").write_bytes(serialize_metadata(state))


def tree(package):
    return {p.relative_to(package.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in package.root.rglob("*") if p.is_file()}


def test_empty_package_and_immutable_records(package):
    state = package.verify()
    assert state.identity.version == PACKAGE_VERSION
    assert not state.inventory and not state.captures and not state.snapshots
    with pytest.raises(AttributeError):
        state.identity.package_id = "changed"
    with pytest.raises(EvidenceError):
        EvidencePackage.create(package.root, state.identity)


@pytest.mark.parametrize("raw", [b"", b"\x00\xff\xfe\x80\r\n", bytes(range(256)), b"text\n"])
def test_exact_binary_round_trip(package, raw):
    artifact = package.register_source("binary.bin", raw)
    assert artifact.byte_length == len(raw)
    assert artifact.sha256 == sha256(raw).hexdigest()
    reopened = EvidencePackage(package.root)
    assert reopened.read_artifact(artifact.path) == raw


def test_missing_and_empty_round_trip(package):
    provenance = package.register_source("provenance.json", b"{}", role="provenance")
    for example, capture_id, raw, outcome in (("F01", "missing", None, "timeout"),
            ("F02", "empty", b"", "received"), ("F03", "error", None, "transport_error")):
        source = input_for(package, example)
        package.register_capture(capture_id, example, raw, outcome=outcome,
                                 input_reference=source.path, provenance_references=(provenance.path,))
    captures = {c.capture_id: c for c in EvidencePackage(package.root).verify().captures}
    assert {c.example_id for c in captures.values()} == {"F01", "F02", "F03"}
    assert captures["missing"].artifact_reference is None
    assert captures["error"].artifact_reference is None
    assert captures["empty"].artifact_reference is not None
    assert package.read_artifact(captures["empty"].artifact_reference) == b""


def test_deterministic_serialization_and_package(tmp_path):
    assert serialize_metadata({"z": "кино", "a": [None, True, 2]}) == \
        b'{"a":[null,true,2],"z":"\xd0\xba\xd0\xb8\xd0\xbd\xd0\xbe"}'
    assert serialize_metadata({"b": 2, "a": 1}) == serialize_metadata({"a": 1, "b": 2})
    packages = [EvidencePackage.create(tmp_path / name, PackageIdentity("pkg", "run"))
                for name in ("one", "two")]
    for package in packages:
        finalized(package)
    assert {p: v[0] for p, v in tree(packages[0]).items()} == \
        {p: v[0] for p, v in tree(packages[1]).items()}


@pytest.mark.parametrize("raw", [b"\xff", b"\xef\xbb\xbf{}", b'{"x":1,"x":2}',
    b'{"x":{"a":1,"a":2}}', b"NaN", b"Infinity", b"1e999", b'"\\ud800"',
    b"{} trailing", b'{"x":'])
def test_strict_json_rejects_invalid(raw):
    with pytest.raises(EvidenceError):
        parse_metadata(raw)


@pytest.mark.parametrize("value", [{1: "key"}, {"x": float("nan")}, {"x": float("inf")},
                                   {"x": "\ud800"}, {"x": b"bytes"}, {"x": (1,)}])
def test_strict_serializer_rejects_invalid(value):
    with pytest.raises(EvidenceError):
        serialize_metadata(value)


@pytest.mark.parametrize("raw", [b"\xff", b'{"identity":{},"identity":{}}', b"{}", b"[]", b""])
def test_invalid_metadata_fails_read_and_write(package, raw):
    (package.root / "package.json").write_bytes(raw)
    before = tree(package)
    with pytest.raises(EvidenceError):
        package.verify()
    with pytest.raises(EvidenceError):
        package.register_source("new.bin", b"x")
    assert tree(package) == before


@pytest.mark.parametrize("name", ["../outside", "a/../../outside", "/absolute", "C:/drive", "C:drive",
    "\\\\server\\share", "//server/share", "\\rooted", "a\\b", "a//b", "a/./b", "a/../b",
    ".", "..", "", "CON", "nul.txt", "LPT1", "com9.bin", "name.", "name ", "x:y", "x\x00y"])
def test_unsafe_paths_rejected(package, name):
    before = tree(package)
    with pytest.raises(EvidenceError):
        package.read_artifact(name)
    with pytest.raises(EvidenceError):
        package.register_source(name, b"x")
    assert tree(package) == before


@pytest.mark.parametrize("path", ["../outside", "/tmp/outside", "C:/outside", "C:outside",
                                 "\\\\server\\share", "sources/run/F01/../../outside"])
def test_persisted_path_attacks(package, path):
    package.register_source("a.bin", b"x")
    state = state_json(package)
    state["inventory"][0]["path"] = path
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


@pytest.mark.parametrize("kind", ["file", "directory", "root"])
def test_real_symlink_escape(package, tmp_path, kind):
    artifact = package.register_source("a.bin", b"x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.bin").write_bytes(b"x")
    try:
        if kind == "file":
            link = package.root / artifact.path
            link.unlink()
            link.symlink_to(outside / "a.bin")
        elif kind == "directory":
            link = package.root / "sources/run/_run"
            (link / "a.bin").unlink()
            link.rmdir()
            link.symlink_to(outside, target_is_directory=True)
        else:
            link = tmp_path / "alias"
            link.symlink_to(package.root, target_is_directory=True)
    except OSError as exc:
        if os.name == "nt" and exc.winerror == 1314:
            pytest.skip("Windows token lacks symlink privilege; real junction tests run separately")
        raise
    before = (outside / "a.bin").read_bytes()
    with pytest.raises(EvidenceError):
        if kind == "root":
            EvidencePackage(link).verify()
        else:
            package.verify()
    assert (outside / "a.bin").read_bytes() == before


@pytest.mark.parametrize("kind", ["file", "directory", "root"])
def test_symlink_detection_guard(package, monkeypatch, kind):
    artifact = package.register_source("a.bin", b"x")
    link = {"file": package.root / artifact.path, "directory": package.root / "sources",
            "root": package.root}[kind]
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original(path))
    with pytest.raises(EvidenceError, match="Symlinks"):
        package.verify()


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction test; POSIX runs actual symlinks")
@pytest.mark.parametrize("kind", ["directory", "root"])
def test_real_windows_junction_escape(package, tmp_path, kind):
    artifact = package.register_source("a.bin", b"x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.bin").write_bytes(b"x")
    if kind == "directory":
        link = package.root / "sources/run/_run"
        (package.root / artifact.path).unlink()
        link.rmdir()
        target = outside
    else:
        link = tmp_path / "alias"
        target = package.root
    # Both paths are fixed descendants of pytest's external temporary directory.
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert link.is_junction()
    try:
        with pytest.raises(EvidenceError, match="junctions"):
            if kind == "root":
                EvidencePackage(link).verify()
            else:
                package.verify()
        assert (outside / "a.bin").read_bytes() == b"x"
    finally:
        link.rmdir()  # Remove only the verified junction, never its target tree.


def test_source_write_once_case_insensitive(package):
    artifact = package.register_source("a.bin", b"first")
    before = tree(package)
    for name in ("a.bin", "A.BIN"):
        with pytest.raises(EvidenceError):
            package.register_source(name, b"second")
    assert tree(package) == before
    assert package.read_artifact(artifact.path) == b"first"


@pytest.mark.parametrize("stage", ["fsync", "link", "replace"])
def test_atomic_failure_retains_previous_state(package, monkeypatch, stage):
    package.register_source("old.bin", b"old")
    before = tree(package)
    def fail(*args, **kwargs):
        raise OSError("injected publication failure")
    with monkeypatch.context() as patch:
        patch.setattr(os, stage, fail)
        with pytest.raises(EvidenceError):
            package.register_source("new.bin", b"new")
    assert tree(package) == before
    package.verify()


def test_atomic_create_if_absent_does_not_replace(package):
    artifact = package.register_source("a.bin", b"first")
    with pytest.raises(FileExistsError):
        package._atomic(artifact.path, b"second")
    assert package.read_artifact(artifact.path) == b"first"


@pytest.mark.parametrize("action", ["changed", "truncated", "missing", "checksum", "length"])
def test_corrupt_artifact_fails_closed(package, action):
    artifact = package.register_source("a.bin", b"original")
    path = package.root / artifact.path
    if action == "changed":
        path.write_bytes(b"modified")
    elif action == "truncated":
        path.write_bytes(b"orig")
    elif action == "missing":
        path.unlink()
    else:
        state = state_json(package)
        state["inventory"][0]["sha256" if action == "checksum" else "byte_length"] = \
            "0" * 64 if action == "checksum" else 0
        write_state(package, state)
    before = tree(package)
    with pytest.raises(EvidenceError):
        package.verify()
    with pytest.raises(EvidenceError):
        package.read_artifact(artifact.path)
    assert tree(package) == before


@pytest.mark.parametrize("field,value", [("version", "future"), ("dataset_version", "other"),
    ("dataset_sha256", "0" * 64), ("evaluation_run_id", "other"), ("package_id", "../pkg")])
def test_identity_tampering(package, field, value):
    finalized(package)
    state = state_json(package)
    state["identity"][field] = value
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


@pytest.mark.parametrize("field,value", [("version", "future"), ("dataset_version", "other"),
                                      ("dataset_sha256", "0" * 64), ("package_id", "../pkg")])
def test_invalid_create_identity(tmp_path, field, value):
    with pytest.raises(EvidenceError):
        EvidencePackage.create(tmp_path / "bad", replace(PackageIdentity("pkg", "run"), **{field: value}))
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("field,value", [("sha256", "bad"), ("sha256", "A" * 64),
    ("byte_length", -1), ("byte_length", True), ("role", "unknown"),
    ("evaluation_run_id", "other"), ("example_id", "F02"), ("snapshot_id", "unknown")])
def test_invalid_inventory_metadata(package, field, value):
    input_for(package)
    state = state_json(package)
    state["inventory"][0][field] = value
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


def test_duplicate_inventory(package):
    package.register_source("a.bin", b"x")
    state = state_json(package)
    state["inventory"].append(state["inventory"][0].copy())
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


def test_wrong_frozen_input_rejected(package):
    with pytest.raises(EvidenceError):
        package.register_source("input.txt", b"changed input", role="input", example_id="F01")
    assert not package.verify().inventory


@pytest.mark.parametrize("raw,outcome", [(None, "received"), (b"", "timeout"),
    (b"x", "transport_error"), (None, "failed"), ("text", "received")])
def test_inconsistent_capture_rejected(package, raw, outcome):
    with pytest.raises(EvidenceError):
        package.register_capture("c", "F01", raw, outcome=outcome, input_reference="unused",
                                 provenance_references=())
    assert not package.verify().captures


@pytest.mark.parametrize("field,value", [("evaluation_run_id", "other"), ("example_id", "F02"),
    ("input_reference", "missing"), ("provenance_references", []),
    ("provenance_references", ["missing"]), ("outcome", "timeout"),
    ("artifact_reference", None), ("capture_id", "../bad"), ("capture_id", "renamed")])
def test_corrupt_capture_references(package, field, value):
    capture_for(package)
    state = state_json(package)
    state["captures"][0][field] = value
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


def test_cross_example_provenance_rejected(package):
    source = input_for(package)
    provenance = package.register_source("prov.json", b"{}", role="provenance", example_id="F02")
    with pytest.raises(EvidenceError):
        package.register_capture("c", "F01", b"", outcome="received", input_reference=source.path,
                                 provenance_references=(provenance.path,))
    assert not package.verify().captures


@pytest.mark.parametrize("kind", ["capture", "raw", "provenance"])
def test_duplicate_capture_references(package, kind):
    capture_for(package)
    state = state_json(package)
    if kind == "provenance":
        state["captures"][0]["provenance_references"] *= 2
    else:
        other = state["captures"][0].copy()
        if kind == "raw":
            other["capture_id"] = "other"
        state["captures"].append(other)
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


def test_snapshot_lifecycle_and_independent_replay(package):
    artifact, seal = finalized(package)
    before = package.read_artifact(seal.path)
    package.create_snapshot("s2", "replay2", capture_ids=("capture",),
                            parent_snapshot_id="s1", supersedes_snapshot_id="s1")
    package.register_derived("s2", "result.json", b"new result", example_id="F01")
    package.finalize_snapshot("s2")
    state = EvidencePackage(package.root).verify()
    assert len(state.snapshots) == 2
    assert state.snapshots[1].parent_snapshot_id == "s1"
    assert package.read_artifact(seal.path) == before
    assert package.read_artifact(artifact.path) == b'{"synthetic":true}'


@pytest.mark.parametrize("operation", ["derived", "finalize", "source", "capture", "reuse_snapshot"])
def test_finalized_immutability(package, operation):
    finalized(package)
    before = tree(package)
    with pytest.raises(EvidenceError):
        if operation == "derived":
            package.register_derived("s1", "new.bin", b"x")
        elif operation == "finalize":
            package.finalize_snapshot("s1")
        elif operation == "source":
            package.register_source("new.bin", b"x")
        elif operation == "capture":
            package.register_capture("new", "F01", None, outcome="timeout",
                                     input_reference="unused", provenance_references=())
        else:
            package.create_snapshot("s1", "replay2", capture_ids=("capture",))
    assert tree(package) == before


@pytest.mark.parametrize("field,value", [("parent_snapshot_id", "missing"),
    ("parent_snapshot_id", "s1"), ("supersedes_snapshot_id", "missing"),
    ("capture_ids", ["missing"]), ("capture_ids", ["capture", "capture"]),
    ("artifact_paths", ["missing"]), ("evaluation_run_id", "other"),
    ("replay_id", "capture"), ("replay_id", "run"), ("finalized", False), ("seal", None)])
def test_broken_snapshot_references(package, field, value):
    finalized(package)
    state = state_json(package)
    state["snapshots"][0][field] = value
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


@pytest.mark.parametrize("kind", ["snapshot", "replay", "unfinalized_parent", "cross_example"])
def test_invalid_snapshot_operations(package, kind):
    capture_for(package)
    package.create_snapshot("s1", "replay1", capture_ids=("capture",))
    before = tree(package)
    with pytest.raises(EvidenceError):
        if kind == "snapshot":
            package.create_snapshot("S1", "replay2", capture_ids=("capture",))
        elif kind == "replay":
            package.create_snapshot("s2", "REPLAY1", capture_ids=("capture",))
        elif kind == "unfinalized_parent":
            package.create_snapshot("s2", "replay2", capture_ids=("capture",), parent_snapshot_id="s1")
        else:
            package.register_derived("s1", "bad.bin", b"x", example_id="F02")
    assert tree(package) == before


@pytest.mark.parametrize("kind", ["bytes_and_checksum", "capture_metadata", "snapshot_metadata",
                                 "seal_bytes", "seal_checksum", "seal_missing", "seal_identity"])
def test_finalized_seal_detects_changes(package, kind):
    artifact, seal = finalized(package)
    state = state_json(package)
    if kind == "bytes_and_checksum":
        source = next(a for a in state["inventory"] if a["role"] == "raw")
        (package.root / source["path"]).write_bytes(b"tampered")
        source["sha256"] = sha256(b"tampered").hexdigest()
        source["byte_length"] = len(b"tampered")
    elif kind == "capture_metadata":
        state["captures"][0]["capture_id"] = "renamed"
        state["snapshots"][0]["capture_ids"] = ["renamed"]
    elif kind == "snapshot_metadata":
        state["snapshots"][0]["replay_id"] = "renamed"
    elif kind == "seal_bytes":
        (package.root / seal.path).write_bytes(b"{}")
    elif kind == "seal_checksum":
        state["snapshots"][0]["seal"]["sha256"] = "0" * 64
    elif kind == "seal_identity":
        state["snapshots"][0]["seal"]["evaluation_run_id"] = "other"
    else:
        (package.root / seal.path).unlink()
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


def test_read_only_verification_and_extra_files(package):
    finalized(package)
    before = tree(package)
    package.verify()
    assert tree(package) == before
    (package.root / "unexpected.bin").write_bytes(b"x")
    with pytest.raises(EvidenceError):
        package.verify()


def test_writer_lock_fail_closed(package):
    (package.root / "writer.lock").write_bytes(b"")
    before = tree(package)
    with pytest.raises(EvidenceError):
        package.register_source("new.bin", b"x")
    assert tree(package) == before


def test_unknown_metadata_fields_and_types(package):
    original = state_json(package)
    for state in ({**original, "extra": 1}, {**original, "inventory": {}},
                  {**original, "identity": {**original["identity"], "extra": 1}}):
        write_state(package, state)
        with pytest.raises(EvidenceError):
            package.verify()


def test_derived_bytes_immutable_even_before_finalization(package):
    package.create_snapshot("s1", "replay1", capture_ids=())
    package.register_derived("s1", "result.bin", b"first")
    before = tree(package)
    with pytest.raises(EvidenceError):
        package.register_derived("s1", "result.bin", b"second")
    assert tree(package) == before


def test_empty_snapshot_finalization(package):
    package.create_snapshot("s1", "replay1", capture_ids=())
    seal = package.finalize_snapshot("s1")
    assert parse_metadata(package.read_artifact(seal.path))["inventory"] == []


@pytest.mark.parametrize("kind", ["unowned_raw", "unowned_derived", "duplicate_derived",
                                 "unowned_seal", "unknown_capture_field", "wrong_provenance_role"])
def test_inventory_ownership_and_closed_schemas(package, kind):
    finalized(package)
    state = state_json(package)
    if kind == "unowned_raw":
        state["captures"] = []
    elif kind == "unowned_derived":
        state["snapshots"][0]["artifact_paths"] = []
    elif kind == "duplicate_derived":
        state["snapshots"][0]["artifact_paths"] *= 2
    elif kind == "unowned_seal":
        state["snapshots"] = []
    elif kind == "unknown_capture_field":
        state["captures"][0]["extra"] = "unknown"
    else:
        provenance = next(a for a in state["inventory"] if a["role"] == "provenance")
        provenance["role"] = "source"
    write_state(package, state)
    with pytest.raises(EvidenceError):
        package.verify()


@pytest.mark.parametrize("operation", ["capture", "derived", "finalize"])
def test_transaction_publication_failure_rolls_back(package, monkeypatch, operation):
    capture = capture_for(package)
    package.create_snapshot("s1", "replay1", capture_ids=(capture.capture_id,))
    if operation == "capture":
        source = input_for(package, "F02")
        provenance = package.register_source("new.json", b"{}", role="provenance", example_id="F02")
    before = tree(package)
    def fail(*args, **kwargs):
        raise OSError("injected metadata replace failure")
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail)
        with pytest.raises(EvidenceError):
            if operation == "capture":
                package.register_capture("new", "F02", b"", outcome="received",
                    input_reference=source.path, provenance_references=(provenance.path,))
            elif operation == "derived":
                package.register_derived("s1", "new.bin", b"x")
            else:
                package.finalize_snapshot("s1")
    assert tree(package) == before
    package.verify()


def test_noncanonical_metadata_rejected(package):
    (package.root / "package.json").write_text(json.dumps(state_json(package), indent=2), encoding="utf-8")
    with pytest.raises(EvidenceError, match="Noncanonical"):
        package.verify()


@pytest.mark.parametrize("first_outcome", ["received", "timeout", "transport_error"])
@pytest.mark.parametrize("second_outcome", ["received", "timeout", "transport_error"])
def test_register_capture_rejects_duplicate_example(package, first_outcome, second_outcome):
    source = input_for(package)
    provenance = package.register_source("provenance.json", b"{}", role="provenance")
    first = package.register_capture("first", "F01", b"" if first_outcome == "received" else None,
        outcome=first_outcome, input_reference=source.path, provenance_references=(provenance.path,))
    before = tree(package)
    with pytest.raises(EvidenceError, match="Duplicate example capture"):
        package.register_capture("second", "F01", b"" if second_outcome == "received" else None,
            outcome=second_outcome, input_reference=source.path, provenance_references=(provenance.path,))
    assert tree(package) == before
    assert EvidencePackage(package.root).verify().captures == (first,)


@pytest.mark.parametrize("first_outcome", ["received", "timeout", "transport_error"])
@pytest.mark.parametrize("second_outcome", ["received", "timeout", "transport_error"])
def test_verify_rejects_duplicate_example_captures(package, first_outcome, second_outcome):
    first_input = input_for(package, "F01")
    second_input = input_for(package, "F02")
    provenance = package.register_source("provenance.json", b"{}", role="provenance")
    for capture_id, example, source, outcome in (("first", "F01", first_input, first_outcome),
                                               ("second", "F02", second_input, second_outcome)):
        package.register_capture(capture_id, example, b"" if outcome == "received" else None,
            outcome=outcome, input_reference=source.path, provenance_references=(provenance.path,))
    assert len(EvidencePackage(package.root).verify().captures) == 2
    state = state_json(package)
    second = state["captures"][1]
    second["example_id"] = "F01"
    second["input_reference"] = first_input.path
    if second_outcome == "received":
        old_path = second["artifact_reference"]
        new_path = "sources/run/F01/second.bin"
        (package.root / old_path).rename(package.root / new_path)
        second["artifact_reference"] = new_path
        artifact = next(a for a in state["inventory"] if a["path"] == old_path)
        artifact.update(path=new_path, example_id="F01")
        state["inventory"].sort(key=lambda a: a["path"])
    write_state(package, state)
    before = tree(package)
    with pytest.raises(EvidenceError, match="Duplicate example capture"):
        EvidencePackage(package.root).verify()
    assert tree(package) == before
