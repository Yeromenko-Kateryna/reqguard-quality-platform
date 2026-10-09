from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from reqguard import main, persistence


@pytest.mark.parametrize("text", [main.FIXTURE_TEXT, "  synthetic unsupported  "])
def test_orchestration_and_mapping(monkeypatch, text):
    calls = []
    monkeypatch.setattr(main, "save_analysis", lambda original, result: calls.append((original, result)))
    response = TestClient(main.app).post("/analyses", json={"requirement_text": text})
    assert response.status_code == 200
    assert calls == [(text, response.json())]


def test_validation_never_invokes_provider_or_repository(monkeypatch):
    def forbidden(*args):
        pytest.fail("validation invoked application boundary")
    monkeypatch.setattr(main, "analyze", forbidden)
    monkeypatch.setattr(main, "save_analysis", forbidden)
    response = TestClient(main.app).post("/analyses", json={"requirement_text": " \t\n"})
    assert response.status_code == 422


@pytest.mark.parametrize("phase", ["connect", "insert", "commit"])
def test_db_errors_are_sanitized_without_retry(monkeypatch, phase):
    monkeypatch.setenv("DATABASE_URL", "synthetic-local-dsn")
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connect = MagicMock(return_value=connection)
    error = psycopg.OperationalError("sensitive SQL user input credentials")
    if phase == "connect":
        connect.side_effect = error
    elif phase == "insert":
        connection.execute.side_effect = error
    else:
        connection.__exit__.side_effect = error
    monkeypatch.setattr(persistence.psycopg, "connect", connect)
    response = TestClient(main.app).post("/analyses", json={"requirement_text": main.FIXTURE_TEXT})
    assert response.status_code == 503
    assert response.json() == {"detail": "Persistence unavailable"}
    assert connect.call_count == 1


@pytest.mark.parametrize("payload,status", [({"value": "synthetic"}, "completed"), (None, "unsupported_fixture")])
def test_parameter_binding_and_commit_exit(monkeypatch, payload, status):
    monkeypatch.setenv("DATABASE_URL", "synthetic-local-dsn")
    events = []
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.side_effect = lambda *args: events.append("insert")
    connection.__exit__.side_effect = lambda *args: events.append("commit acknowledged")
    monkeypatch.setattr(persistence.psycopg, "connect", MagicMock(return_value=connection))
    run_id = uuid4()
    persistence.save_analysis("quote ' ; synthetic", {"run_id": str(run_id), "provider": "fake", "status": status, "analysis": payload})
    events.append("returned")
    assert events == ["insert", "commit acknowledged", "returned"]
    sql, params = connection.execute.call_args.args
    assert sql.count("%s") == 5
    assert "quote" not in sql
    assert params[:4] == (run_id, "fake", status, "quote ' ; synthetic")
    assert (params[4].obj if params[4] is not None else None) == payload


def test_missing_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = TestClient(main.app).post("/analyses", json={"requirement_text": "synthetic"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Persistence unavailable"}


def test_unexpected_application_exception_is_not_db_outage(monkeypatch):
    def broken(*args):
        raise RuntimeError("application defect")
    monkeypatch.setattr(main, "save_analysis", broken)
    response = TestClient(main.app, raise_server_exceptions=False).post("/analyses", json={"requirement_text": "synthetic"})
    assert response.status_code == 500
