"""RG-06D only: Linux hosted CI, existing RG-06B specs, safe publication.

prepare/publish use only stdlib, including after dependency setup fails.
No Docker commands: GitHub owns service disposal, which this file cannot attest.
"""

import ctypes
import hashlib
import importlib.metadata
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


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'quality/browser'
IMAGE = 'postgres:17.11-bookworm@sha256:ec4dfc6571f04fe0731ce948c1500d676af49a7224392dcc6995cc1ee33a94bb'
PASSWORD = '0123456789abcdef' * 4  # Public synthetic service credential, not a secret.
INPUTS = ['pyproject.toml', 'uv.lock', 'db/001_init.sql', 'reqguard/main.py',
          'reqguard/persistence.py', 'reqguard/static/index.html', 'reqguard/static/app.mjs',
          'reqguard/static/style.css', 'quality/browser/package.json',
          'quality/browser/package-lock.json', 'quality/browser/analyses.spec.ts',
          'quality/browser/playwright.config.ts', 'quality/browser/playwright.ci.config.ts',
          'scripts/run_rg06d_ci.py', '.github/workflows/rg06d-e2e.yml']
JSON_ALLOWLIST = ['launch.json', 'postgres-ready.json', 'baseline.json', 'sentinel-plan.json',
                  'supported-response-id.json', 'supported-sql.json', 'invalid-sql.json',
                  'supported-cleanup.json', 'sql-cleanup.json', 'results.json',
                  'server-process.json', 'playwright-process.json', 'run-summary.json']
LOG_ALLOWLIST = ['uvicorn.stdout', 'uvicorn.stderr', 'playwright.stdout', 'playwright.stderr']


class Stop(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Stop(code)


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(argv):
    return subprocess.check_output(argv, cwd=ROOT, stderr=subprocess.DEVNULL,
                                   text=True, timeout=15).strip()


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
        launch = json.loads((path / 'launch.json').read_text())
        require(all(digest(ROOT / n) == h for n, h in launch['inputs'].items()), 'SOURCE_OR_LOCK_CHANGED')
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
        import psycopg
        # One bounded, independent connection. No fallback to an existing DB.
        with psycopg.connect(dsn, connect_timeout=5, options='-c statement_timeout=5000') as connection:
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
        server = subprocess.Popen([sys.executable, '-B', '-m', 'uvicorn', 'reqguard.main:app',
                                   '--host', '127.0.0.1', '--port', str(api_port), '--workers', '1'],
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
        require(report['stats']['expected'] == 2 and not report['errors']
                and all(report['stats'][k] == 0 for k in ('unexpected', 'skipped', 'flaky'))
                and len(specs) == 2 and all(s['ok'] and len(s['tests']) == 1
                and s['tests'][0]['projectName'] == 'chromium' and s['tests'][0]['status'] == 'expected'
                and len(s['tests'][0]['results']) == 1 and s['tests'][0]['results'][0]['status'] == 'passed'
                and s['tests'][0]['results'][0]['retry'] == 0 for s in specs), 'EXACT_TWO_RESULTS')
        require(json.loads((path / 'sql-cleanup.json').read_text()) == {
            'state': 'CLEANED', 'supportedCleaned': True, 'invalidVerified': True, 'uncertain': False}, 'SQL_CLEANUP')
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
        for name in JSON_ALLOWLIST + LOG_ALLOWLIST:
            source = raw / name
            if not source.exists():
                continue
            try:
                require(source.is_file() and not source.is_symlink() and source.stat().st_size <= 10_000_000,
                        'UNSAFE_ARTIFACT_FILE')
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
                (safe / name).write_text(text, encoding='utf-8')
                publication['copied'].append(name)
            except (OSError, ValueError, Stop):
                publication['rejected'].append(name)
    except (KeyError, OSError, Stop):
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
