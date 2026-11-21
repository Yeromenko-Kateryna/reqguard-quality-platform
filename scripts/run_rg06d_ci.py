"""RG-06D only: Linux hosted CI, existing RG-06B specs, safe publication.

prepare/publish use only stdlib, including after dependency setup fails.
Read-only Docker admission only: GitHub owns service disposal, which this file cannot attest.
"""

import ctypes
from contextlib import contextmanager
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
import threading
import tomllib
import urllib.request
import uuid
from types import MappingProxyType
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


NETWORK_INSPECT_TIMEOUT = 15


def output(argv):
    if argv[:1] != ['docker'] or argv[3:5] != ['network', 'inspect']:
        return subprocess.check_output(argv, cwd=ROOT, stderr=subprocess.DEVNULL,
                                       text=True, timeout=15).strip()
    # One argv-only inspection, capped before allocation; no stderr capture.
    process = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ready = threading.Event()
    result = {}
    def read():
        try:
            result['raw'] = process.stdout.read(65537)
        except Exception as error:
            result['error'] = error
        finally:
            ready.set()
    reader = threading.Thread(target=read, daemon=True)
    started = time.monotonic()
    reader.start()
    try:
        if not ready.wait(NETWORK_INSPECT_TIMEOUT):
            raise subprocess.TimeoutExpired(argv, NETWORK_INSPECT_TIMEOUT)
        if 'error' in result:
            raise result['error']
        require(len(result['raw']) <= 65536, 'COMMAND_OUTPUT_SIZE')
        code = process.wait(timeout=max(0.01, NETWORK_INSPECT_TIMEOUT - (time.monotonic() - started)))
        if code:
            raise subprocess.CalledProcessError(code, argv)
        return result['raw'].decode('utf-8').strip()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=1)
        if not reader.is_alive():
            process.stdout.close()


def source_git(*args):
    try:
        return output(['git', '--no-replace-objects', *args])
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Stop('SOURCE_GIT_COMMAND') from None


def source_checkout():
    head = source_git('rev-parse', '--verify', 'HEAD')
    try:
        event = admission.parse(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    except (KeyError, OSError):
        raise Stop('SOURCE_EVENT_FILE') from None
    pr = admission.validate_execution_context(head, event, os.environ)
    require(source_git('cat-file', '-t', head) == 'commit', 'SOURCE_HEAD_OBJECT_TYPE')
    if pr is not None:
        # Raw object headers retain parent order even in a shallow checkout.
        headers = source_git('cat-file', 'commit', head).split('\n\n', 1)[0].splitlines()
        parents = [line[7:] for line in headers if line.startswith('parent ')]
        require(len(parents) == 2, 'SOURCE_MERGE_PARENT_COUNT')
        require(parents == [pr['base']['sha'], pr['head']['sha']], 'SOURCE_MERGE_PARENT_ORDER')
        for parent in parents:
            admission.source_oid(parent)
            require(source_git('cat-file', '-t', parent) == 'commit', 'SOURCE_PARENT_OBJECT_TYPE')
    return head, pr


def source_identity():
    head, pr = source_checkout()
    hashes = {n: digest(ROOT / n) for n in INPUTS}
    value = {'checkout_sha': head, 'pr_head_sha': pr['head']['sha'] if pr else None,
             'pr_base_sha': pr['base']['sha'] if pr else None,
             'tested_merge_sha': head if pr else None,
             'github_run_id': os.environ['GITHUB_RUN_ID'],
             'github_run_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'inputs': hashes,
             'python_lock_sha256': hashes['uv.lock'],
             'node_lock_sha256': hashes['quality/browser/package-lock.json']}
    admission.validate_source(value, value)
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
    reference = os.environ['RG06D_SERVICE_NETWORK']
    admission.require(admission.classify_network_reference(reference) != 'REJECT', 'SERVICE_NETWORK')
    context = output(['docker', 'context', 'show'])
    endpoint = output(['docker', 'context', 'inspect', context, '--format', '{{.Endpoints.docker.Host}}'])
    require(endpoint == 'unix:///var/run/docker.sock', 'JOB_DOCKER_ENDPOINT')
    docker = ['docker', '--context', context]
    engine = output(docker + ['info', '--format', '{{.ID}}'])
    require(bool(engine), 'ENGINE_ID')
    service_id = os.environ['RG06D_SERVICE_ID']
    require(re.fullmatch('[a-f0-9]{64}', service_id), 'SERVICE_ID')
    network_raw = output(docker + ['network', 'inspect', '--format',
        '{"Id":{{json .Id}},"Name":{{json .Name}}}', reference]).encode('utf-8')
    admission.require(0 < len(network_raw) <= 65536, 'SERVICE_NETWORK')
    network = admission.validate_network(admission.parse(network_raw), reference)
    fmt = ('{"Id":{{json .Id}},"Image":{{json .Image}},"State":{{json .State}},'
           '"Mounts":{{json .Mounts}},"NetworkSettings":{{json .NetworkSettings}}}')
    container = admission.parse(output(docker + ['inspect', service_id, '--format', fmt]).encode())
    image = admission.parse(output(docker + ['image', 'inspect', IMAGE, '--format',
        '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"RepoDigests":{{json .RepoDigests}}}']).encode())
    require(IMAGE.split('@')[1] in [s.split('@')[-1] for s in image['RepoDigests']], 'SERVICE_IMAGE_DIGEST')
    admission.validate_service(container, image, service_id, network['Id'], os.environ['RG06B_DB_PORT'], network['Name'])
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
    value = {'schema_version': 'rg06d-service-v3', 'run_id': path.name,
             'source_identity': source, 'container_id': service_id, 'engine_id': engine,
             'endpoint': endpoint, 'image': IMAGE, 'image_id': image['Id'],
             'network_reference': reference, 'network_name': network['Name'], 'network_id': network['Id'],
             'attachment_network_name': next(iter(container['NetworkSettings']['Networks'])),
             'attachment_network_id': next(iter(container['NetworkSettings']['Networks'].values()))['NetworkID'],
             'host_port': os.environ['RG06B_DB_PORT'],
             'fingerprint': fingerprint, 'service_observation': observed,
             'host_path': {'address': address, 'port': 5432},
             'host_target': {'host': '127.0.0.1', 'port': int(os.environ['RG06B_DB_PORT'])},
             'published_bindings': container['NetworkSettings']['Ports']['5432/tcp']}
    admission.validate_service_receipt(value, path.name, source, os.environ)
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
    admission.validate_service_receipt(service, run, source, os.environ)
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


# PREPARE-only proposal: fixed source-bound diagnostic vocabulary; never acceptance.
PREPARE_DIAGNOSTIC_ADMISSION_SHA256 = '9f126fcccb4949b04534a3ae5e02eca9bf3c9247984683071004b60266b6be18'
PREPARE_DIAGNOSTIC_FUNCTIONS = (
    ('A', 'require', '2c87fcb719ea6926e19c5f0aa7181d237f4bc16a2cfca703c00c51a9771d0cb1'),
    ('A', 'shape', '591fccfd5ae5148362f020ebf2eea35be0cdd6c1200f70dc055d760a409fe319'),
    ('A', 'parse', '231ee7d9a47e3a56ded5945cef152759c6c3e14e7369b160fa0c3b9b5d7dd895'),
    ('A', 'parse.<locals>.pairs', '437d2af775ff146249c87aed7f4418d17a154eac1a1646251feb794007aa11d7'),
    ('A', 'parse.<locals>.constant', '210e79266c47524300ca4b784d1007959af5207ac570d57bc7dca28c43c2ce9c'),
    ('A', 'source_oid', 'f550f0f51f20247eae5c23b083caf7f08561a7d48ad3437ba033e4508cefb49f'),
    ('A', 'repository_identity', 'c358b10d6469aba6171f1ce7b229040c678b6feb40831bfc3faaad75bf2c0685'),
    ('A', 'source_branch', '30bdc321bd2f6d122d98329a567be2d4434ceb4f17365ac0e0617debd2d8a739'),
    ('A', 'validate_execution_context', '95d3317737e9a3fe586ded83840b1fd9d432d630a8510fa6d8ccdefec04c3e1a'),
    ('A', 'validate_source', 'fb463b4811f64431a8ce246661def2e1c208530469cd58c89587a4b67d539bd0'),
    ('C', 'prepare', '6b42e309c3bfb85cc780ccb4c3b1bf5c3f376dcb80cb08d4b618e8a40e7b14ef'),
    ('C', 'source_checkout', '9d1f6615218a803495a36274b1cdcdd6e85ced8e9a445b6f1d58401841acf8df'),
    ('C', 'source_identity', '79da10948efc3e64d3c997047e68754c63268eb3f7cb5360de58a70987c02d20'),
)
PREPARE_DIAGNOSTIC_GUARDS = (
    ('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434', 'ADMISSION_FIELDS', 'P.G.01'),
    ('A', 'parse', '9e879d17b6bb6ecce8376c71815c39cbd51bd54d5e50a02d4a40e894ba4ba589', 'ADMISSION_SIZE', 'P.G.02'),
    ('A', 'parse.<locals>.pairs', '6a94a3ee0f0923d97393de748791c68a7cefc16b758432eb18c478798dcba5f6', 'ADMISSION_DUPLICATE_KEY', 'P.G.03'),
    ('A', 'parse.<locals>.constant', 'fe00cc081878eff5d8e9bf88c7e30fb1bb3e362c2df46d24b667e23d20ad24f4', 'ADMISSION_NONFINITE', 'P.G.04'),
    ('A', 'parse', '3f41418c7aa2b530cd1fdb13cb8c6093f69da2fc6059c990e731e6ea42344813', 'ADMISSION_JSON', 'P.G.05'),
    ('A', 'source_oid', '22b152a721437e7723066dd1a69744acb24d1d5fda799d7624f7536c1b2d6c8c', 'SOURCE_COMMIT_OID', 'P.G.06'),
    ('A', 'repository_identity', 'bdde0a1781a0e48a1bb3042c4a1a44b6414ac657a6d5c82a02799b04ee5be889', 'SOURCE_REPOSITORY_FIELDS', 'P.G.07'),
    ('A', 'repository_identity', 'a11d795f16ea60a61be93a94bda2bc572307c5430db3a4d2bb398d297091b6a4', 'SOURCE_REPOSITORY_OWNER', 'P.G.08'),
    ('A', 'repository_identity', '6b9a9d11bae11790c0892fd09a9f8c88c86740ec55e8b773d001b6c8656bb5f0', 'SOURCE_REPOSITORY_IDENTITY', 'P.G.09'),
    ('A', 'source_branch', '4724d876a85533335e66dbe67600830342f30a62a5914a221408f717899ce957', 'SOURCE_BRANCH', 'P.G.10'),
    ('A', 'validate_execution_context', 'da9c0168d900aeee066939b3b107a0cee88d592460cd85e6c229a083469bba5a', 'CHECKOUT_EVENT_SHA', 'P.G.11'),
    ('A', 'validate_execution_context', '7043bef210b1b27f714a7a36b883e1b3ae53d1d720a58e47710c9521293a2b73', 'SOURCE_EVENT_OBJECT', 'P.G.12'),
    ('A', 'validate_execution_context', 'cee0748bf79b92472972639deae0757f88de94c3b47e3469b3408fd2bc8e04f0', 'SOURCE_REPOSITORY_CONTEXT', 'P.G.13'),
    ('A', 'validate_execution_context', '49b0883f53ace410298d71acdb19cd48fa744cc7353f17dc86c45e9159efba36', 'SOURCE_PR_FIELDS', 'P.G.14'),
    ('A', 'validate_execution_context', 'a90c9fced66a8b0b566fdfe3c38ee391a5454c90cb069d682f84368198412100', 'SOURCE_PR_NUMBER', 'P.G.15'),
    ('A', 'validate_execution_context', 'd92bd0d3d2e974d868b418dd1ca112bd83a7726ed617046c38361069047d3583', 'SOURCE_PR_REF', 'P.G.16'),
    ('A', 'validate_execution_context', '5fea276a729ccb7197cea6b340d32b796a152ee45411bf6ac5c57c6b768f4cd6', 'SOURCE_PR_FIELDS', 'P.G.17'),
    ('A', 'validate_execution_context', 'a3c2a85803ef336853f7aa2877d52cef8e5ba48a192d610ea285c73e9a8c7ba3', 'SOURCE_PR_BRANCH_CONTEXT', 'P.G.18'),
    ('A', 'validate_execution_context', '2e8265aceff8d7a07be3b62da1a4d12d3f0a9702db40acc69976dbc6637ecd7b', 'SOURCE_PR_BASE_REPOSITORY', 'P.G.19'),
    ('A', 'validate_execution_context', '814822d7e1a8316ddd18d6b2c3ab55c7c6b85aa4a6cac8a505e1dc5c1edf335e', 'SOURCE_PR_HEAD_REPOSITORY', 'P.G.20'),
    ('A', 'validate_execution_context', 'dec77d133d53a660a13fa5fa4b9506c5b3e68a372d418c8458046ae53c4bb833', 'SOURCE_PR_HEAD_OWNER', 'P.G.21'),
    ('A', 'validate_execution_context', '9b9bec7632acfbdb5ef79d219006b5a150328d1183ad4cd8afd5f283d0fc96ae', 'SOURCE_PR_HEAD_REPOSITORY', 'P.G.22'),
    ('A', 'validate_execution_context', '9323a00194dc6aed7494d327c32101fb40d8fc89da592b13560ce764f47ec808', 'SOURCE_PR_HEAD_FORK', 'P.G.23'),
    ('A', 'validate_execution_context', '89fbdef200796b51bebed238243cdb92d2d8c52100e8f99237a30a92a4487123', 'SOURCE_PR_HEAD_USER', 'P.G.24'),
    ('A', 'validate_execution_context', 'f4038c6464a201b2d168e4bd374903c357026971746f2c05ba7b8f40608316bd', 'SOURCE_EVENT_KIND', 'P.G.25'),
    ('A', 'validate_execution_context', 'ae45b24dde9ec05028a0a841b307f7d05caa4f7080d4b9d849ba2f1755a3a93b', 'SOURCE_NON_PR_CONTEXT', 'P.G.26'),
    ('A', 'validate_execution_context', 'e35004864067cfcf5533764ccc8321daa05721e869d087059898d093ffaaf266', 'SOURCE_PUSH_CONTEXT', 'P.G.27'),
    ('A', 'validate_execution_context', '9c8e8f8b64d3d0a4f14feab09504d2774cce1aa9aaa90bd4d0b4f9697fded4ea', 'SOURCE_DISPATCH_CONTEXT', 'P.G.28'),
    ('A', 'validate_source', '13ad0213238e9730616108488c1d469db9d71dc312c3c6b4fc02ab1caf7801bd', 'SOURCE_MISMATCH', 'P.G.29'),
    ('A', 'validate_source', 'd11dbcd8b9c523a3309086c50b033152af97a225cface56e6402c7752d96288b', 'SOURCE_SHA', 'P.G.30'),
    ('A', 'validate_source', '776bfe3d02d36fe9aa19101209b2199621c9a5fd04a3d6c11084e5999a5a0250', 'SOURCE_MERGE', 'P.G.31'),
    ('A', 'validate_source', 'cf344991f1f9928868590568f1bca7205dbb8e4b7a7e4f79ab82d9a4812cae63', 'SOURCE_PR', 'P.G.32'),
    ('A', 'validate_source', 'e79f2b3a3b0bba3862c58fab36a369c5b9cc08db4ef5cd8dd41d1e67d6d4eefd', 'SOURCE_RUN', 'P.G.33'),
    ('A', 'validate_source', '82764f35a1c35e5be73e7ea02a65e266d686e32d228cdac2e5b9d9441b5a7d07', 'SOURCE_INPUTS', 'P.G.34'),
    ('A', 'validate_source', '9755fc94ec975fac6dbe6bfc4ad104e53ad8baece143a4d7066412d894cc2298', 'SOURCE_HASH', 'P.G.35'),
    ('A', 'validate_source', '836145ab13217348950fe0d5394c94b325cc812d9622f3a0f5d0de62602f9e7b', 'SOURCE_LOCK', 'P.G.36'),
)
PREPARE_DIAGNOSTIC_CALLERS = (
    ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710', 'P.C.01'),
    ('A', 'validate_execution_context', '2b059d7d9a757888aee00207f953c97b2a50cdc0416b9befbb7d5d708c2d5073', 'P.C.02'),
    ('A', 'validate_execution_context', '338d14b6e39e07631f6e0ca030336cc8b8bfe56dd1c8698ac6a782d080a94010', 'P.C.03'),
    ('A', 'validate_execution_context', '618d518ea89603fd7f19773aeb2160a973218ebc3d4e59c246e9aa9620eac90d', 'P.C.04'),
    ('A', 'validate_execution_context', '94e05bdc1acf8daa2ef0e59caba4856cf368a6256e031d34eafad965d7dad18c', 'P.C.05'),
    ('A', 'validate_execution_context', '86e5b4a96f616dc04609ae8408032d7f027dec3dd324b3fb84721b6bf90bbede', 'P.C.06'),
    ('A', 'validate_execution_context', '194cf3b43ab1441c9deebef3a7b87eb5c1f304bce9453cbce8d83466a958fc44', 'P.C.07'),
    ('A', 'validate_execution_context', 'd1f5508d01e1775f2e3e3edab6c71ec533ec93f03649fa7d7fa8d28788d51019', 'P.C.08'),
    ('A', 'validate_source', 'fb24fa6f3223f7f02d3f693f40859f7390015f831421170bf77e60da6087caa2', 'P.C.09'),
    ('C', 'source_checkout', 'c1b0d5fef8c0a3e6b621d4b5e564637c91d47234ee04788de4c1463db76b42dd', 'P.C.10'),
    ('C', 'source_checkout', '7a212172cb3797ad008de48b33cb89f00fda846e891cc2d0638bdab602dc960d', 'P.C.11'),
    ('C', 'source_checkout', '6d57750efc1a19ff2a12b00300615fc4336afdaf49f2f66df0d1768623cd7684', 'P.C.12'),
    ('C', 'source_identity', '83a0fef2c48b0cc9b0ea3c06fc107de3ff15a9ca9ab96b983e2ffc2e19bf0200', 'P.C.13'),
    ('C', 'source_identity', '39db25f7fb7fd8fccdf33031935af0456c2da354e0eeec8bb2ddb224a4d04861', 'P.C.14'),
    ('C', 'prepare', 'd65f21b4f46d5e6b8ef2f7862649574f757cb2367d3c4f3267c6f48642bddb5d', 'P.C.15'),
)


def prepare_diagnostic_output(value):
    """Independent literal vocabulary; registry data never enrolls output values."""
    unresolved = {'schema_version': 'rg06d-prepare-admission-v1', 'phase': 'PREPARE',
                  'guard_code': 'UNRESOLVED', 'call_sites': ['UNRESOLVED']}
    codes = frozenset(('ADMISSION_DUPLICATE_KEY', 'ADMISSION_FIELDS', 'ADMISSION_JSON', 'ADMISSION_NONFINITE', 'ADMISSION_SIZE', 'CHECKOUT_EVENT_SHA', 'SOURCE_BRANCH', 'SOURCE_COMMIT_OID', 'SOURCE_DISPATCH_CONTEXT', 'SOURCE_EVENT_KIND', 'SOURCE_EVENT_OBJECT', 'SOURCE_HASH', 'SOURCE_INPUTS', 'SOURCE_LOCK', 'SOURCE_MERGE', 'SOURCE_MISMATCH', 'SOURCE_NON_PR_CONTEXT', 'SOURCE_PR', 'SOURCE_PR_BASE_REPOSITORY', 'SOURCE_PR_BRANCH_CONTEXT', 'SOURCE_PR_FIELDS', 'SOURCE_PR_HEAD_FORK', 'SOURCE_PR_HEAD_OWNER', 'SOURCE_PR_HEAD_REPOSITORY', 'SOURCE_PR_HEAD_USER', 'SOURCE_PR_NUMBER', 'SOURCE_PR_REF', 'SOURCE_PUSH_CONTEXT', 'SOURCE_REPOSITORY_CONTEXT', 'SOURCE_REPOSITORY_FIELDS', 'SOURCE_REPOSITORY_IDENTITY', 'SOURCE_REPOSITORY_OWNER', 'SOURCE_RUN', 'SOURCE_SHA', 'UNRESOLVED'))
    sites = frozenset(('P.C.01', 'P.C.02', 'P.C.03', 'P.C.04', 'P.C.05', 'P.C.06', 'P.C.07', 'P.C.08', 'P.C.09', 'P.C.10', 'P.C.11', 'P.C.12', 'P.C.13', 'P.C.14', 'P.C.15', 'P.G.01', 'P.G.02', 'P.G.03', 'P.G.04', 'P.G.05', 'P.G.06', 'P.G.07', 'P.G.08', 'P.G.09', 'P.G.10', 'P.G.11', 'P.G.12', 'P.G.13', 'P.G.14', 'P.G.15', 'P.G.16', 'P.G.17', 'P.G.18', 'P.G.19', 'P.G.20', 'P.G.21', 'P.G.22', 'P.G.23', 'P.G.24', 'P.G.25', 'P.G.26', 'P.G.27', 'P.G.28', 'P.G.29', 'P.G.30', 'P.G.31', 'P.G.32', 'P.G.33', 'P.G.34', 'P.G.35', 'P.G.36', 'UNRESOLVED'))
    if type(value) is not dict or set(value) != set(unresolved):
        return unresolved
    if (type(value['schema_version']) is not str or value['schema_version'] != unresolved['schema_version']
            or type(value['phase']) is not str or value['phase'] != 'PREPARE'
            or type(value['guard_code']) is not str or value['guard_code'] not in codes
            or type(value['call_sites']) is not list or not 1 <= len(value['call_sites']) <= 16
            or any(type(site) is not str or site not in sites for site in value['call_sites'])):
        return unresolved
    return {'schema_version': unresolved['schema_version'], 'phase': 'PREPARE',
            'guard_code': value['guard_code'], 'call_sites': list(value['call_sites'])}


def prepare_admission_diagnostic(error):
    """Static attribution only: no args, locals, payload, env or path in output."""
    unresolved = {'schema_version': 'rg06d-prepare-admission-v1', 'phase': 'PREPARE',
                  'guard_code': 'UNRESOLVED', 'call_sites': ['UNRESOLVED']}
    if type(error) is not admission.AdmissionError:
        return unresolved
    try:
        registry = (PREPARE_DIAGNOSTIC_GUARDS, PREPARE_DIAGNOSTIC_CALLERS)
        if (type(registry[0]) is not tuple or len(registry[0]) != 36
                or type(registry[1]) is not tuple or len(registry[1]) != 15
                or any(type(row) is not tuple or any(type(v) is not str or len(v) > 128 for v in row)
                       for rows in registry for row in rows)
                or hashlib.sha256(json.dumps(registry, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
                   != 'aed8c620cc4175e84a1a9a04737bf674ec7c7b35e938e51773ca73f4828febfc'):
            return unresolved
        models = {}
        for label, path in (('A', Path(admission.__file__)), ('C', Path(__file__))):
            raw = path.read_bytes()
            if label == 'A' and hashlib.sha256(raw).hexdigest() != PREPARE_DIAGNOSTIC_ADMISSION_SHA256:
                return unresolved
            nodes = admission.function_nodes(admission.ast.parse(raw))
            compiled = {c.co_qualname: c for c in admission.nested_codes(
                compile(raw, str(path), 'exec', dont_inherit=True, optimize=0))}
            module = admission if label == 'A' else sys.modules[__name__]
            for owner, name, expected in PREPARE_DIAGNOSTIC_FUNCTIONS:
                if owner != label:
                    continue
                top = name.split('.<locals>.', 1)[0]
                live = next(c for c in admission.nested_codes(getattr(module, top).__code__)
                            if c.co_qualname == name)
                if admission.ast_fingerprint(nodes[name]) != expected or live != compiled[name]:
                    return unresolved
                models[id(live)] = (label, name, nodes[name])
        traces = []
        trace = error.__traceback__
        while trace is not None:
            if len(traces) == 32:
                return unresolved
            traces.append(trace)
            trace = trace.tb_next
        if not traces:
            return unresolved
        known = []
        json_codes = (json.loads.__code__, json.JSONDecoder.decode.__code__,
                      json.JSONDecoder.raw_decode.__code__)
        for trace in reversed(traces):
            model = models.get(id(trace.tb_frame.f_code))
            if model is None:
                if known and known[-1][1].startswith('parse') and trace.tb_frame.f_code in json_codes:
                    continue
                known.append(('?', '?', '?'))
                break
            label, name, node = model
            known.append((label, name, admission.traceback_operation(trace, node)))
            if (label, name) == ('C', 'prepare'):
                break
        if known and known[0][:2] == ('A', 'require'):
            node = models[id(admission.require.__code__)][2]
            raises = [admission.ast_fingerprint(n) for n in admission.ast.walk(node)
                      if isinstance(n, admission.ast.Raise)]
            if known[0][2] not in raises:
                return unresolved
            known = known[1:]
        matches = [r for r in PREPARE_DIAGNOSTIC_GUARDS if known and r[:3] == known[0]]
        if len(matches) != 1:
            return unresolved
        sites = [matches[0][4]]
        for frame in known[1:]:
            matches_call = [r[3] for r in PREPARE_DIAGNOSTIC_CALLERS if r[:3] == frame]
            sites.append(matches_call[0] if len(matches_call) == 1 else 'UNRESOLVED')
        if len(sites) > 16:
            return unresolved
        return prepare_diagnostic_output({'schema_version': 'rg06d-prepare-admission-v1', 'phase': 'PREPARE',
                'guard_code': matches[0][3], 'call_sites': sites})
    except Exception:
        return unresolved


def prepare_with_admission_diagnostics():
    try:
        prepare()
    except admission.AdmissionError as error:
        try:
            value = prepare_diagnostic_output(prepare_admission_diagnostic(error))
            text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            if len(text.encode('ascii')) <= 1024:
                print('RG06D PREPARE DIAGNOSTIC ' + text)
        except Exception:
            pass  # Diagnostics must never replace the original failure.
        raise


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


class RuntimeFailure:
    """Small stage cursor; failure diagnostics never confer acceptance."""
    def __init__(self, path):
        self.path = path
        self.source = None
        self.index = 0
        self.first = None
        self._source_bytes = None
        self._first_bytes = None
        self._persisted = False
        self._initial_attempted = False
        self._cleanup = 'PENDING'

    def completed(self, stage):
        require(self.first is None and admission.DIAGNOSTIC_STAGES[self.index] == stage,
                'DIAGNOSTIC_TRANSITION')
        self.index += 1

    def save(self):
        try:
            source = json.loads(self._source_bytes)
            value = json.loads(self._first_bytes)
            value['cleanup_status'] = self._cleanup
            raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
            if not self._persisted:
                admission.require(not self._initial_attempted, 'DIAGNOSTIC_INITIAL_UNAVAILABLE')
                self._initial_attempted = True
                identity = admission.begin_capture(self.path)
                admission.atomic_failure(self.path, raw, self.path.name, source)
                admission.confirm_capture(self.path, identity, raw, self.path.name, source)
                self._persisted = True
            else:
                admission.require(not admission.capture_denied(self.path), 'DIAGNOSTIC_CAPTURE_DENIED')
                admission.atomic_failure(self.path, raw, self.path.name, source)
        except Exception:
            print('DIAGNOSTIC_UNAVAILABLE')

    def failed(self, error):
        if self.first is not None:
            return
        # Latch before classification/I/O. Capture failure cannot be recaptured later.
        self.first = MappingProxyType({})
        try:
            stage = admission.DIAGNOSTIC_STAGES[self.index]
            source = json.loads(json.dumps(self.source, allow_nan=False))
            identity, reference = admission.diagnostic_binding(self.path.name, source)
            code, original, site = admission.attribute_first_error(
                error, stage, source, FIRST_ERROR_RUNNER_CODES, Stop)
            value = {'last_completed_runtime_stage': admission.DIAGNOSTIC_STAGES[self.index - 1]
                     if self.index else 'NONE', 'first_failed_runtime_stage': stage,
                     'allowlisted_failure_code': code, 'cleanup_status': 'PENDING',
                     'schema_version': 'rg06d-failure-diagnostic-v2',
                     'run_identity': identity, 'source_identity_reference': reference,
                     'first_admission_error_code': original, 'first_admission_call_site': site}
            self._source_bytes = json.dumps(source, sort_keys=True, allow_nan=False).encode('ascii')
            self._first_bytes = json.dumps(value, sort_keys=True, allow_nan=False).encode('ascii')
            self.first = MappingProxyType({k: v for k, v in value.items()
                                           if k not in ('run_identity', 'source_identity_reference')})
            self.save()
        except Exception:
            print('DIAGNOSTIC_UNAVAILABLE')

    def cleanup(self, server_receipt, test_receipt, summary, raised):
        if self.first is None or not self._persisted or self._cleanup != 'PENDING':
            return
        complete = (not raised and summary.get('descendantsExited') is True
                    and all(not r['started'] or (r['exited'] and not r['forced']
                            and not r.get('terminationUnknown')) for r in (server_receipt, test_receipt))
                    and (not server_receipt['started'] or server_receipt.get('gracefulShutdown') is True))
        self._cleanup = 'COMPLETED' if complete else 'FAILED_OR_UNVERIFIED'
        self.save()


@contextmanager
def diagnostic_cleanup(tracker, server_receipt, test_receipt, summary):
    try:
        yield
    except BaseException as error:
        tracker.failed(error)
        raise
    finally:
        tracker.cleanup(server_receipt, test_receipt, summary, sys.exc_info()[0] is not None)


def run_tests():
    try:
        path = artifact()
    except Exception:
        print('DIAGNOSTIC_UNAVAILABLE')
        raise
    server = playwright = None
    server_receipt = {'started': False, 'exited': False, 'forced': False}
    test_receipt = {'started': False, 'exited': False, 'forced': False}
    summary = {'state': 'FAIL', 'run': path.name, 'sqlCleanup': 'NOT_VERIFIED',
               'serviceDisposal': 'GITHUB_MANAGED_NOT_ATTESTED_BY_HARNESS'}
    streams = []
    failure = RuntimeFailure(path)
    try:
        failure.source = source_identity()
        require(sys.platform == 'linux' and sys.version_info[:3] == (3, 12, 10)
                and os.environ.get('GITHUB_ACTIONS') == 'true', 'LINUX_PYTHON_VERSION')
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.restype = ctypes.c_int
        require(prctl(36, ctypes.c_ulong(1), 0, 0, 0) == 0, 'SUBREAPER_UNAVAILABLE')
        require(output(['node', '--version']) == 'v24.15.0', 'NODE_VERSION')
        require(output(['npm', '--version']) == '11.12.1', 'NPM_VERSION')
        require(output(['uv', 'self', 'version', '--short']) == '0.11.22', 'UV_VERSION')
        failure.completed('EARLY_CHECKS')
        launch = admission.parse(admission.read(path, 'launch.json'))
        source = validate_launch(launch)
        require(all(digest(ROOT / n) == h for n, h in launch['inputs'].items()), 'SOURCE_OR_LOCK_CHANGED')
        failure.completed('SOURCE_INTEGRITY')
        unit_gate(path, source)
        failure.completed('OWNERSHIP_UNIT')
        preload_gate(path, source)
        failure.completed('PG_PRELOAD')
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
        failure.completed('RUNTIME_PACKAGES')
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
        failure.completed('POSTGRESQL_ADMISSION')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            api_port = sock.getsockname()[1]
        require(api_port != int(port), 'PORT_COLLISION')
        env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
        env.update(DATABASE_URL=dsn, RG06B_PASSWORD=PASSWORD, RG06B_API_PORT=str(api_port),
                   RG06B_BASE_URL=f'http://127.0.0.1:{api_port}', PYTHONDONTWRITEBYTECODE='1')
        admission.validate_source_domain(source)
        env['RG06D_EXPECTED_SOURCE_IDENTITY_SHA256'] = admission.diagnostic_binding(path.name, source)[1]['source_identity_sha256']
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
        failure.completed('API_SERVER')
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
        failure.completed('CHROMIUM')
        validate_unsupported_receipts(read_unsupported_receipts(path), path.name)
        connections = [admission.parse(admission.read(path, p.name)) for p in sorted(path.glob('connection-*.json'))]
        write(path / 'connections.json', {'schema_version': 'rg06d-connections-v1', 'run_id': path.name,
                                         'source_identity': source, 'connections': connections})
        validate_launch(admission.parse(admission.read(path, 'launch.json')))
        validate_admission_bundle(path, source, path.name)
        summary.update(tests=report['stats'], sqlCleanup='VERIFIED', assertions='PASS')
        failure.completed('EVIDENCE_VALIDATION')
    except BaseException as error:
        failure.failed(error)
        # Only bounded classification, never dynamic exception text/class names.
        summary['reason'] = (failure.first.get('allowlisted_failure_code', 'EXECUTION_EXCEPTION')
                             if failure.first is not None else 'EXECUTION_EXCEPTION')
    finally:
        with diagnostic_cleanup(failure, server_receipt, test_receipt, summary):
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
                failure.failed(Stop('PROCESS_CLEANUP_NOT_VERIFIED'))
                summary.setdefault('reason', 'PROCESS_CLEANUP_NOT_VERIFIED')
            write(path / 'server-process.json', server_receipt)
            write(path / 'playwright-process.json', test_receipt)
            write(path / 'run-summary.json', summary)
    print('RG06D ' + summary['state'] + '; run=' + path.name)
    return 0 if summary['state'] == 'PASS' else 1


def publish_failure(raw, safe, publication):
    """Independent source-bound diagnostic path, never part of copied acceptance."""
    target = safe / admission.DIAGNOSTIC_NAME
    try:
        require(publication['runOutcome'] == 'failure', 'DIAGNOSTIC_CONTEXT')
        require(raw.name == os.environ['RG06B_RUN_ID'], 'DIAGNOSTIC_EXECUTION_CONTEXT')
        require(not admission.capture_denied(raw), 'DIAGNOSTIC_CAPTURE_DENIED')
        directory_identity = admission.capture_directory(raw)
        source = source_identity()
        require(source['github_run_id'] == os.environ['GITHUB_RUN_ID']
                and source['github_run_attempt'] == os.environ['GITHUB_RUN_ATTEMPT'], 'DIAGNOSTIC_CI_CONTEXT')
        original = admission.read_failure(raw, raw.name, source)
        admission.atomic_failure(safe, original, raw.name, source)
        require(admission.read_failure(safe, raw.name, source) == original, 'DIAGNOSTIC_COPY_CHANGED')
        require(admission.read_failure(raw, raw.name, source) == original, 'DIAGNOSTIC_RAW_CHANGED')
        require(admission.capture_directory(raw) == directory_identity
                and not admission.capture_denied(raw), 'DIAGNOSTIC_CAPTURE_CHANGED')
        publication['diagnosticPublication'] = 'PUBLISHED'
    except Exception:
        # safe is newly created; remove only this diagnostic copy, never raw files.
        if target.exists() or target.is_symlink():
            target.unlink()
        publication['diagnosticPublication'] = 'DIAGNOSTIC_UNAVAILABLE'


def reject_unexpected_git_metadata(value):
    """Other public receipts must never acquire opaque Playwright Git metadata."""
    def visit(item, depth=0):
        require(depth <= 64, 'PUBLIC_METADATA_DEPTH')
        if type(item) is dict:
            require(not any(k.casefold() in ('gitcommit', 'gitdiff') for k in item),
                    'UNEXPECTED_GIT_METADATA')
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
    visit(value)


def sanitize_playwright_results(raw, checkout_sha):
    """Narrow deterministic public metadata projection; preserve test evidence."""
    require(type(checkout_sha) is str and re.fullmatch('[a-f0-9]{40}', checkout_sha),
            'PUBLIC_RESULTS_SOURCE')
    try:
        report = parse_evidence_json(raw)
    except (RecursionError, ValueError, UnicodeError):
        raise Stop('PUBLIC_RESULTS_JSON') from None
    require(type(report) is dict and set(report) == {'config', 'suites', 'errors', 'stats'}
            and type(report['config']) is dict and type(report['suites']) is list
            and type(report['errors']) is list and type(report['stats']) is dict,
            'PUBLIC_RESULTS_SHAPE')
    config = report['config']
    require(type(config.get('projects')) is list, 'PUBLIC_RESULTS_PROJECTS')
    containers = [(config, ('config',))]
    for key in ('projects', 'filteredProjects'):
        if key not in config:
            continue
        require(type(config[key]) is list and all(type(p) is dict for p in config[key]),
                'PUBLIC_RESULTS_PROJECTS')
        containers.extend((p, ('config', key, str(i))) for i, p in enumerate(config[key]))
    allowed_git_paths = set()
    for container, path in containers:
        if 'metadata' not in container:
            continue
        metadata = container['metadata']
        require(type(metadata) is dict and set(metadata) <= {'ci', 'gitCommit', 'gitDiff', 'actualWorkers'},
                'PUBLIC_METADATA_FIELDS')
        public = {}
        if 'actualWorkers' in metadata:
            require(type(metadata['actualWorkers']) is int and metadata['actualWorkers'] >= 0,
                    'PUBLIC_METADATA_WORKERS')
            public['actualWorkers'] = metadata['actualWorkers']
        if 'gitCommit' in metadata:
            git = metadata['gitCommit']
            require(type(git) is dict and set(git) <= {'hash', 'shortHash', 'subject', 'body', 'branch', 'author', 'committer'}
                    and git.get('hash') == checkout_sha, 'PUBLIC_GIT_COMMIT')
            for role in ('author', 'committer'):
                if role in git:
                    person = git[role]
                    require(type(person) is dict and set(person) <= {'name', 'email', 'time'}
                            and all(type(person[k]) is str for k in ('name', 'email') if k in person)
                            and ('time' not in person or type(person['time']) in (int, float)),
                            'PUBLIC_GIT_IDENTITY_SHAPE')
            for key in ('subject', 'body', 'branch'):
                require(key not in git or type(git[key]) is str, 'PUBLIC_GIT_TEXT_SHAPE')
            public['gitCommit'] = {'hash': checkout_sha}
            if 'shortHash' in git:
                short = git['shortHash']
                require(type(short) is str and re.fullmatch('[a-f0-9]{7,40}', short)
                        and checkout_sha.startswith(short), 'PUBLIC_GIT_SHORT_HASH')
                public['gitCommit']['shortHash'] = short
            allowed_git_paths.add(path + ('metadata', 'gitCommit'))
        if 'ci' in metadata:
            ci = metadata['ci']
            require(type(ci) is dict and set(ci) <= {'commitHref', 'commitHash', 'prHref', 'prTitle', 'prBaseHash', 'buildHref', 'branch'}
                    and all(v is None or type(v) is str for v in ci.values()), 'PUBLIC_CI_METADATA')
            clean_ci = {}
            if 'commitHash' in ci:
                require(ci['commitHash'] == checkout_sha, 'PUBLIC_CI_COMMIT')
                clean_ci['commitHash'] = checkout_sha
            if 'prBaseHash' in ci:
                require(type(ci['prBaseHash']) is str and re.fullmatch('[a-f0-9]{40}', ci['prBaseHash']),
                        'PUBLIC_CI_BASE')
                clean_ci['prBaseHash'] = ci['prBaseHash']
            public['ci'] = clean_ci
        if 'gitDiff' in metadata:
            require(type(metadata['gitDiff']) is str, 'PUBLIC_GIT_DIFF_SHAPE')
        container['metadata'] = public
    def validate(item, path=(), depth=0):
        require(depth <= 64, 'PUBLIC_METADATA_DEPTH')
        if type(item) is dict:
            for key, value in item.items():
                if key.casefold() in ('gitcommit', 'gitdiff'):
                    require(path + (key,) in allowed_git_paths and key == 'gitCommit',
                            'UNEXPECTED_GIT_METADATA')
                validate(value, path + (key,), depth + 1)
        elif type(item) is list:
            for i, value in enumerate(item):
                validate(value, path + (str(i),), depth + 1)
    validate(report)
    try:
        text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
    except (ValueError, UnicodeError):
        raise Stop('PUBLIC_RESULTS_JSON') from None
    require(not re.search(r'(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|GitCommitInfo:', text),
            'PUBLIC_IDENTITY_TEXT')
    return text.encode('utf-8')


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
                   'diagnosticPublication': 'DIAGNOSTIC_UNAVAILABLE',
                   'note': 'Only allowlisted JSON and redacted text; no profiles, temp, traces or screenshots.'}
    # Write safe fallback evidence even if setup never reached the harness.
    write(safe / 'publication-context.json', publication)
    try:
        raw = artifact()
        if publication['runOutcome'] == 'failure':
            publish_failure(raw, safe, publication)
        source = validate_launch(admission.parse(admission.read(raw, 'launch.json')))
        public_checkout_sha = source['checkout_sha']
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
                elif name == 'results.json':
                    original_results = source.read_bytes()
                    text = sanitize_playwright_results(original_results, public_checkout_sha).decode('utf-8')
                else:
                    text = source.read_text(encoding='utf-8')
                if name in JSON_ALLOWLIST:
                    value = json.loads(text)
                    if name != 'results.json':
                        reject_unexpected_git_metadata(value)
                text = text.replace(PASSWORD, '<redacted-ci-password>')
                text = re.sub(r'(?i)postgres(?:ql)?://[^\s\"\x27]+', '<redacted-dsn>', text)
                # Do not publish unexpected credentials, private keys or auth headers.
                require(not re.search(r'(?i)-----BEGIN .*PRIVATE KEY-----|\bBearer\s+\S+|'
                                      r'\b(?:gh[pousr]_|github_pat_|sk-proj-)[A-Za-z0-9_-]+|'
                                      r'https?://[^\s/:]+:[^\s@]+@', text), 'SENSITIVE_ARTIFACT')
                require(not re.search(r'(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|GitCommitInfo:', text),
                        'PUBLIC_IDENTITY_TEXT')
                if name in JSON_ALLOWLIST:
                    json.loads(text)
                if name in UNSUPPORTED_EVIDENCE_FILES or name in ADMISSION_FILES:
                    expected_bytes = admission_bytes[name] if name in ADMISSION_FILES else receipt_bytes[name]
                    require(text.encode('utf-8') == expected_bytes, 'EVIDENCE_REDACTION_CHANGED')
                (safe / name).write_text(text, encoding='utf-8', newline='\n')
                publication['copied'].append(name)
                if name == 'results.json':
                    publication.setdefault('sanitized', {})[name] = {
                        'schema': 'rg06d-public-playwright-metadata-v1',
                        'source_sha256': hashlib.sha256(original_results).hexdigest(),
                        'published_sha256': digest(safe / name),
                    }
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




FIRST_ERROR_RUNNER_CODES = tuple(('C', f.__code__) for f in (require, service_admission, run_tests))


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'run', 'publish'), 'MODE')
        if sys.argv[1] == 'prepare':
            prepare_with_admission_diagnostics()
        elif sys.argv[1] == 'publish':
            publish()
        else:
            sys.exit(run_tests())
    except Exception as error:
        print('RG06D STOP: ' + (str(error) if isinstance(error, Stop) else type(error).__name__))
        sys.exit(1)
