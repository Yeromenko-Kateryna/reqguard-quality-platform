"""Offline conformance checks for the frozen dataset, with no product imports."""

from collections import Counter
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

import pytest

from reqguard.evaluation import dataset


@pytest.fixture
def records():
    return json.loads(dataset.DATASET_PATH.read_bytes())


def encode(records):
    return json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_exact_artifact_and_specification_fixture():
    raw = dataset.DATASET_PATH.read_bytes()
    assert len(raw) == dataset.DATASET_BYTE_LENGTH == 10407
    assert sha256(raw).hexdigest().upper() == dataset.DATASET_SHA256 == (
        "3DC279E2D018522E552C29C40451AB71A785098DACB68BD5CF1F8AB9330F3A7E"
    )
    spec = Path(__file__).resolve().parents[1] / "docs/ai-quality/RG-07A_EVALUATION_SPEC_v1.md"
    section = spec.read_text(encoding="utf-8").split(
        "### 2.5 Canonical materialized dataset", 1
    )[1]
    fixture = section.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert raw == fixture.encode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not raw.endswith(b"\n")


def test_load_default_and_copy_preserve_all_values(tmp_path, records):
    copy = tmp_path / "copy.json"
    copy.write_bytes(dataset.DATASET_PATH.read_bytes())
    loaded = dataset.load_dataset()
    assert loaded == dataset.load_dataset(str(copy))
    assert tuple(r.example_id for r in loaded) == (
        "F01", "F02", "F03", "F04", "A01", "A02", "A03", "A04",
        "S01", "S02", "S03", "S04",
    )
    assert Counter(r.category for r in loaded) == {"functional": 4, "ambiguous": 4, "safety": 4}
    for actual, expected in zip(loaded, records, strict=True):
        for field, value in expected.items():
            assert getattr(actual, field) == (tuple(value) if isinstance(value, list) else value)
        assert 1 <= len(actual.requirement_text) <= 2000
    assert loaded[8].authorized_facts == loaded[8].requirement_text.split("\n", 1)[0]
    with pytest.raises(FrozenInstanceError):
        loaded[0].requirement_text = "changed"
    assert isinstance(loaded, tuple)
    assert isinstance(loaded[0].expected_properties, tuple)


@pytest.mark.parametrize("kind", [
    "empty", "malformed", "invalid-utf8", "bom", "terminal-lf", "terminal-crlf",
    "whitespace", "pretty-json", "changed-content", "wrong-version", "reordered-keys",
    "reordered-records", "missing-record", "duplicate-id",
])
def test_loader_rejects_any_unaccepted_bytes_before_parsing(tmp_path, records, monkeypatch, kind):
    raw = dataset.DATASET_PATH.read_bytes()
    if kind == "empty":
        raw = b""
    elif kind == "malformed":
        raw = raw[:-1]
    elif kind == "invalid-utf8":
        raw = b"\xff" + raw[1:]
    elif kind == "bom":
        raw = b"\xef\xbb\xbf" + raw
    elif kind == "terminal-lf":
        raw += b"\n"
    elif kind == "terminal-crlf":
        raw += b"\r\n"
    elif kind == "whitespace":
        raw = b" " + raw
    elif kind == "pretty-json":
        raw = json.dumps(records, indent=2).encode()
    elif kind == "changed-content":
        raw = raw.replace(b"shopper", b"Shopper", 1)  # Same byte length.
    elif kind == "wrong-version":
        raw = raw.replace(b"rg07a-synthetic-v1", b"rg07a-synthetic-v2")
    elif kind == "reordered-keys":
        records[0] = dict(reversed(list(records[0].items())))
        raw = encode(records)
    elif kind == "reordered-records":
        raw = encode(list(reversed(records)))
    elif kind == "missing-record":
        raw = encode(records[:-1])
    elif kind == "duplicate-id":
        records[1]["example_id"] = "F01"
        raw = encode(records)
    path = tmp_path / "modified.json"
    path.write_bytes(raw)

    def forbidden_parse(raw):
        pytest.fail("Unaccepted fingerprint reached the JSON parser")

    monkeypatch.setattr(dataset, "_parse_records", forbidden_parse)
    with pytest.raises(dataset.DatasetValidationError, match="SHA-256 mismatch"):
        dataset.load_dataset(path)


@pytest.mark.parametrize("kind", ["missing", "directory", "unreadable"])
def test_unavailable_artifact_fails_closed(tmp_path, monkeypatch, kind):
    path = tmp_path / "missing.json"
    if kind == "directory":
        path = tmp_path
    elif kind == "unreadable":
        def denied(self):
            raise PermissionError("synthetic denied read")
        monkeypatch.setattr(Path, "read_bytes", denied)
    with pytest.raises(dataset.DatasetValidationError, match="Cannot read dataset"):
        dataset.load_dataset(path)


# Structural defense is tested directly: production never bypasses the pinned hash.
@pytest.mark.parametrize("raw", [b"\xff", b"[", b"\xef\xbb\xbf[]"])
def test_parser_rejects_invalid_encoding_or_json(raw):
    with pytest.raises(dataset.DatasetValidationError, match="UTF-8 JSON"):
        dataset._parse_records(raw)


def test_parser_rejects_duplicate_json_keys():
    with pytest.raises(dataset.DatasetValidationError, match="Duplicate JSON key"):
        dataset._parse_records(b'[{"example_id":"F01","example_id":"F02"}]')


@pytest.mark.parametrize("value", [None, {}, "records", [], [None] * 11, [None] * 13])
def test_parser_requires_twelve_record_array(value):
    with pytest.raises(dataset.DatasetValidationError, match="exactly 12"):
        dataset._parse_records(encode(value))


@pytest.mark.parametrize("kind,match", [
    ("not-object", "fields"), ("missing-field", "fields"), ("extra-field", "fields"),
    ("field-order", "fields"), ("version", "version"), ("duplicate-id", "ordered ID"),
    ("unknown-id", "ordered ID"), ("id-order", "ordered ID"),
    ("category", "category"), ("category-case", "category"),
    ("empty-input", "nonblank"), ("blank-input", "nonblank"),
    ("long-input", "input length"), ("numeric-input", "nonblank"),
    ("null-rationale", "nonblank"), ("surrogate", "nonblank"),
    ("facts", "authorized facts"), ("safety-facts", "authorized facts"),
    ("expected-string", "string array"), ("expected-empty", "one paragraph"),
    ("expected-split", "one paragraph"), ("prohibited-empty", "one paragraph"),
    ("prohibited-nonstring", "string array"), ("forbidden-string", "string array"),
    ("forbidden-nonstring", "string array"), ("forbidden-blank", "string array"),
])
def test_structural_defense(records, kind, match):
    first = records[0]
    if kind == "not-object":
        records[0] = None
    elif kind == "missing-field":
        del first["rationale"]
    elif kind == "extra-field":
        first["extra"] = "unexpected"
    elif kind == "field-order":
        records[0] = dict(reversed(list(first.items())))
    elif kind == "version":
        first["dataset_version"] = "rg07a-synthetic-v2"
    elif kind == "duplicate-id":
        records[1]["example_id"] = "F01"
    elif kind == "unknown-id":
        first["example_id"] = "F05"
    elif kind == "id-order":
        records[0], records[1] = records[1], records[0]
    elif kind in ("category", "category-case"):
        first["category"] = "safety" if kind == "category" else "Functional"
    elif kind in ("empty-input", "blank-input", "long-input", "numeric-input"):
        first["requirement_text"] = {
            "empty-input": "", "blank-input": " \t\n", "long-input": "x" * 2001,
            "numeric-input": 123,
        }[kind]
    elif kind == "null-rationale":
        first["rationale"] = None
    elif kind == "surrogate":
        first["rationale"] = "\ud800"
        with pytest.raises(dataset.DatasetValidationError, match=match):
            dataset._parse_records(json.dumps(records).encode())
        return
    elif kind == "facts":
        first["authorized_facts"] = "unexpected"
    elif kind == "safety-facts":
        records[8]["authorized_facts"] = records[8]["requirement_text"]
    else:
        field, value = {
            "expected-string": ("expected_properties", "paragraph"),
            "expected-empty": ("expected_properties", []),
            "expected-split": ("expected_properties", ["one", "two"]),
            "prohibited-empty": ("prohibited_behavior", []),
            "prohibited-nonstring": ("prohibited_behavior", [False]),
            "forbidden-string": ("forbidden_literals", "marker"),
            "forbidden-nonstring": ("forbidden_literals", [None]),
            "forbidden-blank": ("forbidden_literals", [" "]),
        }[kind]
        first[field] = value
    with pytest.raises(dataset.DatasetValidationError, match=match):
        dataset._parse_records(encode(records))


@pytest.mark.parametrize("text", ["x", "x" * 2000, " x ", "x\nx"])
def test_structural_input_boundaries_preserve_text(records, text):
    records[0]["requirement_text"] = text
    records[0]["authorized_facts"] = text
    assert dataset._parse_records(encode(records))[0].requirement_text == text
