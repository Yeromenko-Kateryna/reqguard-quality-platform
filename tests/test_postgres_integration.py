"""Mandatory real PostgreSQL tests: missing configuration is a failure, never a skip."""
import os
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from reqguard import main, persistence


@pytest.fixture
def dsn():
    value = os.environ.get("DATABASE_URL")
    assert value, "DATABASE_URL is mandatory for real PostgreSQL integration"
    with psycopg.connect(value) as connection:
        assert connection.execute("SHOW server_version").fetchone()[0].startswith("17.11")
    return value


def read(dsn, run_id):
    with psycopg.connect(dsn) as connection:
        connection.execute("SET TIME ZONE 'UTC'")
        return connection.execute(
            "SELECT run_id,provider,status,original_input,analysis_payload,created_at,"
            "analysis_payload IS NULL FROM public.analyses WHERE run_id=%s", (run_id,),
        ).fetchall()


def cleanup(dsn, ids):
    with psycopg.connect(dsn) as connection:
        for run_id in ids:
            connection.execute("DELETE FROM public.analyses WHERE run_id=%s", (run_id,))
    for run_id in ids:
        assert read(dsn, run_id) == []


@pytest.mark.parametrize("supported", [True, False])
def test_committed_api_mapping(dsn, supported):
    text = main.FIXTURE_TEXT if supported else f"  synthetic '{uuid4()}' unsupported  "
    ids = []
    sentinel = uuid4()
    try:
        # A pre-existing unrelated-to-request row must survive request cleanup.
        with psycopg.connect(dsn) as connection:
            connection.execute("INSERT INTO public.analyses (run_id,provider,status,original_input) VALUES (%s,'fake','unsupported_fixture',%s)", (sentinel, str(uuid4())))
        response = TestClient(main.app).post("/analyses", json={"requirement_text": text})
        assert response.status_code == 200
        body = response.json()
        run_id = UUID(body["run_id"])
        ids.append(run_id)
        rows = read(dsn, run_id)
        assert len(rows) == 1
        row = rows[0]
        assert row[:5] == (run_id, body["provider"], body["status"], text, body["analysis"])
        assert isinstance(row[5], datetime) and row[5].tzinfo is not None
        assert row[6] is (not supported)
        assert isinstance(row[4], dict) if supported else row[4] is None
        cleanup(dsn, ids)
        assert len(read(dsn, sentinel)) == 1
    finally:
        cleanup(dsn, ids + [sentinel])


def test_exact_metadata(dsn):
    with psycopg.connect(dsn) as connection:
        columns = connection.execute("SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='analyses' ORDER BY ordinal_position").fetchall()
        assert columns == [
            ('run_id','uuid','NO',None), ('provider','text','NO',None),
            ('status','text','NO',None), ('original_input','text','NO',None),
            ('analysis_payload','jsonb','YES',None),
            ('created_at','timestamp with time zone','NO','CURRENT_TIMESTAMP'),
        ]
        constraints = connection.execute("SELECT conname,contype,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.analyses'::regclass ORDER BY conname").fetchall()
        assert {name for name, kind, definition in constraints if kind in ('c','p')} == {'analyses_pkey','analyses_status_valid','analyses_analysis_consistency'}
        definitions = {name: definition for name, kind, definition in constraints}
        assert definitions['analyses_pkey'] == 'PRIMARY KEY (run_id)'
        assert definitions['analyses_status_valid'] == "CHECK ((status = ANY (ARRAY['completed'::text, 'unsupported_fixture'::text])))"
        assert definitions['analyses_analysis_consistency'] == (
            "CHECK ((((status = 'completed'::text) AND (analysis_payload IS NOT NULL) "
            "AND (jsonb_typeof(analysis_payload) = 'object'::text)) OR "
            "((status = 'unsupported_fixture'::text) AND (analysis_payload IS NULL))))"
        )


@pytest.mark.parametrize('status,payload,valid', [
    ('completed', {}, True), ('completed', None, False),
    ('completed', [], False), ('completed', 'scalar', False),
    ('completed', 42, False), ('completed', True, False),
    ('completed', Jsonb(None), False), ('unsupported_fixture', None, True),
    ('unsupported_fixture', {}, False), ('unsupported_fixture', Jsonb(None), False),
    ('unknown', None, False),
])
def test_constraint_matrix(dsn, status, payload, valid):
    run_id = uuid4()
    adapted = payload if payload is None or isinstance(payload, Jsonb) else Jsonb(payload)
    try:
        with psycopg.connect(dsn) as connection:
            if valid:
                connection.execute("INSERT INTO public.analyses (run_id,provider,status,original_input,analysis_payload) VALUES (%s,'fake',%s,%s,%s)", (run_id,status,str(uuid4()),adapted))
            else:
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute("INSERT INTO public.analyses (run_id,provider,status,original_input,analysis_payload) VALUES (%s,'fake',%s,%s,%s)", (run_id,status,str(uuid4()),adapted))
                connection.rollback()
        assert len(read(dsn, run_id)) == int(valid)
    finally:
        cleanup(dsn, [run_id])


@pytest.mark.parametrize('column', ['run_id','provider','status','original_input','created_at'])
def test_required_columns(dsn, column):
    from psycopg import sql
    run_id = uuid4()
    values = dict(run_id=run_id, provider='fake', status='unsupported_fixture', original_input=str(uuid4()), created_at=datetime.now().astimezone())
    values[column] = None
    with psycopg.connect(dsn) as connection:
        with pytest.raises(psycopg.errors.NotNullViolation):
            connection.execute(sql.SQL("INSERT INTO public.analyses ({}) VALUES ({})").format(sql.SQL(',').join(map(sql.Identifier, values)), sql.SQL(',').join([sql.Placeholder()] * len(values))), tuple(values.values()))
        connection.rollback()
    assert read(dsn, run_id) == []


def test_duplicate_and_transaction_rollback(dsn, monkeypatch):
    first, second = uuid4(), uuid4()
    try:
        persistence.save_analysis(str(uuid4()), dict(run_id=str(first),provider='fake',status='unsupported_fixture',analysis=None))
        with psycopg.connect(dsn) as connection:
            connection.execute("INSERT INTO public.analyses (run_id,provider,status,original_input) VALUES (%s,'fake','unsupported_fixture','synthetic')", (second,))
            with pytest.raises(psycopg.errors.UniqueViolation):
                connection.execute("INSERT INTO public.analyses (run_id,provider,status,original_input) VALUES (%s,'fake','unsupported_fixture','synthetic')", (first,))
            connection.rollback()
        assert read(dsn, second) == []
        monkeypatch.setattr(main, 'analyze', lambda text: main.UnsupportedResponse(run_id=first))
        response = TestClient(main.app).post('/analyses', json={'requirement_text': 'synthetic'})
        assert response.status_code == 503
        assert response.json() == {'detail': 'Persistence unavailable'}
        assert len(read(dsn, first)) == 1
    finally:
        cleanup(dsn, [first, second])


def test_real_bad_credentials(dsn, monkeypatch):
    from psycopg.conninfo import make_conninfo
    monkeypatch.setenv('DATABASE_URL', make_conninfo(dsn, password='synthetic_invalid_password'))
    response = TestClient(main.app).post('/analyses', json={'requirement_text': 'synthetic'})
    assert response.status_code == 503
    assert response.json() == {'detail': 'Persistence unavailable'}
