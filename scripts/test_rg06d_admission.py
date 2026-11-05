"""Synthetic deterministic admission tests. Never connect to Docker, PostgreSQL or GitHub."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rg06d_admission as a
import run_rg06d_ci as ci

RUN = 'a' * 32
SOURCE = {'checkout_sha': 'b' * 40, 'pr_head_sha': None, 'pr_base_sha': None,
          'tested_merge_sha': None, 'github_run_id': '123', 'github_run_attempt': '1',
          'inputs': {'uv.lock': 'c' * 64, 'quality/browser/package-lock.json': 'd' * 64},
          'python_lock_sha256': 'c' * 64, 'node_lock_sha256': 'd' * 64}
FP = {'db': 'reqguard_rg06b', 'role': 'reqguard_rg06b', 'version': '170011',
      'system_id': '1234567'}
SERVER_PATH = {'address': '172.18.0.2', 'port': 5432}
TARGET = {'host': '127.0.0.1', 'port': 49123}
OBS = {**FP, **SERVER_PATH, 'backend_pid': 123}
ENV = {'RG06D_SERVICE_ID': 'e' * 64, 'RG06D_SERVICE_NETWORK': 'f' * 64, 'RG06B_DB_PORT': '49123',
       'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'RG06B_RUN_ID': RUN}


def encoded(value):
    return json.dumps(value, allow_nan=False).encode()


def preservation():
    row = {'run_id': '00000001-0000-4000-8000-000000000001', 'provider': 'fake',
           'status': 'unsupported_fixture', 'original_input': 'RG06B synthetic foreign fixture ' + 'c' * 32,
           'analysis_payload': None, 'sql_null': True, 'created_at': '2026-11-05 12:00:00+00'}
    return {'schema_version': 'rg06d-ownership-v1', 'run_id': RUN, 'source_identity': copy.deepcopy(SOURCE),
            'scenario': 'foreign-row-rejection', 'foreign_run_id': row['run_id'], 'registry_owner': 'c' * 32,
            'ownership_rejection': 'OwnershipRejected', 'sql_dispatch_count': 0, 'delete_dispatch_count': 0,
            'foreign_row_before': row, 'foreign_row_after': copy.deepcopy(row),
            'preservation_verified': True, 'preservation_verified_before_teardown': True,
            'fixture_teardown': 'NOT_ATTEMPTED'}


def ownership_pair(before=None):
    before = preservation() if before is None else before
    raw = encoded(before)
    final = {**copy.deepcopy(before), 'fixture_teardown': 'COMMITTED_BASELINE_RESTORED',
             'preservation_sha256': hashlib.sha256(raw).hexdigest()}
    return raw, final


def unit():
    return {'schema_version': 'rg06d-unit-v1', 'run_id': RUN, 'source_identity': copy.deepcopy(SOURCE), 'exit_code': 0,
            'report': {'cases': [{'name': n, 'passed': True, 'skip': False, 'todo': False, 'nesting': 0} for n in a.UNIT_NAMES],
                       'summary': {'tests': 4, 'passed': 4, 'failed': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0, 'suites': 0}}}


def preload():
    return {'schema_version': 'rg06d-preload-v1', 'run_id': RUN, 'source_identity': copy.deepcopy(SOURCE),
            'pg_version': '8.23.1', 'exit_code': 0,
            'report': {'cases': [{'name': a.PRELOAD_NAME, 'passed': True, 'skip': False, 'todo': False, 'nesting': 0}],
                       'summary': {'tests': 1, 'passed': 1, 'failed': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0, 'suites': 0}}}


def connections():
    return {'schema_version': 'rg06d-connections-v1', 'run_id': RUN, 'source_identity': copy.deepcopy(SOURCE),
            'connections': [{'receipt_id': str(i) * 32, 'kind': k, 'identity': dict(OBS)}
                            for i, k in enumerate(('api', 'api', 'verifier'), 1)]}


def bundle(directory):
    raw, final = ownership_pair()
    (directory / 'ownership-preservation.json').write_bytes(raw)
    a.write(directory, 'ownership.json', final)
    a.write(directory, 'ownership-unit.json', unit())
    a.write(directory, 'pg-preload.json', preload())
    a.write(directory, 'connections.json', connections())
    a.write(directory, 'service-identity.json', {'schema_version': 'rg06d-service-v2', 'run_id': RUN,
            'source_identity': SOURCE, 'container_id': ENV['RG06D_SERVICE_ID'], 'engine_id': 'synthetic-engine',
            'endpoint': 'unix:///var/run/docker.sock', 'image': ci.IMAGE, 'image_id': 'sha256:' + 'e' * 64,
            'network_id': ENV['RG06D_SERVICE_NETWORK'], 'host_port': '49123', 'fingerprint': FP,
            'service_observation': {**FP, 'address': '127.0.0.1', 'port': 5432, 'backend_pid': 99},
            'host_path': SERVER_PATH, 'host_target': TARGET,
            'published_bindings': [{'HostIp': '0.0.0.0', 'HostPort': '49123'}]})


class EvidenceTests(unittest.TestCase):
    def test_positive_ownership(self):
        raw, final = ownership_pair()
        a.validate_ownership(encoded(final), raw, RUN, SOURCE)

    def test_strict_json(self):
        for raw in (b'', b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{}' * 500001):
            with self.subTest(raw=raw[:30]), self.assertRaises(a.AdmissionError):
                a.parse(raw)

    def test_reject_bad_ownership_observations(self):
        mutations = [
            lambda p: p.update(sql_dispatch_count=1),
            lambda p: p.update(delete_dispatch_count=1),
            lambda p: p.update(sql_dispatch_count=0, delete_dispatch_count=2),
            lambda p: p.update(sql_dispatch_count=False),
            lambda p: p.update(delete_dispatch_count=-1),
            lambda p: p.update(preservation_verified_before_teardown=False),
            lambda p: p.update(preservation_verified=False),
            lambda p: p.update(run_id='d' * 32),
            lambda p: p.update(foreign_run_id='00000002-0000-4000-8000-000000000002'),
            lambda p: p['foreign_row_after'].update(original_input='changed'),
            lambda p: p['foreign_row_after'].update(sql_null=1),
            lambda p: p.update(ownership_rejection='PASS'),
            lambda p: p.update(extra='unexpected'),
            lambda p: p['source_identity'].update(checkout_sha='e' * 40),
        ]
        for mutate in mutations:
            p = preservation(); mutate(p); raw, final = ownership_pair(p)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises((a.AdmissionError, ValueError)):
                a.validate_ownership(encoded(final), raw, RUN, SOURCE)

    def test_failed_or_ambiguous_teardown_and_late_preservation(self):
        for state in ('FAILED', 'UNKNOWN', 'NOT_ATTEMPTED'):
            raw, final = ownership_pair(); final['fixture_teardown'] = state
            with self.subTest(state=state), self.assertRaises(a.AdmissionError):
                a.validate_ownership(encoded(final), raw, RUN, SOURCE)
        p = preservation(); p['fixture_teardown'] = 'COMMITTED_BASELINE_RESTORED'
        raw, final = ownership_pair(p)
        with self.assertRaises(a.AdmissionError):
            a.validate_ownership(encoded(final), raw, RUN, SOURCE)

    def test_preservation_changed_or_hash_mismatched(self):
        raw, final = ownership_pair(); final['preservation_sha256'] = '0' * 64
        with self.assertRaises(a.AdmissionError):
            a.validate_ownership(encoded(final), raw, RUN, SOURCE)
        raw, final = ownership_pair(); final['foreign_row_before']['original_input'] = 'changed'
        with self.assertRaises(a.AdmissionError):
            a.validate_ownership(encoded(final), raw, RUN, SOURCE)

    def test_unit_validation_and_negative_results(self):
        a.validate_unit(unit(), RUN, SOURCE)
        mutations = [lambda u: u.update(exit_code=1), lambda u: u.update(report=None),
                     lambda u: u['report']['cases'].pop(),
                     lambda u: u['report']['cases'].append(copy.deepcopy(u['report']['cases'][0])),
                     lambda u: u['report']['cases'][0].update(skip=True),
                     lambda u: u['report']['cases'][0].update(passed=False),
                     lambda u: u['report']['summary'].update(cancelled=1),
                     lambda u: u['report']['summary'].update(passed=3),
                     lambda u: u.update(run_id='f' * 32)]
        for mutate in mutations:
            value = unit(); mutate(value)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises((a.AdmissionError, TypeError)):
                a.validate_unit(value, RUN, SOURCE)

    def test_source_relationships(self):
        a.validate_source(SOURCE, SOURCE)
        for key, value in (('python_lock_sha256', 'f' * 64), ('tested_merge_sha', 'e' * 40),
                           ('github_run_id', '0'), ('pr_head_sha', 'e' * 40)):
            source = copy.deepcopy(SOURCE); source[key] = value
            with self.subTest(key=key), self.assertRaises(a.AdmissionError):
                a.validate_source(source, source)
        with self.assertRaises(a.AdmissionError):
            a.validate_source(SOURCE, {**SOURCE, 'checkout_sha': 'e' * 40})

    def test_missing_duplicate_and_copied_evidence(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', ENV):
            directory = Path(temp); raw = directory / 'raw'; safe = directory / 'safe'; raw.mkdir()
            bundle(raw); ci.validate_admission_bundle(raw, SOURCE, RUN)
            shutil.copytree(raw, safe); ci.validate_admission_bundle(safe, SOURCE, RUN)
            a.write(raw, 'ownership-copy.json', {})
            with self.assertRaises(ci.Stop):
                ci.validate_admission_bundle(raw, SOURCE, RUN)
            (safe / 'ownership.json').unlink()
            with self.assertRaises((ci.Stop, FileNotFoundError)):
                ci.validate_admission_bundle(safe, SOURCE, RUN)

    def test_missing_unit_and_corrupt_ownership_files(self):
        for name, raw in (('ownership-unit.json', None), ('ownership.json', b'{'),
                          ('ownership.json', b'{"run_id":"a","run_id":"b"}')):
            with self.subTest(name=name, raw=raw), tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', ENV):
                directory = Path(temp); bundle(directory)
                if raw is None: (directory / name).unlink()
                else: (directory / name).write_bytes(raw)
                with self.assertRaises((a.AdmissionError, ci.Stop, FileNotFoundError)):
                    ci.validate_admission_bundle(directory, SOURCE, RUN)

    def test_actual_reporter_handoff_is_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / RUN; directory.mkdir()
            ci.unit_gate(directory, SOURCE)
            a.validate_unit(a.parse(a.read(directory, 'ownership-unit.json')), RUN, SOURCE)

    def test_publication_revalidates_copied_bundle(self):
        # Isolate the preexisting legacy receipt validator; exercise the real new
        # publisher/copy/validator path with synthetic admission receipts only.
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); raw = directory / RUN; raw.mkdir(); bundle(raw)
            for name in ci.JSON_ALLOWLIST:
                if not (raw / name).exists(): a.write(raw, name, {})
            for name in ci.LOG_ALLOWLIST: (raw / name).write_text('synthetic diagnostic\n')
            env = {**ENV, 'RUNNER_TEMP': temp, 'RG06D_RUN_OUTCOME': 'success'}
            with patch.dict('os.environ', env), patch.object(ci, 'artifact', return_value=raw), \
                 patch.object(ci, 'validate_launch', return_value=SOURCE), \
                 patch.object(ci, 'validate_unsupported_receipts'):
                ci.publish()
            safe = directory / 'rg06d-safe-123-1'
            with patch.dict('os.environ', ENV): ci.validate_admission_bundle(safe, SOURCE, RUN)
            final = a.parse(a.read(safe, 'ownership.json')); final['delete_dispatch_count'] = 1
            (safe / 'ownership.json').write_bytes(encoded(final))
            with patch.dict('os.environ', ENV), self.assertRaises(a.AdmissionError):
                ci.validate_admission_bundle(safe, SOURCE, RUN)

    def test_missing_or_ambiguous_api_sql_identity(self):
        a.validate_connections(connections(), RUN, SOURCE, FP, SERVER_PATH)
        for change in ('missing', 'duplicate', 'mismatch'):
            value = connections()
            if change == 'missing': value['connections'].pop()
            if change == 'duplicate': value['connections'][1]['receipt_id'] = value['connections'][0]['receipt_id']
            if change == 'mismatch': value['connections'][0]['identity']['system_id'] = '999'
            with self.subTest(change=change), self.assertRaises(a.AdmissionError):
                a.validate_connections(value, RUN, SOURCE, FP, SERVER_PATH)

    def test_manifest_and_workflow_scope(self):
        self.assertEqual(len(ci.INPUTS), len(set(ci.INPUTS)))
        for name in ci.INPUTS:
            self.assertTrue((ci.ROOT / name).is_file(), name)
        self.assertIn('quality/browser/owned-cleanup.ts', ci.INPUTS)
        self.assertIn('quality/browser/owned-cleanup.test.ts', ci.INPUTS)
        workflow = (ci.ROOT / '.github/workflows/rg06d-e2e.yml').read_text()
        self.assertIn('RG06D_SERVICE_ID: ${{ job.services.postgres.id }}', workflow)
        self.assertIn("RG06D_REQUIRE_PG_PRELOAD_TEST: '1'", workflow)
        self.assertIn('quality/browser/ci-preload-checks.mjs', ci.INPUTS)
        self.assertIn('quality/browser/ci-preload-gate.test.mjs', ci.INPUTS)
        self.assertNotIn('job.services', workflow.split('    steps:')[0])
        self.assertNotIn('runner.environment', workflow.split('    steps:')[0])
        self.assertIn('test "$RUN_OUTCOME" = success', workflow)
        self.assertIn('test "$PUBLISH_OUTCOME" = success', workflow)
        self.assertIn('test "$UPLOAD_OUTCOME" = success', workflow)
        self.assertIn('  pull_request:\n  push:\n    branches: [main]\n  workflow_dispatch:', workflow)
        spec = (ci.ROOT / 'quality/browser/analyses.spec.ts').read_text()
        self.assertEqual(len(re.findall(r"^test\('", spec, re.M)), 3)
        self.assertLess(spec.index("receipt('ownership-preservation.json'"), spec.index('await fixtureOwner.removeOwned'))


class FakeConnection:
    def __init__(self, autocommit=False, observed=OBS):
        self.info = SimpleNamespace(transaction_status=0, host='127.0.0.1', port=49123)
        self.autocommit = autocommit; self.observed = observed; self.closed = False; self.calls = []
        self.query_error = None
    def transaction(self):
        connection = self
        class Transaction:
            def __enter__(self): connection.info.transaction_status = 2
            def __exit__(self, *args): connection.info.transaction_status = 0
        return Transaction()
    def execute(self, sql): self.calls.append(sql)
    def cursor(self):
        connection = self
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql):
                connection.calls.append(sql)
                if connection.query_error: raise connection.query_error
            def fetchone(self): return tuple(connection.observed.values()) if connection.observed else None
        return Cursor()
    def close(self): self.closed = True


class IdentityTests(unittest.TestCase):
    def test_host_bindings_are_exact_and_unambiguous(self):
        good = {'HostIp': '0.0.0.0', 'HostPort': '49123'}
        a.validate_bindings([good], '49123')
        a.validate_bindings([good, {'HostIp': '::', 'HostPort': '49123'}], '49123')
        for invalid in (None, [], [good, good], [{'HostPort': '49123'}],
                        [{'HostIp': '192.0.2.1', 'HostPort': '49123'}],
                        [{'HostIp': '', 'HostPort': '49123'}],
                        [{'HostIp': '::', 'HostPort': '49123'}],
                        [{'HostIp': '127.0.0.1', 'HostPort': '49123'}],
                        [{'HostIp': '0.0.0.0', 'HostPort': '9999'}],
                        [good, {'HostIp': '::', 'HostPort': ''}]):
            with self.subTest(binding=invalid), self.assertRaises(a.AdmissionError):
                a.validate_bindings(invalid, '49123')

    def test_cluster_equivalence_uses_independently_admitted_connection_paths(self):
        a.validate_identity(OBS, FP, SERVER_PATH)
        local_path = {'address': '127.0.0.1', 'port': 5432}
        a.validate_identity({**FP, **local_path, 'backend_pid': 999}, FP, local_path)
        for change in ({'system_id': '999'}, {'db': 'other'}, {'role': 'other'},
                       {'version': '170012'}, {'system_id': None}, {'address': '192.0.2.1'},
                       {'port': 5555}, {'backend_pid': 0}):
            with self.subTest(change=change), self.assertRaises(a.AdmissionError):
                a.validate_identity({**OBS, **change}, FP, SERVER_PATH)
        with self.assertRaises(a.AdmissionError):
            a.validate_identity({**FP, **local_path, 'backend_pid': 99}, FP, SERVER_PATH)
        for host, port in (('192.0.2.1', 49123), ('127.0.0.1', 5432)):
            with self.subTest(host=host, port=port), self.assertRaises(a.AdmissionError):
                a.validate_client_target(host, port, TARGET)

    def test_identity_query_failure_preserves_failure_and_closes_without_insert(self):
        connection = FakeConnection()
        failure = RuntimeError('synthetic permission denied')
        connection.query_error = failure
        with self.assertRaises(RuntimeError) as caught:
            a.guarded_connect(lambda: connection, FP, lambda _: None, SERVER_PATH, TARGET)()
        self.assertIs(caught.exception, failure)
        self.assertTrue(connection.closed)
        self.assertEqual(connection.info.transaction_status, 0)
        self.assertEqual(connection.calls[-1], a.IDENTITY_SQL)

    def test_real_guard_component_preserves_idle_autocommit_and_checks_every_connection(self):
        for autocommit in (False, True):
            emitted = []
            connection = FakeConnection(autocommit)
            guard = a.guarded_connect(lambda *args, **kwargs: connection, FP, emitted.append, SERVER_PATH, TARGET)
            self.assertIs(guard('synthetic'), connection)
            self.assertEqual(connection.info.transaction_status, 0)
            self.assertEqual(connection.autocommit, autocommit)
            self.assertEqual(emitted, [OBS])
            self.assertIn('SET TRANSACTION READ ONLY', connection.calls)
            self.assertFalse(connection.closed)

    def test_backend_mismatch_missing_identity_or_evidence_failure_prevents_insert(self):
        for observed in ({**OBS, 'system_id': '999'}, None, OBS):
            connection = FakeConnection(observed=observed)
            def emit(_): raise a.AdmissionError('DISK_FAILURE')
            guard = a.guarded_connect(lambda: connection, FP, emit, SERVER_PATH, TARGET)
            with self.subTest(observed=observed), self.assertRaises(a.AdmissionError):
                guard().execute('INSERT forbidden')
            self.assertTrue(connection.closed)
            self.assertNotIn('INSERT forbidden', connection.calls)

    def test_driver_error_propagates(self):
        failure = RuntimeError('synthetic connection error')
        def original(): raise failure
        with self.assertRaises(RuntimeError) as caught:
            a.guarded_connect(original, FP, lambda _: None, SERVER_PATH, TARGET)()
        self.assertIs(caught.exception, failure)

    def test_service_mismatch_before_schema(self):
        container = {'Id': 'e' * 64, 'Image': 'image', 'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                     'Mounts': [{'Type': 'volume', 'Destination': '/var/lib/postgresql/data'}],
                     'NetworkSettings': {'Networks': {'job': {'NetworkID': 'f' * 64, 'IPAddress': '172.18.0.2'}},
                                         'Ports': {'5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '49123'}]}}}
        image = {'Id': 'image', 'Os': 'linux', 'Architecture': 'amd64'}
        a.validate_service(container, image, 'e' * 64, 'f' * 64, '49123')
        for mutate in (lambda c: c.update(Id='9' * 64), lambda c: c.update(Image='wrong'),
                       lambda c: c['NetworkSettings']['Ports']['5432/tcp'][0].update(HostPort='9999'),
                       lambda c: c['NetworkSettings']['Networks']['job'].update(NetworkID='9' * 64),
                       lambda c: c['NetworkSettings']['Networks']['job'].update(IPAddress='127.0.0.1'),
                       lambda c: c['NetworkSettings']['Ports'].update({'9999/tcp': []})):
            value = copy.deepcopy(container); mutate(value)
            with self.assertRaises(a.AdmissionError):
                a.validate_service(value, image, 'e' * 64, 'f' * 64, '49123')


class ReporterBoundaryTests(unittest.TestCase):
    def assert_rejected(self, raw, exit_code=0):
        with self.assertRaises((a.AdmissionError, ValueError)):
            value = unit(); value['report'] = a.parse(raw); value['exit_code'] = exit_code
            a.validate_unit(value, RUN, SOURCE)

    def test_pass_looking_output_requires_successful_process_and_complete_json(self):
        self.assert_rejected(encoded(unit()['report']), 1)
        for raw in (b'', b'PASS', b'{"cases":', encoded({'cases': unit()['report']['cases']})):
            with self.subTest(raw=raw[:40]): self.assert_rejected(raw)

    def test_actual_reporter_rejects_incomplete_or_contradictory_event_streams(self):
        events = [{'type': 'test:pass', 'data': {'name': n, 'nesting': 0}} for n in a.UNIT_NAMES]
        summary = {'type': 'test:summary', 'data': {'counts': unit()['report']['summary']}}
        valid = events + [summary]
        streams = [events, events[:-1] + [summary], valid + [summary],
                   [events[0], events[0], *events[2:], summary]]
        for field, value in (('name', 'unexpected'), ('skip', True), ('todo', True)):
            changed = copy.deepcopy(valid); changed[0]['data'][field] = value; streams.append(changed)
        changed = copy.deepcopy(valid); changed[0]['type'] = 'test:fail'; streams.append(changed)
        cancelled = copy.deepcopy(valid)
        cancelled[0]['type'] = 'test:fail'
        cancelled[0]['data']['details'] = {'error': {'failureType': 'cancelledByParent'}}
        cancelled[-1]['data']['counts'].update(passed=3, cancelled=1)
        streams.append(cancelled)
        for key in ('tests', 'passed', 'failed', 'skipped', 'cancelled', 'todo'):
            changed = copy.deepcopy(valid); changed[-1]['data']['counts'][key] += 1; streams.append(changed)
        program = ('import reporter from ' + json.dumps((ci.PACKAGE / 'unit-reporter.mjs').as_uri()) + ';'
                   'async function* events(){yield* JSON.parse(process.argv[1]);}'
                   'for await (const chunk of reporter(events())) process.stdout.write(chunk);')
        for index, stream in enumerate([valid, *streams]):
            result = subprocess.run(['node', '--input-type=module', '-e', program, json.dumps(stream)],
                                    cwd=ci.ROOT, capture_output=True, timeout=10, check=False)
            with self.subTest(stream=index):
                if index == 0:
                    self.assertEqual(result.returncode, 0)
                    value = unit(); value['report'] = a.parse(result.stdout)
                    a.validate_unit(value, RUN, SOURCE)
                else:
                    self.assert_rejected(result.stdout, result.returncode)

    def test_real_node_failure_skip_todo_and_nonzero_exit(self):
        # Cancellation and truncated streams are controlled TestsStream fixtures
        # above; no intentionally hanging subprocess is needed to test refusal.
        for mode in ('fail', 'skip', 'todo', 'exit'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                lines = ["import {test} from 'node:test';"]
                for i, name in enumerate(a.UNIT_NAMES):
                    body = '() => {}'; options = '{}'
                    if i == 0:
                        if mode == 'fail': body = "() => {throw new Error('synthetic failure')}"
                        if mode == 'skip': options = '{skip:true}'
                        if mode == 'todo': options = '{todo:true}'
                    lines.append('test(' + json.dumps(name) + ',' + options + ',' + body + ');')
                if mode == 'exit': lines.append('process.exitCode=1;')
                fixture = Path(temp) / 'synthetic.test.mjs'; fixture.write_text('\n'.join(lines))
                result = subprocess.run(['node', '--test', '--test-reporter', (ci.PACKAGE / 'unit-reporter.mjs').as_uri(), str(fixture)],
                                        cwd=ci.ROOT, capture_output=True, timeout=10, check=False)
                # Prove the intended real TestsStream outcome was reached, rather
                # than accepting a fixture/import error as negative evidence.
                report = a.parse(result.stdout)
                key = {'fail': 'failed', 'skip': 'skipped', 'todo': 'todo'}.get(mode)
                if key: self.assertGreater(report['summary'][key], 0)
                if mode == 'exit': self.assertNotEqual(result.returncode, 0)
                self.assert_rejected(result.stdout, result.returncode)


class PreloadGateTests(unittest.TestCase):
    def test_positive_required_r03_outcome(self):
        a.validate_preload(preload(), RUN, SOURCE)

    def test_skipped_missing_duplicate_failed_cancelled_or_inconsistent_r03_is_rejected(self):
        mutations = [
            lambda p: p.update(exit_code=1),
            lambda p: p.update(pg_version='8.23.0'),
            lambda p: p.update(report=None),
            lambda p: p.update(run_id='b' * 32),
            lambda p: p['source_identity'].update(checkout_sha='f' * 40),
            lambda p: p['report']['cases'].clear(),
            lambda p: p['report']['cases'].append(copy.deepcopy(p['report']['cases'][0])),
            lambda p: p['report']['cases'][0].update(name='another identity test'),
            lambda p: p['report']['cases'][0].update(skip=True),
            lambda p: p['report']['cases'][0].update(passed=False),
            lambda p: p['report']['cases'][0].update(todo=True),
            lambda p: p['report']['summary'].update(cancelled=1),
            lambda p: p['report']['summary'].update(tests=2),
            lambda p: p['report'].pop('summary'),
        ]
        for index, mutate in enumerate(mutations):
            value = preload(); mutate(value)
            with self.subTest(case=index), self.assertRaises(a.AdmissionError):
                a.validate_preload(value, RUN, SOURCE)
        # The exact false green: process exit 0, but one skipped R03 result.
        skipped = preload(); skipped['report']['cases'][0].update(passed=True, skip=True)
        skipped['report']['summary'].update(passed=0, skipped=1)
        with self.assertRaises(a.AdmissionError): a.validate_preload(skipped, RUN, SOURCE)

    def test_truncated_missing_or_corrupt_report_is_not_accepted(self):
        for raw in (b'', b'PASS', b'{"cases":', b'{"report":{},"report":{}}'):
            with self.subTest(raw=raw), self.assertRaises(a.AdmissionError):
                a.parse(raw)
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', ENV):
            directory = Path(temp); bundle(directory); (directory / 'pg-preload.json').unlink()
            with self.assertRaises(FileNotFoundError): ci.validate_admission_bundle(directory, SOURCE, RUN)

    def test_harness_requires_explicit_mode_and_rejects_missing_or_wrong_package(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); package = directory / 'browser'; package.mkdir()
            with patch.object(ci, 'PACKAGE', package), patch.dict('os.environ', {'RG06D_REQUIRE_PG_PRELOAD_TEST': '0'}):
                with self.assertRaises(ci.Stop): ci.preload_gate(directory, SOURCE)
            with patch.object(ci, 'PACKAGE', package), patch.dict('os.environ', {'RG06D_REQUIRE_PG_PRELOAD_TEST': '1'}):
                with self.assertRaises(ci.Stop): ci.preload_gate(directory, SOURCE)
                meta = package / 'node_modules/pg/package.json'; meta.parent.mkdir(parents=True)
                meta.write_text('{"version":"8.23.0"}')
                with self.assertRaises(ci.Stop): ci.preload_gate(directory, SOURCE)

    def test_actual_harness_boundary_rejects_zero_exit_with_skipped_or_missing_r03(self):
        skipped = preload()['report']
        skipped['cases'][0]['skip'] = True
        skipped['summary'].update(passed=0, skipped=1)
        missing = preload()['report']; missing['cases'] = []
        for report in (skipped, missing):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); directory = root / RUN; directory.mkdir()
                package = root / 'browser'; meta = package / 'node_modules/pg/package.json'
                meta.parent.mkdir(parents=True); meta.write_text('{"version":"8.23.1"}')
                result = SimpleNamespace(returncode=0, stdout=encoded(report))
                with patch.object(ci, 'PACKAGE', package), patch.object(ci.subprocess, 'run', return_value=result) as command, \
                     patch.dict('os.environ', {'RG06D_REQUIRE_PG_PRELOAD_TEST': '1'}):
                    with self.assertRaises(a.AdmissionError): ci.preload_gate(directory, SOURCE)
                    self.assertEqual(command.call_args.kwargs['env']['RG06D_REQUIRE_PG_PRELOAD_TEST'], '1')
                    self.assertEqual(command.call_args.args[0][-1], 'quality/browser/ci-preload.integration.test.mjs')


class MergeCheckoutTests(unittest.TestCase):
    """Real Git objects and source_identity; all writes stay in an external temp repo."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='rg06d-source-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.git_env = {**os.environ, 'GIT_AUTHOR_NAME': 'Synthetic QA',
                       'GIT_AUTHOR_EMAIL': 'qa@example.invalid', 'GIT_COMMITTER_NAME': 'Synthetic QA',
                       'GIT_COMMITTER_EMAIL': 'qa@example.invalid',
                       'GIT_AUTHOR_DATE': '2026-11-05T12:00:00+00:00',
                       'GIT_COMMITTER_DATE': '2026-11-05T12:00:00+00:00'}
        cls.git('init', '--quiet')
        cls.tree = cls.git('mktree', data=b'')
        cls.base = cls.commit('base')
        cls.head = cls.commit('feature', cls.base)
        cls.extra = cls.commit('other', cls.base)
        cls.merge = cls.commit('tested merge', cls.base, cls.head)
        (cls.root / 'uv.lock').write_bytes(b'synthetic python lock\n')
        (cls.root / 'node.lock').write_bytes(b'synthetic node lock\n')

    @classmethod
    def git(cls, *args, data=None):
        return subprocess.check_output(['git', *args], cwd=cls.root, env=cls.git_env,
                                       input=data, stderr=subprocess.DEVNULL).decode().strip()

    @classmethod
    def commit(cls, message, *parents):
        args = ['commit-tree', cls.tree]
        for parent in parents:
            args.extend(('-p', parent))
        return cls.git(*args, data=message.encode())

    def setUp(self):
        self.git('update-ref', 'HEAD', self.merge)
        repo = {'id': 123, 'name': 'reqguard-quality-platform', 'full_name': a.OFFICIAL_REPOSITORY,
                'owner': {'login': 'Yeromenko-Kateryna', 'id': 456}, 'fork': False}
        self.event = {'number': 3, 'repository': copy.deepcopy(repo), 'pull_request': {
            'number': 3, 'merge_commit_sha': self.merge,
            'base': {'sha': self.base, 'ref': 'main', 'label': 'Yeromenko-Kateryna:main',
                     'repo': copy.deepcopy(repo)},
            'head': {'sha': self.head, 'ref': 'codex/source-test',
                     'label': 'Yeromenko-Kateryna:codex/source-test', 'repo': copy.deepcopy(repo)}}}
        self.env = {'GITHUB_SHA': self.merge, 'GITHUB_EVENT_NAME': 'pull_request',
                    'GITHUB_EVENT_PATH': str(self.root / 'event.json'), 'GITHUB_REF': 'refs/pull/3/merge',
                    'GITHUB_REPOSITORY': a.OFFICIAL_REPOSITORY, 'GITHUB_REPOSITORY_ID': '123',
                    'GITHUB_REPOSITORY_OWNER': 'Yeromenko-Kateryna', 'GITHUB_REPOSITORY_OWNER_ID': '456',
                    'GITHUB_BASE_REF': 'main', 'GITHUB_HEAD_REF': 'codex/source-test',
                    'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        (self.root / 'uv.lock').write_bytes(b'synthetic python lock\n')
        self.enterContext(patch.object(ci, 'ROOT', self.root))
        # Keep the evidence lock-field contract while using small synthetic inputs.
        (self.root / 'quality/browser').mkdir(parents=True, exist_ok=True)
        (self.root / 'quality/browser/package-lock.json').write_bytes(b'synthetic node lock\n')
        self.enterContext(patch.object(ci, 'INPUTS', ['uv.lock', 'quality/browser/package-lock.json']))
        self.enterContext(patch.dict('os.environ', self.env))

    def identity(self):
        (self.root / 'event.json').write_bytes(encoded(self.event))
        return ci.source_identity()

    def reject(self, code):
        with self.assertRaisesRegex((a.AdmissionError, ci.Stop), '^' + code + '$'):
            self.identity()

    def checkout(self, oid):
        self.git('update-ref', 'HEAD', oid)
        os.environ['GITHUB_SHA'] = oid

    def test_valid_merge_real_source_identity(self):
        value = self.identity()
        self.assertEqual(set(value), set(a.SOURCE_KEYS))
        self.assertEqual((value['checkout_sha'], value['tested_merge_sha']), (self.merge, self.merge))
        self.assertEqual((value['pr_base_sha'], value['pr_head_sha']), (self.base, self.head))
        a.validate_source(value, value)

    def test_stale_event_merge_sha_passes(self):
        self.event['pull_request']['merge_commit_sha'] = self.extra
        self.assertEqual(self.identity()['checkout_sha'], self.merge)

    def test_missing_event_merge_sha_passes(self):
        del self.event['pull_request']['merge_commit_sha']
        self.assertEqual(self.identity()['checkout_sha'], self.merge)

    def test_head_sha_mismatch(self):
        with patch.dict('os.environ', {'GITHUB_SHA': self.head}): self.reject('CHECKOUT_EVENT_SHA')

    def test_wrong_merge_ref(self):
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/pull/3/head'}): self.reject('SOURCE_PR_REF')

    def test_wrong_pr_number(self):
        for value in (True, 0, -1, '3', 4):
            with self.subTest(number=value):
                self.event['pull_request']['number'] = value
                self.reject('SOURCE_PR_NUMBER')

    def test_non_pr_event_cannot_use_pr_path(self):
        for kind in ('push', 'workflow_dispatch', 'pull_request_target', 'unknown'):
            with self.subTest(event=kind), patch.dict('os.environ', {'GITHUB_EVENT_NAME': kind}):
                self.reject('SOURCE_NON_PR_CONTEXT' if kind in ('push', 'workflow_dispatch') else 'SOURCE_EVENT_KIND')

    def test_missing_required_event_fields(self):
        original = copy.deepcopy(self.event)
        for path, code in ((('repository',), 'SOURCE_REPOSITORY_FIELDS'),
                           (('pull_request',), 'SOURCE_PR_FIELDS'),
                           (('number',), 'SOURCE_PR_NUMBER'),
                           (('pull_request', 'head'), 'SOURCE_PR_FIELDS'),
                           (('pull_request', 'head', 'sha'), 'SOURCE_COMMIT_OID'),
                           (('pull_request', 'base', 'repo'), 'SOURCE_REPOSITORY_FIELDS'),
                           (('pull_request', 'head', 'label'), 'SOURCE_PR_BRANCH_CONTEXT')):
            self.event = copy.deepcopy(original)
            target = self.event
            for part in path[:-1]: target = target[part]
            del target[path[-1]]
            with self.subTest(path=path): self.reject(code)

    def test_missing_required_execution_fields(self):
        for key, code in (('GITHUB_SHA', 'SOURCE_COMMIT_OID'),
                          ('GITHUB_REPOSITORY_ID', 'SOURCE_REPOSITORY_CONTEXT'),
                          ('GITHUB_REPOSITORY_OWNER_ID', 'SOURCE_REPOSITORY_CONTEXT'),
                          ('GITHUB_REF', 'SOURCE_PR_REF'),
                          ('GITHUB_HEAD_REF', 'SOURCE_PR_BRANCH_CONTEXT'),
                          ('GITHUB_BASE_REF', 'SOURCE_PR_BRANCH_CONTEXT')):
            env = dict(os.environ); del env[key]
            with self.subTest(key=key), patch.dict('os.environ', env, clear=True): self.reject(code)

    def test_malformed_sha_and_json(self):
        for sha in ('abc', 'F' * 40, '../HEAD', 123, None):
            self.event['pull_request']['head']['sha'] = sha
            with self.subTest(sha=sha): self.reject('SOURCE_COMMIT_OID')
        for raw, code in ((b'{', 'ADMISSION_JSON'), (b'[]', 'SOURCE_EVENT_OBJECT'),
                          (b'{"number":1,"number":2}', 'ADMISSION_DUPLICATE_KEY')):
            (self.root / 'event.json').write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(a.AdmissionError, '^' + code + '$'):
                ci.source_identity()

    def test_missing_event_file(self):
        with patch.dict('os.environ', {'GITHUB_EVENT_PATH': str(self.root / 'missing.json')}):
            self.reject('SOURCE_EVENT_FILE')

    def test_one_parent_merge_rejected(self):
        self.checkout(self.head)
        self.reject('SOURCE_MERGE_PARENT_COUNT')

    def test_zero_parent_merge_rejected(self):
        self.checkout(self.base)
        self.reject('SOURCE_MERGE_PARENT_COUNT')

    def test_more_than_two_parents_rejected(self):
        self.checkout(self.commit('octopus', self.base, self.head, self.extra))
        self.reject('SOURCE_MERGE_PARENT_COUNT')

    def test_reversed_parent_order_rejected(self):
        self.checkout(self.commit('reversed', self.head, self.base))
        self.reject('SOURCE_MERGE_PARENT_ORDER')

    def test_base_parent_mismatch(self):
        self.event['pull_request']['base']['sha'] = self.extra
        self.reject('SOURCE_MERGE_PARENT_ORDER')

    def test_head_parent_mismatch(self):
        self.event['pull_request']['head']['sha'] = self.extra
        self.reject('SOURCE_MERGE_PARENT_ORDER')

    def test_unexpected_base_repository(self):
        self.event['pull_request']['base']['repo']['id'] = 789
        self.reject('SOURCE_PR_BASE_REPOSITORY')

    def test_wrong_execution_repository(self):
        for key, value in (('GITHUB_REPOSITORY', 'attacker/other'), ('GITHUB_REPOSITORY_ID', '789'),
                           ('GITHUB_REPOSITORY_OWNER_ID', '789')):
            with self.subTest(key=key), patch.dict('os.environ', {key: value}):
                self.reject('SOURCE_REPOSITORY_CONTEXT')

    def test_contradictory_head_repository(self):
        original = copy.deepcopy(self.event)
        for change, code in (({'id': 789}, 'SOURCE_PR_HEAD_REPOSITORY'),
                             ({'full_name': 'attacker/other'}, 'SOURCE_REPOSITORY_IDENTITY'),
                             ({'owner': {'login': 'Yeromenko-Kateryna', 'id': 789}}, 'SOURCE_PR_HEAD_OWNER')):
            self.event = copy.deepcopy(original)
            self.event['pull_request']['head']['repo'].update(change)
            with self.subTest(change=change): self.reject(code)

    def test_head_ref_label_and_user_cross_checks(self):
        for value in ('attacker:codex/source-test', 'Yeromenko-Kateryna:other'):
            self.event['pull_request']['head']['label'] = value
            with self.subTest(label=value): self.reject('SOURCE_PR_BRANCH_CONTEXT')
        self.event['pull_request']['head']['label'] = 'Yeromenko-Kateryna:codex/source-test'
        self.event['pull_request']['head']['user'] = {'login': 'other', 'id': 789}
        self.reject('SOURCE_PR_HEAD_USER')

    def test_existing_fork_trigger_policy_requires_consistent_identity(self):
        head = self.event['pull_request']['head']
        head['repo'] = {'id': 789, 'name': 'fork', 'full_name': 'SyntheticOwner/fork',
                        'owner': {'login': 'SyntheticOwner', 'id': 987}, 'fork': True}
        head['label'] = 'SyntheticOwner:codex/source-test'
        self.assertEqual(self.identity()['pr_head_sha'], self.head)
        head['repo']['fork'] = False
        self.reject('SOURCE_PR_HEAD_FORK')

    def test_unavailable_parent_object(self):
        missing = 'd' * 40
        raw = (f'tree {self.tree}\nparent {self.base}\nparent {missing}\n'
               'author Synthetic QA <qa@example.invalid> 1793880000 +0000\n'
               'committer Synthetic QA <qa@example.invalid> 1793880000 +0000\n\nmissing parent\n').encode()
        self.checkout(self.git('hash-object', '-t', 'commit', '-w', '--stdin', data=raw))
        self.event['pull_request']['head']['sha'] = missing
        self.reject('SOURCE_GIT_COMMAND')

    def test_non_commit_head_object(self):
        blob = self.git('hash-object', '-w', '--stdin', data=b'not a commit')
        real_git = ci.source_git
        def git_boundary(*args):
            return blob if args == ('rev-parse', '--verify', 'HEAD') else real_git(*args)
        with patch.object(ci, 'source_git', side_effect=git_boundary), patch.dict('os.environ', {'GITHUB_SHA': blob}):
            self.reject('SOURCE_HEAD_OBJECT_TYPE')

    def test_non_commit_parent_object(self):
        blob = self.git('hash-object', '-w', '--stdin', data=b'not a parent commit')
        raw = (f'tree {self.tree}\nparent {self.base}\nparent {blob}\n'
               'author Synthetic QA <qa@example.invalid> 1793880000 +0000\n'
               'committer Synthetic QA <qa@example.invalid> 1793880000 +0000\n\nbad parent type\n').encode()
        self.checkout(self.git('hash-object', '-t', 'commit', '-w', '--stdin', data=raw))
        self.event['pull_request']['head']['sha'] = blob
        self.reject('SOURCE_PARENT_OBJECT_TYPE')

    def test_git_command_nonzero_fails_closed(self):
        with patch.object(ci.subprocess, 'check_output', side_effect=subprocess.CalledProcessError(128, 'git')):
            self.reject('SOURCE_GIT_COMMAND')

    def test_source_hash_changed_rejects_existing_launch(self):
        source = self.identity()
        launch = {'source_identity': source, 'head': self.merge, 'inputs': source['inputs'],
                  'githubRun': '123', 'githubAttempt': '1'}
        ci.validate_launch(launch)
        (self.root / 'uv.lock').write_bytes(b'changed without updating expected hash')
        with self.assertRaisesRegex(a.AdmissionError, '^SOURCE_MISMATCH$'):
            ci.validate_launch(launch)

    def test_unchanged_receipt_schema_and_corrupt_source_rejection(self):
        source = self.identity()
        value = unit(); value['source_identity'] = source
        a.validate_unit(value, RUN, source)
        value['source_identity'] = {**source, 'github_run_attempt': '2'}
        with self.assertRaisesRegex(a.AdmissionError, '^SOURCE_MISMATCH$'):
            a.validate_unit(value, RUN, source)

    def test_publication_cannot_accept_failed_source_admission(self):
        source = self.identity()
        raw = self.root / 'raw'; raw.mkdir(exist_ok=True)
        (raw / 'launch.json').write_bytes(encoded({'source_identity': source}))
        temp = self.root / 'publisher'; temp.mkdir(exist_ok=True)
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/pull/4/merge', 'RUNNER_TEMP': str(temp),
                                      'RG06D_RUN_OUTCOME': 'success'}), patch.object(ci, 'artifact', return_value=raw):
            with self.assertRaisesRegex(ci.Stop, '^EVIDENCE_PUBLICATION_INCOMPLETE$'):
                ci.publish()
        published = a.parse((temp / 'rg06d-safe-123-1/publication-manifest.json').read_bytes())
        self.assertIn('RAW_EVIDENCE_UNAVAILABLE', published['rejected'])
        self.assertEqual(published['copied'], [])

    def test_existing_push_and_dispatch_paths_are_explicit(self):
        self.event = {'repository': self.event['repository'], 'ref': 'refs/heads/main',
                      'after': self.merge, 'deleted': False}
        context = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
                   'GITHUB_HEAD_REF': '', 'GITHUB_BASE_REF': ''}
        with patch.dict('os.environ', context):
            self.assertIsNone(self.identity()['tested_merge_sha'])
        self.event['ref'] = 'main'
        with patch.dict('os.environ', {**context, 'GITHUB_EVENT_NAME': 'workflow_dispatch'}):
            self.assertIsNone(self.identity()['pr_head_sha'])
            self.event['ref'] = 'other'
            self.reject('SOURCE_DISPATCH_CONTEXT')

    def test_real_depth_two_checkout_contains_parent_objects(self):
        clone = self.root / 'depth-two'
        result = subprocess.run(['git', 'clone', '--quiet', '--depth=2', '--no-checkout',
                                 self.root.as_uri(), str(clone)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'],
                                                cwd=clone).decode().strip(), 'true')
        for name in ci.INPUTS:
            target = clone / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.root / name).read_bytes())
        with patch.object(ci, 'ROOT', clone):
            self.assertEqual(self.identity()['checkout_sha'], self.merge)


if __name__ == '__main__':
    unittest.main()
