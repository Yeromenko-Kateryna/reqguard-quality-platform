"""Real Uvicorn HTTP responses compared with external container psql."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from uuid import UUID, uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "The user can quickly reset their password"


def psql(run_id, sql):
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'db', 'psql', '-X', '-q', '-A', '-t',
         '-v', 'ON_ERROR_STOP=1', '-v', f'run_id={run_id}', '-U', 'reqguard', '-d', 'reqguard'],
        input=sql, text=True, encoding='utf-8', capture_output=True, cwd=ROOT, timeout=20,
    )
    if result.returncode:
        raise RuntimeError(f'external psql failed (exit {result.returncode})')
    return result.stdout.strip()


def main():
    assert os.environ.get('DATABASE_URL'), 'DATABASE_URL required'
    ids = []
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryFile(mode='w+b') as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'reqguard.main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=ROOT, stdout=log, stderr=log,
        )
        print(f'Owned Uvicorn PID={process.pid} port={port}', flush=True)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10) as client:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Owned Uvicorn exited before readiness')
                    try:
                        if client.get('/openapi.json').status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError('Uvicorn readiness')
                    time.sleep(0.1)
                invalid = client.post('/analyses', json={'requirement_text': ' \t\n'})
                assert invalid.status_code == 422
                print('HTTP 422 validation PASS')
                for text in [FIXTURE, f"  synthetic '{uuid4()}' unsupported  "]:
                    response = client.post('/analyses', json={'requirement_text': text})
                    assert response.status_code == 200
                    body = response.json()
                    run_id = str(UUID(body['run_id']))
                    ids.append(run_id)
                    raw = psql(run_id, "SET TIME ZONE 'UTC'; SELECT row_to_json(r) FROM (SELECT run_id,provider,status,original_input,analysis_payload,created_at,analysis_payload IS NULL AS analysis_is_sql_null FROM public.analyses WHERE run_id=:'run_id'::uuid) r;")
                    rows = raw.splitlines()
                    assert len(rows) == 1
                    row = json.loads(rows[0])
                    assert row['run_id'] == body['run_id']
                    assert row['provider'] == body['provider']
                    assert row['status'] == body['status']
                    assert row['original_input'] == text
                    assert row['analysis_payload'] == body['analysis']
                    timestamp = datetime.fromisoformat(row['created_at'])
                    assert timestamp.tzinfo is not None
                    if body['status'] == 'completed':
                        assert isinstance(row['analysis_payload'], dict)
                        assert row['analysis_is_sql_null'] is False
                    else:
                        assert body['status'] == 'unsupported_fixture'
                        assert row['analysis_is_sql_null'] is True
                    print('HTTP 200 RESPONSE ' + json.dumps(body))
                    print('EXTERNAL PSQL ROW ' + json.dumps(row))
                    print('All mapped fields, cardinality, timestamp and SQL NULL assertions PASS')
        finally:
            try:
                for run_id in ids:
                    psql(run_id, "DELETE FROM public.analyses WHERE run_id=:'run_id'::uuid;")
                    count = psql(run_id, "SELECT count(*) FROM public.analyses WHERE run_id=:'run_id'::uuid;")
                    assert count == '0'
                    print(f'Targeted cleanup {run_id}: remaining=0')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                print(f'Owned Uvicorn PID={process.pid} terminated')
    print('NETWORK-TO-SQL PASS: both statuses')


if __name__ == '__main__':
    main()
