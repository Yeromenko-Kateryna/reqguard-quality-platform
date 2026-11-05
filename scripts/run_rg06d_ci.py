"""RG-06D only: Linux hosted CI, existing RG-06B specs, safe publication.

prepare/publish use only stdlib, including after dependency setup fails.
Read-only Docker admission only: GitHub owns service disposal, which this file cannot attest.
"""

import ctypes
from datetime import datetime, timedelta
import stat
import hashlib
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
import uuid
import rg06d_admission as admission


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'quality/browser'
IMAGE = 'postgres:17.11-bookworm@sha256:ec4dfc6571f04fe0731ce948c1500d676af49a7224392dcc6995cc1ee33a94bb'
PASSWORD = '0123456789abcdef' * 4  # Public synthetic service credential, not a secret.
INPUTS = ['pyproject.toml', 'uv.lock', 'db/001_init.sql', 'reqguard/main.py',
          'reqguard/persistence.py', 'reqguard/static/index.html', 'reqguard/static/app.mjs',
          'reqguard/static/style.css', 'quality/browser/package.json',
          'quality/browser/package-lock.json', 'quality/browser/analyses.spec.ts',
          'quality/browser/playwright.config.ts', 'quality/browser/playwright.ci.config.ts',
          'scripts/run_rg06d_ci.py', '.github/workflows/rg06d-e2e.yml',
          'quality/browser/owned-cleanup.ts', 'quality/browser/owned-cleanup.test.ts',
          'quality/browser/ci-identity.mjs', 'quality/browser/unit-reporter.mjs',
          'scripts/rg06d_admission.py', 'scripts/test_rg06d_admission.py',
          'quality/browser/ci-identity.test.mjs', 'quality/browser/ci-preload.integration.test.mjs',
          'quality/browser/ci-preload-checks.mjs', 'quality/browser/ci-preload-gate.test.mjs']
ADMISSION_FILES = ['ownership-preservation.json', 'ownership.json', 'ownership-unit.json',
                   'service-identity.json', 'connections.json', 'pg-preload.json']
JSON_ALLOWLIST = ['launch.json', 'postgres-ready.json', 'baseline.json', 'sentinel-plan.json',
                  'supported-response-id.json', 'supported-sql.json', 'invalid-sql.json',
                  'supported-cleanup.json', 'unsupported-response-id.json', 'unsupported-sql.json',
                  'unsupported-cleanup.json', 'sql-cleanup.json', 'results.json',
                  'server-process.json', 'playwright-process.json', 'run-summary.json']
JSON_ALLOWLIST += ADMISSION_FILES
LOG_ALLOWLIST = ['uvicorn.stdout', 'uvicorn.stderr', 'playwright.stdout', 'playwright.stderr']


class Stop(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Stop(code)


# Kept identical in both harnesses: no application imports or database access.
UNSUPPORTED_EVIDENCE_FILES = (
    'baseline.json', 'sentinel-plan.json', 'unsupported-response-id.json',
    'unsupported-sql.json', 'unsupported-cleanup.json', 'sql-cleanup.json',
)


def parse_evidence_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'EVIDENCE_DUPLICATE_KEY')
            result[key] = value
        return result

    def constant(_):
        raise Stop('EVIDENCE_NONFINITE_JSON')

    require(type(raw) is bytes and 0 < len(raw) <= 10_000_000, 'EVIDENCE_BYTES')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError):
        raise Stop('EVIDENCE_JSON_INVALID') from None


def validate_unsupported_receipts(receipts, run):
    def shape(value, keys):
        require(type(value) is dict and set(value) == set(keys), 'EVIDENCE_KEYS')
        return value

    def boolean(value, expected):
        require(type(value) is bool and value is expected, 'EVIDENCE_BOOLEAN')

    def identifier(value):
        require(type(value) is str and re.fullmatch(
            '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', value),
            'EVIDENCE_UUID4')

    def row(value, original):
        shape(value, ('run_id', 'provider', 'status', 'original_input',
                      'analysis_payload', 'created_at', 'sql_null'))
        identifier(value['run_id'])
        require(value['provider'] == 'fake' and value['status'] == 'unsupported_fixture',
                'EVIDENCE_ROW_STATUS')
        require(type(value['original_input']) is str and value['original_input'] == original,
                'EVIDENCE_INPUT')
        require(value['analysis_payload'] is None, 'EVIDENCE_SQL_NULL')
        boolean(value['sql_null'], True)
        stamp = value['created_at']
        require(type(stamp) is str and re.fullmatch(r'.*\+00(?::?00)?', stamp),
                'EVIDENCE_TIMESTAMP')
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            raise Stop('EVIDENCE_TIMESTAMP') from None
        require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
                'EVIDENCE_TIMESTAMP')
        return value

    require(type(run) is str and re.fullmatch('[a-f0-9]{32}', run), 'EVIDENCE_RUN')
    shape(receipts, UNSUPPORTED_EVIDENCE_FILES)
    docs = {name: parse_evidence_json(receipts[name]) for name in UNSUPPORTED_EVIDENCE_FILES}
    plan = shape(docs['sentinel-plan.json'], ('run', 'run_id'))
    require(type(plan['run']) is str and plan['run'] == run, 'EVIDENCE_SENTINEL_RUN')
    identifier(plan['run_id'])
    base = shape(docs['baseline.json'], ('identity', 'columns', 'constraints', 'rows'))
    require(base['identity'] == {
        'db': 'reqguard_rg06b', 'role': 'reqguard_rg06b', 'version': '170011',
    }, 'EVIDENCE_DB_IDENTITY')
    expected_columns = [
        {'column_name': name, 'data_type': kind, 'is_nullable': nullable, 'column_default': default}
        for name, kind, nullable, default in (
            ('run_id', 'uuid', 'NO', None), ('provider', 'text', 'NO', None),
            ('status', 'text', 'NO', None), ('original_input', 'text', 'NO', None),
            ('analysis_payload', 'jsonb', 'YES', None),
            ('created_at', 'timestamp with time zone', 'NO', 'CURRENT_TIMESTAMP'),
        )
    ]
    require(base['columns'] == expected_columns, 'EVIDENCE_COLUMNS')
    require(base['constraints'] == [
        {'conname': 'analyses_analysis_consistency', 'definition':
         "CHECK ((((status = 'completed'::text) AND (analysis_payload IS NOT NULL) AND (jsonb_typeof(analysis_payload) = 'object'::text)) OR ((status = 'unsupported_fixture'::text) AND (analysis_payload IS NULL))))"},
        {'conname': 'analyses_pkey', 'definition': 'PRIMARY KEY (run_id)'},
        {'conname': 'analyses_status_valid', 'definition':
         "CHECK ((status = ANY (ARRAY['completed'::text, 'unsupported_fixture'::text])))"},
    ], 'EVIDENCE_CONSTRAINTS')
    require(type(base['rows']) is list and len(base['rows']) == 1, 'EVIDENCE_BASELINE_ROWS')
    sentinel = row(base['rows'][0], 'RG06B owned sentinel ' + run)
    require(sentinel['run_id'] == plan['run_id'], 'EVIDENCE_SENTINEL_ID')
    response_id = shape(docs['unsupported-response-id.json'], ('run_id',))
    identifier(response_id['run_id'])
    sql = shape(docs['unsupported-sql.json'],
                ('response', 'before', 'after', 'verified', 'browserVersion'))
    boolean(sql['verified'], True)
    require(type(sql['browserVersion']) is str and bool(sql['browserVersion'].strip()),
            'EVIDENCE_BROWSER_VERSION')
    response = shape(sql['response'], ('run_id', 'provider', 'status', 'analysis'))
    identifier(response['run_id'])
    require(response['run_id'] == response_id['run_id'] and
            response['run_id'] != sentinel['run_id'], 'EVIDENCE_RESPONSE_ID')
    require(response['provider'] == 'fake' and response['status'] == 'unsupported_fixture' and
            response['analysis'] is None, 'EVIDENCE_RESPONSE')
    require(type(sql['before']) is list and len(sql['before']) == 1, 'EVIDENCE_BEFORE')
    row(sql['before'][0], sentinel['original_input'])
    require(sql['before'] == base['rows'], 'EVIDENCE_BASELINE_CHANGED')
    require(type(sql['after']) is list and len(sql['after']) == 2, 'EVIDENCE_AFTER')
    original = '  A synthetic unsupported requirement ' + run + '  '
    for item in sql['after']:
        shape(item, ('run_id', 'provider', 'status', 'original_input',
                     'analysis_payload', 'created_at', 'sql_null'))
        row(item, sentinel['original_input'] if item['run_id'] == sentinel['run_id'] else original)
    owned = [item for item in sql['after'] if item['run_id'] == response['run_id']]
    require(len(owned) == 1 and sql['after'] == sorted(
        [sentinel, owned[0]], key=lambda item: item['run_id']), 'EVIDENCE_ROW_DELTA')
    cleanup = shape(docs['unsupported-cleanup.json'], ('remainingOwnedRows', 'sentinelUnchanged'))
    require(type(cleanup['remainingOwnedRows']) is int and cleanup['remainingOwnedRows'] == 0,
            'EVIDENCE_OWNED_CLEANUP')
    boolean(cleanup['sentinelUnchanged'], True)
    final = shape(docs['sql-cleanup.json'],
                  ('state', 'supportedCleaned', 'invalidVerified', 'unsupportedCleaned', 'uncertain'))
    require(type(final['state']) is str and final['state'] == 'CLEANED', 'EVIDENCE_CLEANUP_STATE')
    for key in ('supportedCleaned', 'invalidVerified', 'unsupportedCleaned'):
        boolean(final[key], True)
    boolean(final['uncertain'], False)


def read_unsupported_receipts(directory):
    result = {}
    for name in UNSUPPORTED_EVIDENCE_FILES:
        source = directory / name
        info = source.lstat()
        require(stat.S_ISREG(info.st_mode) and not source.is_symlink() and
                not (getattr(info, 'st_file_attributes', 0) & 0x400), 'EVIDENCE_FILE_TYPE')
        with source.open('rb') as stream:
            result[name] = stream.read(10_000_001)
        require(0 < len(result[name]) <= 10_000_000, 'EVIDENCE_FILE_SIZE')
    # Checks and reads are not atomic; callers must not claim race-free admission.
    return result


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(argv):
    return subprocess.check_output(argv, cwd=ROOT, stderr=subprocess.DEVNULL,
                                   text=True, timeout=15).strip()


def source_identity():
    head = output(['git', 'rev-parse', 'HEAD'])
    event = admission.parse(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request') if os.environ['GITHUB_EVENT_NAME'] == 'pull_request' else None
    hashes = {n: digest(ROOT / n) for n in INPUTS}
    value = {'checkout_sha': head, 'pr_head_sha': pr['head']['sha'] if pr else None,
             'pr_base_sha': pr['base']['sha'] if pr else None,
             'tested_merge_sha': head if pr else None,
             'github_run_id': os.environ['GITHUB_RUN_ID'],
             'github_run_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'inputs': hashes,
             'python_lock_sha256': hashes['uv.lock'],
             'node_lock_sha256': hashes['quality/browser/package-lock.json']}
    admission.validate_source(value, value)
    require(head == os.environ['GITHUB_SHA'], 'CHECKOUT_EVENT_SHA')
    if pr:
        require(pr.get('merge_commit_sha') == head, 'PR_MERGE_SHA')
    return value


def validate_launch(launch):
    expected = source_identity()
    admission.validate_source(launch['source_identity'], expected)
    require(launch['head'] == expected['checkout_sha'] and launch['inputs'] == expected['inputs']
            and launch['githubRun'] == expected['github_run_id']
            and launch['githubAttempt'] == expected['github_run_attempt'], 'LAUNCH_SOURCE')
    return expected


def service_admission(path, source):
    require(os.environ.get('RG06D_RUNNER_ENV') == 'github-hosted', 'HOSTED_RUNNER_REQUIRED')
    require(not any(os.environ.get(k) for k in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')), 'DOCKER_OVERRIDE')
    context = output(['docker', 'context', 'show'])
    endpoint = output(['docker', 'context', 'inspect', context, '--format', '{{.Endpoints.docker.Host}}'])
    require(endpoint == 'unix:///var/run/docker.sock', 'JOB_DOCKER_ENDPOINT')
    docker = ['docker', '--context', context]
    engine = output(docker + ['info', '--format', '{{.ID}}'])
    require(bool(engine), 'ENGINE_ID')
    service_id = os.environ['RG06D_SERVICE_ID']
    require(re.fullmatch('[a-f0-9]{64}', service_id), 'SERVICE_ID')
    fmt = ('{"Id":{{json .Id}},"Image":{{json .Image}},"State":{{json .State}},'
           '"Mounts":{{json .Mounts}},"NetworkSettings":{{json .NetworkSettings}}}')
    container = admission.parse(output(docker + ['inspect', service_id, '--format', fmt]).encode())
    image = admission.parse(output(docker + ['image', 'inspect', IMAGE, '--format',
        '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"RepoDigests":{{json .RepoDigests}}}']).encode())
    require(IMAGE.split('@')[1] in [s.split('@')[-1] for s in image['RepoDigests']], 'SERVICE_IMAGE_DIGEST')
    admission.validate_service(container, image, service_id, os.environ['RG06D_SERVICE_NETWORK'], os.environ['RG06B_DB_PORT'])
    address = next(iter(container['NetworkSettings']['Networks'].values()))['IPAddress']
    # Loopback TCP inside the admitted container binds the cluster to this service;
    # host-side connections independently validate the inspected bridge address.
    query = 'SELECT row_to_json(i) FROM (' + admission.IDENTITY_SQL + ') i'
    observed = admission.parse(output(docker + ['exec', '-e', 'PGPASSWORD=' + PASSWORD,
        '-e', 'PGCONNECT_TIMEOUT=5', '-e', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000', service_id,
        'psql', '-X', '-w', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-U', 'reqguard_rg06b',
        '-d', 'reqguard_rg06b', '-h', '127.0.0.1', '-c', query]).encode())
    fingerprint = {k: observed[k] for k in admission.FINGERPRINT_KEYS}
    admission.validate_identity(observed, fingerprint, {'address': '127.0.0.1', 'port': 5432})
    value = {'schema_version': 'rg06d-service-v2', 'run_id': path.name,
             'source_identity': source, 'container_id': service_id, 'engine_id': engine,
             'endpoint': endpoint, 'image': IMAGE, 'image_id': image['Id'],
             'network_id': os.environ['RG06D_SERVICE_NETWORK'], 'host_port': os.environ['RG06B_DB_PORT'],
             'fingerprint': fingerprint, 'service_observation': observed,
             'host_path': {'address': address, 'port': 5432},
             'host_target': {'host': '127.0.0.1', 'port': int(os.environ['RG06B_DB_PORT'])},
             'published_bindings': container['NetworkSettings']['Ports']['5432/tcp']}
    write(path / 'service-identity.json', value)
    return value


def unit_gate(path, source):
    result = subprocess.run(['node', '--test', '--test-reporter', (PACKAGE / 'unit-reporter.mjs').as_uri(),
                             'quality/browser/owned-cleanup.test.ts'], cwd=ROOT,
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
    value = {'schema_version': 'rg06d-unit-v1', 'run_id': path.name, 'source_identity': source,
             'exit_code': result.returncode, 'report': admission.parse(result.stdout)}
    write(path / 'ownership-unit.json', value)
    admission.validate_unit(value, path.name, source)


def preload_gate(path, source):
    require(os.environ.get('RG06D_REQUIRE_PG_PRELOAD_TEST') == '1', 'PRELOAD_REQUIRED_MODE')
    meta = PACKAGE / 'node_modules/pg/package.json'
    require(meta.is_file(), 'PRELOAD_PG_MISSING')
    version = admission.parse(meta.read_bytes())['version']
    require(version == '8.23.1', 'PRELOAD_PG_VERSION')
    result = subprocess.run(['node', '--test', '--test-reporter', (PACKAGE / 'unit-reporter.mjs').as_uri(),
                             'quality/browser/ci-preload.integration.test.mjs'], cwd=ROOT,
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False,
                            env={**os.environ, 'RG06D_REQUIRE_PG_PRELOAD_TEST': '1'})
    value = {'schema_version': 'rg06d-preload-v1', 'run_id': path.name, 'source_identity': source,
             'exit_code': result.returncode, 'pg_version': version, 'report': admission.parse(result.stdout)}
    write(path / 'pg-preload.json', value)
    admission.validate_preload(value, path.name, source)


def validate_admission_bundle(directory, source, run):
    # Re-read bounded exact filenames at both execution and publication boundaries.
    require({p.name for p in Path(directory).glob('ownership*.json')} ==
            {'ownership.json', 'ownership-preservation.json', 'ownership-unit.json'}, 'OWNERSHIP_RECEIPT_SET')
    raw = {n: admission.read(directory, n) for n in ADMISSION_FILES}
    admission.validate_ownership(raw['ownership.json'], raw['ownership-preservation.json'], run, source)
    admission.validate_unit(admission.parse(raw['ownership-unit.json']), run, source)
    admission.validate_preload(admission.parse(raw['pg-preload.json']), run, source)
    service = admission.parse(raw['service-identity.json'])
    admission.shape(service, ('schema_version', 'run_id', 'source_identity', 'container_id', 'engine_id',
                             'endpoint', 'image', 'image_id', 'network_id', 'host_port', 'fingerprint',
                             'service_observation', 'host_path', 'host_target', 'published_bindings'))
    require(service['schema_version'] == 'rg06d-service-v2' and service['run_id'] == run
            and service['image'] == IMAGE and service['endpoint'] == 'unix:///var/run/docker.sock', 'SERVICE_RECEIPT')
    admission.validate_source(service['source_identity'], source)
    require(service['container_id'] == os.environ['RG06D_SERVICE_ID']
            and service['network_id'] == os.environ['RG06D_SERVICE_NETWORK']
            and service['host_port'] == os.environ['RG06B_DB_PORT']
            and bool(service['engine_id']) and re.fullmatch('sha256:[a-f0-9]{64}', service['image_id']), 'SERVICE_CONTEXT')
    admission.validate_bindings(service['published_bindings'], service['host_port'])
    admission.validate_client_target('127.0.0.1', int(service['host_port']), service['host_target'])
    admission.validate_identity(service['service_observation'], service['fingerprint'], {'address': '127.0.0.1', 'port': 5432})
    require(not ipaddress.ip_address(service['host_path']['address']).is_loopback, 'SERVICE_HOST_PATH')
    admission.validate_connections(admission.parse(raw['connections.json']), run, source, service['fingerprint'], service['host_path'])
    return raw


def artifact():
    run = os.environ['RG06B_RUN_ID']
    require(re.fullmatch('[a-f0-9]{32}', run), 'RUN_ID')
    expected = PACKAGE / '.artifacts' / run
    require(os.environ['RG06B_ARTIFACT'] == str(expected), 'ARTIFACT_BOUNDARY')
    require(expected.is_dir() and not expected.is_symlink(), 'ARTIFACT_MISSING')
    return expected


def prepare():
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true', 'HOSTED_LINUX_CI_REQUIRED')
    run = uuid.uuid4().hex
    path = PACKAGE / '.artifacts' / run
    path.mkdir(parents=True, exist_ok=False)
    write(path / 'launch.json', {
        'executionMode': 'linux-ci', 'run': run,
        'head': output(['git', 'rev-parse', 'HEAD']),
        'githubRun': os.environ['GITHUB_RUN_ID'], 'githubAttempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'postgresImage': IMAGE, 'inputs': {n: digest(ROOT / n) for n in INPUTS},
        'serviceDisposal': 'GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS',
        'source_identity': source_identity(),
    })
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
        stream.write(f'RG06B_RUN_ID={run}\nRG06B_ARTIFACT={path}\n')
    print('RG06D PREPARED; no tests executed')


def stop_process(process, receipt):
    if process is None:
        return
    if process.poll() is None:
        receipt['terminationRequested'] = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            receipt['forced'] = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    receipt.update(exit=process.returncode, exited=process.returncode is not None, finishedAt=time.time())


def no_descendants(summary):
    # As a Linux subreaper, this harness adopts orphaned browser/server children.
    # Do not signal guessed PIDs or unrelated processes. Live descendants fail CI.
    deadline = time.monotonic() + 5
    summary['adoptedExits'] = []
    while time.monotonic() < deadline:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            summary['descendantsExited'] = True
            return
        if pid:
            summary['adoptedExits'].append({'pid': pid, 'exit': os.waitstatus_to_exitcode(status)})
        else:
            time.sleep(0.05)
    summary['descendantsExited'] = False


def run_tests():
    path = artifact()
    server = playwright = None
    server_receipt = {'started': False, 'exited': False, 'forced': False}
    test_receipt = {'started': False, 'exited': False, 'forced': False}
    summary = {'state': 'FAIL', 'run': path.name, 'sqlCleanup': 'NOT_VERIFIED',
               'serviceDisposal': 'GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS'}
    streams = []
    try:
        require(sys.platform == 'linux' and sys.version_info[:3] == (3, 12, 10)
                and os.environ.get('GITHUB_ACTIONS') == 'true', 'LINUX_PYTHON_VERSION')
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.restype = ctypes.c_int
        require(prctl(36, ctypes.c_ulong(1), 0, 0, 0) == 0, 'SUBREAPER_UNAVAILABLE')
        require(output(['node', '--version']) == 'v24.15.0', 'NODE_VERSION')
        require(output(['npm', '--version']) == '11.12.1', 'NPM_VERSION')
        require(output(['uv', 'self', 'version', '--short']) == '0.11.22', 'UV_VERSION')
        launch = admission.parse(admission.read(path, 'launch.json'))
        source = validate_launch(launch)
        require(all(digest(ROOT / n) == h for n, h in launch['inputs'].items()), 'SOURCE_OR_LOCK_CHANGED')
        unit_gate(path, source)
        preload_gate(path, source)
        locked = {p['name']: p['version'] for p in tomllib.loads((ROOT / 'uv.lock').read_text())['package']}
        runtime = {n: importlib.metadata.version(n) for n in
                   ('fastapi', 'psycopg', 'psycopg-binary', 'uvicorn', 'pydantic', 'starlette')}
        require(all(locked[n] == v for n, v in runtime.items()), 'PYTHON_LOCK_MISMATCH')
        for name, version in {'@playwright/test': '1.64.0', 'playwright': '1.64.0',
                              'playwright-core': '1.64.0', 'pg': '8.23.1'}.items():
            require(json.loads((PACKAGE / 'node_modules' / name / 'package.json').read_text())['version'] == version,
                    'NODE_PACKAGE_VERSION')
        catalog = json.loads((PACKAGE / 'node_modules/playwright-core/browsers.json').read_text())
        require(next(b for b in catalog['browsers'] if b['name'] == 'chromium')['revision'] == '1248', 'CHROMIUM_REVISION')
        browser = Path(output(['node', '--input-type=module', '-e',
                              'import {chromium} from ' + json.dumps((PACKAGE / 'node_modules/playwright/index.mjs').as_uri())
                              + '; console.log(chromium.executablePath())']))
        cache = Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']).resolve(strict=True)
        require(browser.is_file() and browser.resolve().is_relative_to(cache)
                and 'chromium-1248' in browser.parts, 'CHROMIUM_BOUNDARY')
        port = os.environ['RG06B_DB_PORT']
        require(port.isdigit() and 1024 <= int(port) <= 65535, 'DB_PORT')
        require(os.environ['RG06D_DB_PASSWORD'] == PASSWORD, 'CI_SERVICE_CREDENTIAL')
        dsn = f'postgresql://reqguard_rg06b:{PASSWORD}@127.0.0.1:{port}/reqguard_rg06b'
        service = service_admission(path, source)
        import psycopg
        # One bounded, independent connection. No fallback to an existing DB.
        with psycopg.connect(dsn, connect_timeout=5, options='-c statement_timeout=5000') as connection:
            admission.validate_client_target(connection.info.host, connection.info.port, service['host_target'])
            actual = admission.observe(connection)
            admission.validate_identity(actual, service['fingerprint'], service['host_path'])
            identity = connection.execute("SELECT current_database(), current_user, current_setting('server_version_num')").fetchone()
            require(identity == ('reqguard_rg06b', 'reqguard_rg06b', '170011'), 'DB_IDENTITY')
            require(connection.execute("SELECT to_regclass('public.analyses')").fetchone() == (None,), 'DB_NOT_FRESH')
            connection.execute((ROOT / 'db/001_init.sql').read_text())
            connection.commit()
            require(connection.execute('SELECT count(*) FROM public.analyses').fetchone() == (0,), 'DB_NOT_EMPTY')
        write(path / 'postgres-ready.json', {'database': identity[0], 'role': identity[1],
              'serverVersionNum': identity[2], 'freshSchemaCommitted': True,
              'pythonPackages': runtime, 'chromiumSha256': digest(browser)})
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            api_port = sock.getsockname()[1]
        require(api_port != int(port), 'PORT_COLLISION')
        env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
        env.update(DATABASE_URL=dsn, RG06B_PASSWORD=PASSWORD, RG06B_API_PORT=str(api_port),
                   RG06B_BASE_URL=f'http://127.0.0.1:{api_port}', PYTHONDONTWRITEBYTECODE='1')
        # These child-only values fulfill the existing RG-06B config/spec contract.
        for name in ('uvicorn.stdout', 'uvicorn.stderr', 'playwright.stdout', 'playwright.stderr'):
            streams.append((path / name).open('xb'))
        server = subprocess.Popen([sys.executable, '-B', str(ROOT / 'scripts/rg06d_admission.py')],
                                  cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                  stdout=streams[0], stderr=streams[1], start_new_session=True)
        server_receipt.update(started=True, pid=server.pid, startedAt=time.time())
        deadline = time.monotonic() + 60
        ready = False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            require(server.poll() is None, 'SERVER_EXIT_BEFORE_READY')
            try:
                with opener.open(env['RG06B_BASE_URL'] + '/', timeout=1) as response:
                    ready = response.status == 200
                if ready:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        require(ready and server.poll() is None, 'SERVER_READINESS_TIMEOUT')
        server_receipt['ready'] = True
        require(not env.get('NODE_OPTIONS'), 'AMBIENT_NODE_OPTIONS')
        env.update(RG06D_NODE_IDENTITY='1', NODE_OPTIONS='--import=' + (PACKAGE / 'ci-identity.mjs').as_uri())
        playwright = subprocess.Popen(['node', str(PACKAGE / 'node_modules/playwright/cli.js'),
                                       'test', '--config', str(PACKAGE / 'playwright.ci.config.ts'),
                                       '--project=chromium'], cwd=ROOT, env=env,
                                      stdin=subprocess.DEVNULL, stdout=streams[2], stderr=streams[3],
                                      start_new_session=True)
        test_receipt.update(started=True, pid=playwright.pid, startedAt=time.time())
        code = playwright.wait(timeout=160)
        test_receipt.update(exit=code, exited=True)
        require(code == 0 and server.poll() is None, 'PLAYWRIGHT_OR_SERVER_FAILED')
        report = json.loads((path / 'results.json').read_text())
        specs = []
        def collect(suites):
            for suite in suites:
                specs.extend(suite.get('specs', []))
                collect(suite.get('suites', []))
        collect(report['suites'])
        require({s['title'] for s in specs} == {
            'supported fixture: browser HTTP 200, visible result, independent committed SQL row',
            'invalid whitespace: actual FastAPI HTTP 422 and unchanged SQL snapshot',
            'unsupported fixture: browser HTTP 200, visible unsupported result, independent SQL NULL row',
        }, 'EXACT_THREE_SCENARIOS')
        require(report['stats']['expected'] == 3 and not report['errors']
                and all(report['stats'][k] == 0 for k in ('unexpected', 'skipped', 'flaky'))
                and len(specs) == 3 and all(s['ok'] and len(s['tests']) == 1
                and s['tests'][0]['projectName'] == 'chromium' and s['tests'][0]['status'] == 'expected'
                and len(s['tests'][0]['results']) == 1 and s['tests'][0]['results'][0]['status'] == 'passed'
                and s['tests'][0]['results'][0]['retry'] == 0 for s in specs), 'EXACT_THREE_RESULTS')
        validate_unsupported_receipts(read_unsupported_receipts(path), path.name)
        connections = [admission.parse(admission.read(path, p.name)) for p in sorted(path.glob('connection-*.json'))]
        write(path / 'connections.json', {'schema_version': 'rg06d-connections-v1', 'run_id': path.name,
                                         'source_identity': source, 'connections': connections})
        validate_launch(admission.parse(admission.read(path, 'launch.json')))
        validate_admission_bundle(path, source, path.name)
        summary.update(tests=report['stats'], sqlCleanup='VERIFIED', assertions='PASS')
    except BaseException as error:
        summary['reason'] = str(error) if isinstance(error, Stop) else 'EXECUTION_' + type(error).__name__
    finally:
        for process, receipt in [(playwright, test_receipt), (server, server_receipt)]:
            try:
                stop_process(process, receipt)
            except BaseException:
                receipt['terminationUnknown'] = True
        if server is not None:
            server_receipt['finishedAt'] = time.time()
        no_descendants(summary)
        for stream in streams:
            stream.close()
        # Uvicorn re-raises a handled SIGTERM after graceful lifespan shutdown.
        server_log = (path / 'uvicorn.stderr').read_text(errors='replace') if streams else ''
        server_receipt['gracefulShutdown'] = (
            server_receipt.get('terminationRequested') is True
            and server_receipt.get('exit') in (0, -signal.SIGTERM)
            and 'Application shutdown complete.' in server_log
            and 'Finished server process' in server_log)
        clean = (summary.get('assertions') == 'PASS' and server_receipt['gracefulShutdown']
                 and all(r['exited'] and not r['forced'] and not r.get('terminationUnknown')
                         for r in (server_receipt, test_receipt)) and summary['descendantsExited'])
        summary['state'] = 'PASS' if clean else 'FAIL'
        if not clean:
            summary.setdefault('reason', 'PROCESS_CLEANUP_NOT_VERIFIED')
        write(path / 'server-process.json', server_receipt)
        write(path / 'playwright-process.json', test_receipt)
        write(path / 'run-summary.json', summary)
    print('RG06D ' + summary['state'] + '; run=' + path.name)
    return 0 if summary['state'] == 'PASS' else 1


def publish():
    # A nonempty, separately created directory, never the raw artifacts tree.
    run_id, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    require(run_id.isdigit() and attempt.isdigit(), 'GITHUB_RUN_ID')
    safe = Path(os.environ['RUNNER_TEMP']) / f'rg06d-safe-{run_id}-{attempt}'
    safe.mkdir(exist_ok=False)
    publication = {'runOutcome': os.environ.get('RG06D_RUN_OUTCOME', 'unknown'),
                   'dependencyOutcome': os.environ.get('RG06D_DEPENDENCY_OUTCOME', 'unknown'),
                   'serviceDisposal': 'GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS',
                   'copied': [], 'rejected': [], 'binaryDiagnostics': 'NOT_PUBLISHED',
                   'note': 'Only allowlisted JSON and redacted text; no profiles, temp, traces or screenshots.'}
    # Write safe fallback evidence even if setup never reached the harness.
    write(safe / 'publication-context.json', publication)
    try:
        raw = artifact()
        source = validate_launch(admission.parse(admission.read(raw, 'launch.json')))
        admission_bytes = validate_admission_bundle(raw, source, raw.name)
        receipt_bytes = {}
        receipt_valid = False
        try:
            receipt_bytes = read_unsupported_receipts(raw)
            validate_unsupported_receipts(receipt_bytes, os.environ['RG06B_RUN_ID'])
            receipt_valid = True
        except (OSError, ValueError, Stop):
            publication['rejected'].append('UNSUPPORTED_EVIDENCE_INVALID')
        for name in JSON_ALLOWLIST + LOG_ALLOWLIST:
            source = raw / name
            if not source.exists():
                continue
            try:
                require(source.is_file() and not source.is_symlink() and source.stat().st_size <= 10_000_000,
                        'UNSAFE_ARTIFACT_FILE')
                if name in ADMISSION_FILES:
                    require(source.read_bytes() == admission_bytes[name], 'ADMISSION_EVIDENCE_CHANGED')
                    text = admission_bytes[name].decode('utf-8')
                elif name in UNSUPPORTED_EVIDENCE_FILES:
                    require(receipt_valid, 'UNSUPPORTED_EVIDENCE_INVALID')
                    require(source.read_bytes() == receipt_bytes[name], 'EVIDENCE_CHANGED')
                    text = receipt_bytes[name].decode('utf-8')
                else:
                    text = source.read_text(encoding='utf-8')
                if name in JSON_ALLOWLIST:
                    json.loads(text)
                text = text.replace(PASSWORD, '<redacted-ci-password>')
                text = re.sub(r'(?i)postgres(?:ql)?://[^\s\"\x27]+', '<redacted-dsn>', text)
                # Do not publish unexpected credentials, private keys or auth headers.
                require(not re.search(r'(?i)-----BEGIN .*PRIVATE KEY-----|\bBearer\s+\S+|'
                                      r'\b(?:gh[pousr]_|github_pat_|sk-proj-)[A-Za-z0-9_-]+|'
                                      r'https?://[^\s/:]+:[^\s@]+@', text), 'SENSITIVE_ARTIFACT')
                if name in JSON_ALLOWLIST:
                    json.loads(text)
                if name in UNSUPPORTED_EVIDENCE_FILES or name in ADMISSION_FILES:
                    expected_bytes = admission_bytes[name] if name in ADMISSION_FILES else receipt_bytes[name]
                    require(text.encode('utf-8') == expected_bytes, 'EVIDENCE_REDACTION_CHANGED')
                (safe / name).write_text(text, encoding='utf-8')
                publication['copied'].append(name)
            except (OSError, ValueError, Stop):
                publication['rejected'].append(name)
        if receipt_valid:
            # Revalidate the copied bytes, not a previous run-success flag.
            validate_unsupported_receipts(read_unsupported_receipts(safe), os.environ['RG06B_RUN_ID'])
            require(read_unsupported_receipts(raw) == receipt_bytes, 'EVIDENCE_CHANGED')
            validate_admission_bundle(safe, validate_launch(admission.parse(admission.read(safe, 'launch.json'))), raw.name)
            require({n: admission.read(raw, n) for n in ADMISSION_FILES} == admission_bytes, 'ADMISSION_EVIDENCE_CHANGED')
            # No lock spans this check and upload; later filesystem races remain possible.
    except (KeyError, OSError, ValueError, Stop, admission.AdmissionError):
        publication['rejected'].append('RAW_EVIDENCE_UNAVAILABLE')
    if publication['runOutcome'] == 'success':
        publication['rejected'].extend('MISSING_' + name for name in JSON_ALLOWLIST + LOG_ALLOWLIST
                                       if name not in publication['copied'])
    publication['files'] = {f.name: {'bytes': f.stat().st_size, 'sha256': digest(f)}
                            for f in safe.iterdir() if f.is_file()}
    write(safe / 'publication-manifest.json', publication)
    require(publication['copied'] and not publication['rejected'], 'EVIDENCE_PUBLICATION_INCOMPLETE')
    print('RG06D safe evidence prepared')


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'run', 'publish'), 'MODE')
        if sys.argv[1] == 'prepare':
            prepare()
        elif sys.argv[1] == 'publish':
            publish()
        else:
            sys.exit(run_tests())
    except Exception as error:
        print('RG06D STOP: ' + (str(error) if isinstance(error, Stop) else type(error).__name__))
        sys.exit(1)
