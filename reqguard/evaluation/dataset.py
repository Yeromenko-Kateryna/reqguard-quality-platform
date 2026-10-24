"""Load the frozen RG-07A fixture; never normalize or repair dataset bytes.

The fingerprint pins the entire artifact, including JSON spelling and order.
Structural validation is a separate defense, not a way to accept another hash.
This module implements no provider calls, scoring, or output evaluation.
"""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path


DATASET_VERSION = "rg07a-synthetic-v1"
DATASET_SHA256 = "3DC279E2D018522E552C29C40451AB71A785098DACB68BD5CF1F8AB9330F3A7E"
DATASET_BYTE_LENGTH = 10407
DATASET_PATH = Path(__file__).with_name("datasets") / f"{DATASET_VERSION}.json"
EXAMPLE_IDS = tuple(f"{prefix}{number:02}" for prefix in "FAS" for number in range(1, 5))
# RG-07A section 2.2 pins the current API bound without importing FastAPI.
MIN_INPUT_LENGTH = 1
MAX_INPUT_LENGTH = 2000
_CATEGORIES = {"F": "functional", "A": "ambiguous", "S": "safety"}
_FIELDS = (
    "dataset_version", "example_id", "category", "requirement_text",
    "expected_properties", "prohibited_behavior", "rationale",
    "authorized_facts", "forbidden_literals",
)
_STRING_FIELDS = (
    "dataset_version", "example_id", "category", "requirement_text",
    "rationale", "authorized_facts",
)


class DatasetValidationError(ValueError):
    """The requested artifact is unavailable or violates the frozen contract."""


@dataclass(frozen=True)
class DatasetRecord:
    dataset_version: str
    example_id: str
    category: str
    requirement_text: str
    expected_properties: tuple[str, ...]
    prohibited_behavior: tuple[str, ...]
    rationale: str
    authorized_facts: str
    forbidden_literals: tuple[str, ...]


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DatasetValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonblank_string(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _parse_records(raw: bytes) -> tuple[DatasetRecord, ...]:
    """Validate structure after fingerprint validation by load_dataset."""
    try:
        records = json.loads(raw.decode("utf-8", errors="strict"),
                             object_pairs_hook=_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DatasetValidationError("Dataset must be a UTF-8 JSON array") from exc
    if not isinstance(records, list) or len(records) != len(EXAMPLE_IDS):
        raise DatasetValidationError("Dataset must contain exactly 12 records")

    validated = []
    for expected_id, record in zip(EXAMPLE_IDS, records, strict=True):
        if not isinstance(record, dict) or tuple(record) != _FIELDS:
            raise DatasetValidationError(f"{expected_id}: unexpected fields or field order")
        for field in _STRING_FIELDS:
            if not _nonblank_string(record[field]):
                raise DatasetValidationError(f"{expected_id}: {field} must be a nonblank string")
        if record["dataset_version"] != DATASET_VERSION:
            raise DatasetValidationError(f"{expected_id}: unexpected dataset version")
        if record["example_id"] != expected_id:
            raise DatasetValidationError(f"Expected unique ordered ID {expected_id}")
        if record["category"] != _CATEGORIES[expected_id[0]]:
            raise DatasetValidationError(f"{expected_id}: unexpected category")
        text = record["requirement_text"]
        if not MIN_INPUT_LENGTH <= len(text) <= MAX_INPUT_LENGTH:
            raise DatasetValidationError(f"{expected_id}: input length must be 1–2000 characters")
        facts = text.split("\n", 1)[0] if expected_id.startswith("S") else text
        if record["authorized_facts"] != facts:
            raise DatasetValidationError(f"{expected_id}: authorized facts differ from product input")
        for field in ("expected_properties", "prohibited_behavior", "forbidden_literals"):
            values = record[field]
            if not isinstance(values, list) or not all(_nonblank_string(v) for v in values):
                raise DatasetValidationError(f"{expected_id}: {field} must be a string array")
            if field != "forbidden_literals" and len(values) != 1:
                raise DatasetValidationError(f"{expected_id}: {field} must contain one paragraph")
        validated.append(DatasetRecord(**{
            **record,
            "expected_properties": tuple(record["expected_properties"]),
            "prohibited_behavior": tuple(record["prohibited_behavior"]),
            "forbidden_literals": tuple(record["forbidden_literals"]),
        }))
    if Counter(r.category for r in validated) != dict.fromkeys(_CATEGORIES.values(), 4):
        raise DatasetValidationError("Expected four records per category")
    return tuple(validated)


def load_dataset(path: str | Path = DATASET_PATH) -> tuple[DatasetRecord, ...]:
    """Read and validate exactly rg07a-synthetic-v1, returning immutable records.

    Alternate paths are permitted for offline copies, but never alternate bytes,
    versions, or caller-supplied fingerprints. No trimming or reserialization.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise DatasetValidationError("Cannot read dataset artifact") from exc
    if sha256(raw).hexdigest().upper() != DATASET_SHA256:
        raise DatasetValidationError("Dataset SHA-256 mismatch")
    if len(raw) != DATASET_BYTE_LENGTH:
        raise DatasetValidationError("Dataset byte length mismatch")
    return _parse_records(raw)
