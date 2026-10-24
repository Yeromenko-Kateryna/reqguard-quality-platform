"""RG-06B only: fresh Docker project, two browser tests, owned cleanup.

Windows x64 / CPython 3.12. This file has no import-time provisioning.
Failure preserves Docker resources and private artifacts; it never retries.
"""

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import uuid


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'quality' / 'browser'
IMAGE = 'postgres:17.11-bookworm'
LABEL = 'com.docker.compose.project'
BOOTSTRAP = """import ctypes, json, os, subprocess, sys, time
exit_process = ctypes.WinDLL('kernel32', use_last_error=True).ExitProcess
exit_process.argtypes = [ctypes.c_uint32]
exit_process.restype = None
def publish(value):
    with open(sys.argv[3], 'x', encoding='utf-8', newline='\\n') as stream:
        json.dump(value, stream)
        stream.write('\\n')
        stream.flush()
        os.fsync(stream.fileno())
target = None
exit_code = 126
try:
    deadline = time.monotonic() + 30
    while not os.path.isfile(sys.argv[1]):
        if time.monotonic() > deadline: exit_process(125)
        time.sleep(0.02)
    argv = json.loads(sys.argv[2])
    # No shell, detach or breakaway. Descendants inherit this bootstrap's job.
    target = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    code = target.wait()
    if type(code) is not int or not 0 <= code <= 0xffffffff:
        raise RuntimeError('RG06B_TARGET_EXIT_UNKNOWN')
    publish({'launchId': sys.argv[4], 'state': 'EXIT_CONFIRMED',
             'targetPid': target.pid, 'exit': code})
    exit_code = code
except BaseException:
    try:
        publish({'launchId': sys.argv[4],
                 'state': 'START_FAILED' if target is None else 'UNKNOWN',
                 'targetPid': None if target is None else target.pid, 'exit': None})
    except BaseException:
        pass
    sys.stderr.write('RG06B_BOOTSTRAP_FAILURE\\n')
    sys.stderr.flush()
# Avoid sys.exit's signed C-int conversion: preserve every Windows DWORD value.
exit_process(exit_code)
"""


class Stop(Exception):
    """Only fixed, non-sensitive codes are printed to the console."""


def require(condition, code):
    if not condition:
        raise Stop(code)


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Job:
    """One Windows Job Object per command, including all descendants.

    A stdlib-only gated bootstrap prevents the target from starting until
    assignment succeeds. Disposal alone is never evidence of termination.
    """

    def __init__(self):
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in
                        ('readOps', 'writeOps', 'otherOps', 'readBytes', 'writeBytes', 'otherBytes')]

        class Basic(ctypes.Structure):
            _fields_ = [('processTime', ctypes.c_longlong), ('jobTime', ctypes.c_longlong),
                        ('flags', wintypes.DWORD), ('minWS', ctypes.c_size_t),
                        ('maxWS', ctypes.c_size_t), ('activeLimit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('processMemory', ctypes.c_size_t),
                        ('jobMemory', ctypes.c_size_t), ('peakProcess', ctypes.c_size_t),
                        ('peakJob', ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [(n, ctypes.c_longlong) for n in ('user', 'kernel', 'periodUser', 'periodKernel')] + [
                (n, wintypes.DWORD) for n in ('faults', 'total', 'active', 'terminated')]

        self.accounting = Accounting
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in [
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('GetProcessTimes', [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                                ctypes.POINTER(wintypes.FILETIME)], wintypes.BOOL),
            ('QueryInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            ('TerminateJobObject', [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ]:
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        require(ctypes.sizeof(Extended) == 144 and ctypes.sizeof(Accounting) == 48, 'JOB_LAYOUT')
        self.handle = self.api.CreateJobObjectW(None, None)
        require(bool(self.handle), 'JOB_CREATE')
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.api.CloseHandle(self.handle)
            raise Stop('JOB_CONFIGURE')

    def assign(self, process):
        require(self.api.AssignProcessToJobObject(self.handle, int(process._handle)), 'JOB_ASSIGN')

    def creation_time(self, process):
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        require(self.api.GetProcessTimes(int(process._handle), ctypes.byref(created),
                ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)), 'PROCESS_IDENTITY_UNKNOWN')
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)

    def empty(self):
        info = self.accounting()
        require(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None), 'JOB_QUERY')
        return info.active == 0

    def wait_empty(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.empty():
                return True
            time.sleep(0.05)
        return self.empty()

    def terminate(self):
        require(self.api.TerminateJobObject(self.handle, 124), 'JOB_TERMINATION_UNKNOWN')

    def close(self):
        require(self.api.CloseHandle(self.handle), 'JOB_CLOSE_UNKNOWN')


class Commands:
    def __init__(self, artifact, env):
        self.artifact, self.env, self.index = artifact, env, 0

    def run(self, label, argv, timeout=30):
        self.index += 1
        prefix = f'{self.index:03d}-{label}'
        gate = self.artifact / (prefix + '.ready')
        launch_id = uuid.uuid4().hex
        target_result = self.artifact / (prefix + '-target-exit.json')
        receipt = {'label': label, 'launchId': launch_id, 'state': 'ATTEMPTED',
                   'processState': 'ATTEMPTED', 'exit': None, 'bootstrapExit': None,
                   'targetState': 'NOT_RELEASED', 'gateReleased': False,
                   'treeExited': False, 'forced': False}
        # Never record argv/env: a DSN or Docker inspection can contain credentials.
        write_new(self.artifact / (prefix + '-launch.json'), receipt)
        job, process, assigned = Job(), None, False
        out, err = b'', b''
        problem = None
        try:
            process = subprocess.Popen(
                [sys._base_executable, '-I', '-S', '-c', BOOTSTRAP, str(gate), json.dumps(argv),
                 str(target_result), launch_id],
                cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            receipt.update(state='STARTED', processState='STARTED', bootstrapPid=process.pid)
            job.assign(process)
            assigned = True
            receipt['bootstrapCreatedFiletime'] = job.creation_time(process)
            # Exclusive publication, flush, fsync and close all precede gate release.
            # If any publication step fails, the target is never released.
            write_new(self.artifact / (prefix + '-started.json'), receipt)
            gate.touch(exist_ok=False)
            receipt.update(gateReleased=True, targetState='UNKNOWN')
            out, err = process.communicate(timeout=timeout)
            receipt['bootstrapExit'] = process.returncode
            require(job.wait_empty(), 'DESCENDANT_STILL_RUNNING')
            receipt.update(treeExited=True, state='EXIT_CONFIRMED', processState='EXIT_CONFIRMED')
            target = json.loads(target_result.read_text(encoding='utf-8'))
            require(target.get('launchId') == launch_id, 'TARGET_RECEIPT_IDENTITY')
            require(target.get('state') in ('EXIT_CONFIRMED', 'START_FAILED', 'UNKNOWN'), 'TARGET_RECEIPT_STATE')
            receipt['targetState'] = target['state']
            require(target['state'] == 'EXIT_CONFIRMED', 'TARGET_EXIT_UNCONFIRMED')
            require(type(target.get('targetPid')) is int and target['targetPid'] > 0, 'TARGET_PID_UNKNOWN')
            require(type(target.get('exit')) is int and 0 <= target['exit'] <= 0xffffffff, 'TARGET_EXIT_UNKNOWN')
            receipt.update(exit=target['exit'], targetPid=target['targetPid'])
            require(receipt['bootstrapExit'] == receipt['exit'], 'TARGET_EXIT_PROPAGATION')
        except BaseException as error:
            problem = error
            if process is not None and not receipt['treeExited']:
                receipt['forced'] = True
                try:
                    if assigned:
                        job.terminate()
                    else:
                        # Target was never released; only this exact bootstrap is stopped.
                        process.kill()
                    out, err = process.communicate(timeout=5)
                    receipt['bootstrapExit'] = process.returncode
                    require(process.returncode is not None and job.wait_empty(), 'PROCESS_EXIT_UNCONFIRMED')
                    receipt.update(treeExited=True, state='FORCED_STOP_CONFIRMED', processState='EXIT_CONFIRMED')
                except BaseException:
                    receipt.update(treeExited=False, state='PROCESS_STATE_UNKNOWN', processState='UNKNOWN')
            elif process is None:
                receipt['state'] = 'START_FAILED'
        finally:
            try:
                job.close()
            except BaseException as error:
                problem = error
                receipt.update(state='PROCESS_STATE_UNKNOWN', processState='UNKNOWN')
            # These private byte streams can include paths; never print them.
            for suffix, content in [('stdout', out), ('stderr', err)]:
                file = self.artifact / (prefix + '.' + suffix)
                with file.open('xb') as stream:
                    stream.write(content)
                receipt[suffix] = {'file': file.name, 'bytes': len(content), 'sha256': digest(file)}
            write_new(self.artifact / (prefix + '-exit.json'), receipt)
        if problem is not None:
            raise Stop('COMMAND_OR_PROCESS_UNCERTAIN') from None
        require(receipt['treeExited'] and receipt['exit'] == 0, 'COMMAND_FAILED')
        return out.decode('utf-8', errors='strict')


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    require(os.name == 'nt' and ctypes.sizeof(ctypes.c_void_p) == 8 and
            sys.version_info[:2] == (3, 12) and sys.implementation.name == 'cpython', 'WINDOWS_X64_PYTHON312_REQUIRED')
    require(not any(k.startswith('NODE_') or k.startswith('PW_TEST_') or
                    (k.startswith('PLAYWRIGHT_') and k != 'PLAYWRIGHT_BROWSERS_PATH')
                    for k in os.environ), 'AMBIENT_NODE_CONFIGURATION')
    require(not any(os.environ.get(k) for k in ('DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')), 'DOCKER_OVERRIDE')
    require(not any(os.environ.get(k) for k in ('PYTHONPATH', 'PYTHONHOME', 'UV_PROJECT', 'UV_WORKING_DIRECTORY')), 'PYTHON_PROJECT_OVERRIDE')
    tools = {name: shutil.which(name + '.exe') for name in ('docker', 'node', 'uv', 'git')}
    require(all(tools.values()), 'TOOLS_UNAVAILABLE')
    run = uuid.uuid4().hex
    project = 'rg06b_' + run
    artifact = PACKAGE / '.artifacts' / run
    artifact.parent.mkdir(exist_ok=True)
    artifact.mkdir(exist_ok=False)
    temporary = artifact / 'temp'
    temporary.mkdir(exist_ok=False)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('COMPOSE_') and not k.startswith('PG')}
    # Only child environment changes; no shell/session/global mutations.
    env.update(UV_OFFLINE='1', UV_NO_SYNC='1', UV_PYTHON_DOWNLOADS='never',
               PYTHONDONTWRITEBYTECODE='1', NO_COLOR='1', TEMP=str(temporary), TMP=str(temporary))
    api_port, db_port = available_port(), available_port()
    require(api_port != db_port, 'PORT_COLLISION')
    password = secrets.token_hex(32)
    env.update(RG06B_RUN_ID=run, RG06B_ARTIFACT=str(artifact), RG06B_DB_PORT=str(db_port),
               RG06B_API_PORT=str(api_port), RG06B_PASSWORD=password,
               RG06B_BASE_URL=f'http://127.0.0.1:{api_port}',
               DATABASE_URL=f'postgresql://reqguard_rg06b:{password}@127.0.0.1:{db_port}/reqguard_rg06b')
    commands = Commands(artifact, env)
    final = {'run': run, 'project': project, 'state': 'PREFLIGHT', 'e2e': 'NOT_RUN', 'docker': 'NOT_CREATED'}
    try:
        node = tools['node']
        require(commands.run('node-version', [node, '--version']).strip() == 'v24.15.0', 'NODE_VERSION')
        npm = Path(node).parent / 'node_modules/npm/bin/npm-cli.js'
        require(npm.is_file(), 'NPM_UNAVAILABLE')
        require(commands.run('npm-version', [node, str(npm), '--version']).strip() == '11.12.1', 'NPM_VERSION')
        for package, version in [('@playwright/test', '1.64.0'), ('playwright', '1.64.0'), ('pg', '8.23.1')]:
            meta = PACKAGE / 'node_modules' / package / 'package.json'
            require(meta.is_file() and json.loads(meta.read_text(encoding='utf-8'))['version'] == version, 'PACKAGE_NOT_INSTALLED_OR_MISMATCH')
        cli = PACKAGE / 'node_modules/playwright/cli.js'
        browser = commands.run('chromium-path', [node, '--input-type=module', '-e',
            'import {chromium} from ' + json.dumps((PACKAGE / 'node_modules/playwright/index.mjs').as_uri()) + '; console.log(chromium.executablePath())']).strip()
        require(Path(browser).is_file(), 'CHROMIUM_NOT_INSTALLED')
        runtime_names = ['fastapi', 'psycopg', 'psycopg-binary', 'uvicorn', 'pydantic', 'starlette']
        python_runtime = json.loads(commands.run('python-version', [tools['uv'], 'run', '--locked', '--no-sync', 'python', '-c',
            'import sys,json,importlib.metadata as m; assert sys.version_info[:2] == (3,12); '
            'print(json.dumps({"python":sys.version,"packages":{n:m.version(n) for n in ' + repr(runtime_names) + '}}))']))
        locked_python = {p['name']: p['version'] for p in tomllib.loads((ROOT / 'uv.lock').read_text(encoding='utf-8'))['package']}
        require(all(python_runtime['packages'][name] == locked_python[name] for name in runtime_names), 'PYTHON_LOCK_MISMATCH')
        head = commands.run('git-head', [tools['git'], 'rev-parse', 'HEAD']).strip()
        inputs = ['uv.lock', 'pyproject.toml', 'db/001_init.sql', 'reqguard/main.py', 'reqguard/persistence.py',
                  'reqguard/static/index.html', 'reqguard/static/app.mjs', 'reqguard/static/style.css',
                  'quality/browser/package.json', 'quality/browser/package-lock.json',
                  'quality/browser/playwright.config.ts', 'quality/browser/analyses.spec.ts',
                  'quality/browser/compose.rg06b.yaml', 'scripts/run_rg06b_e2e.py']
        write_new(artifact / 'launch.json', {'run': run, 'head': head, 'python': python_runtime,
            'node': '24.15.0', 'npm': '11.12.1', 'playwright': '1.64.0', 'pg': '8.23.1',
            'chromiumSha256': digest(Path(browser)),
            'browserCatalog': json.loads((PACKAGE / 'node_modules/playwright-core/browsers.json').read_text(encoding='utf-8')),
            'inputs': {p: digest(ROOT / p) for p in inputs}})
        context = commands.run('docker-context', [tools['docker'], 'context', 'show']).strip()
        endpoint = commands.run('docker-context-info', [tools['docker'], 'context', 'inspect', context,
            '--format', '{{.Endpoints.docker.Host}}']).strip()
        require(endpoint.startswith('npipe://'), 'LOCAL_DOCKER_CONTEXT_REQUIRED')
        docker = [tools['docker'], '--context', context]
        require(commands.run('docker-engine', docker + ['info', '--format', '{{.OSType}}']).strip() == 'linux', 'LINUX_ENGINE_REQUIRED')
        commands.run('docker-version', docker + ['version', '--format', '{{.Server.Version}}'])
        compose_version = commands.run('compose-version', docker + ['compose', 'version', '--short']).strip().lstrip('v')
        require(compose_version.startswith('2.') or compose_version == '5.5.1', 'COMPOSE_V2_OR_EXACT_5_5_1_REQUIRED')
        image_id = json.loads(commands.run('image', docker + ['image', 'inspect', IMAGE, '--format', '{{json .Id}}']))
        compose_env = artifact / 'compose.env'
        with compose_env.open('x', encoding='ascii') as stream:
            stream.write('')
        compose = docker + ['compose', '--project-name', project, '--env-file', str(compose_env),
                            '--file', str(PACKAGE / 'compose.rg06b.yaml')]

        def inventory():
            containers = commands.run('container-list', docker + ['ps', '-a', '--format', '{{.ID}} {{.Names}} {{.Label "com.docker.compose.project"}}'])
            networks = commands.run('network-list', docker + ['network', 'ls', '--format', '{{.ID}} {{.Name}} {{.Label "com.docker.compose.project"}}'])
            volumes = commands.run('volume-list', docker + ['volume', 'ls', '--format', '{{.Name}} {{.Label "com.docker.compose.project"}}'])
            return containers.splitlines(), networks.splitlines(), volumes.splitlines()

        def relevant(lines):
            return [line for line in lines if project in line.split() or any(x.startswith(project + '-') or x.startswith(project + '_') for x in line.split())]

        require(all(not relevant(lines) for lines in inventory()), 'RESOURCE_COLLISION')
        commands.run('compose-config', compose + ['config', '--quiet'])
        # Daemon operations are outside the CLI Job Object. Any failure preserves resources.
        final.update(docker='CREATION_ATTEMPTED', state='PROVISIONING')
        commands.run('compose-up', compose + ['up', '--detach', '--wait', '--wait-timeout', '90', '--pull', 'never', '--no-build', 'db'], 110)

        def owned_resources():
            listings = inventory()
            require([len(relevant(x)) for x in listings] == [1, 1, 1], 'UNEXPECTED_PROJECT_RESOURCES')
            # Whitelist inspection fields. Config.Env contains the generated password
            # and must never enter command diagnostics or receipts.
            container_format = ('{"Id":{{json .Id}},"Image":{{json .Image}},'
                '"Config":{"Labels":{{json .Config.Labels}}},"State":{{json .State}},'
                '"NetworkSettings":{"Ports":{{json .NetworkSettings.Ports}}},"Mounts":{{json .Mounts}}}')
            container = json.loads(commands.run('container-inspect', docker + ['inspect', project + '-db-1', '--format', container_format]))
            network = json.loads(commands.run('network-inspect', docker + ['network', 'inspect', project + '_default']))[0]
            volume = json.loads(commands.run('volume-inspect', docker + ['volume', 'inspect', project + '_pgdata']))[0]
            for obj, labels in [(container, container['Config']['Labels']), (network, network['Labels']), (volume, volume['Labels'])]:
                require(labels.get(LABEL) == project and labels.get('org.reqguard.run') == run and labels.get('org.reqguard.scope') == 'rg06b-e2e', 'RESOURCE_OWNERSHIP')
            require(container['Image'] == image_id and container['State']['Running'] and container['State']['Health']['Status'] == 'healthy', 'DATABASE_IDENTITY_OR_HEALTH')
            require(container['NetworkSettings']['Ports']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': str(db_port)}], 'DATABASE_PORT_BOUNDARY')
            mounts = container['Mounts']
            require(len(mounts) == 2, 'UNEXPECTED_MOUNTS')
            require(any(m['Type'] == 'volume' and m['Name'] == project + '_pgdata' and m['Destination'] == '/var/lib/postgresql/data' for m in mounts), 'DATABASE_VOLUME')
            require(any(m['Type'] == 'bind' and m['Destination'] == '/schema/001_init.sql' and not m['RW'] for m in mounts), 'SCHEMA_MOUNT')
            require(list(network['Containers']) == [container['Id']], 'UNEXPECTED_NETWORK_MEMBER')
            return {'container': container['Id'], 'network': network['Id'], 'volume': volume['Name'],
                    'volumeCreated': volume['CreatedAt'], 'image': image_id}

        owned = owned_resources()
        write_new(artifact / 'resources.json', owned)
        final.update(docker='OWNED', state='SCHEMA')
        commands.run('schema', compose + ['exec', '-T', 'db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
            '-U', 'reqguard_rg06b', '-d', 'reqguard_rg06b', '-f', '/schema/001_init.sql'])
        final.update(state='TESTING', e2e='ATTEMPTED')
        commands.run('playwright', [node, str(cli), 'test', '--config', str(PACKAGE / 'playwright.config.ts'), '--project=chromium'], 160)
        report = json.loads((artifact / 'results.json').read_text(encoding='utf-8'))
        require(report['stats']['expected'] == 2 and all(report['stats'][k] == 0 for k in ('unexpected', 'skipped', 'flaky')) and not report.get('errors'), 'PLAYWRIGHT_RESULTS')
        specs = []

        def collect(suites):
            for suite in suites:
                specs.extend(suite.get('specs', []))
                collect(suite.get('suites', []))

        collect(report['suites'])
        require(len(specs) == 2 and all(s['ok'] and len(s['tests']) == 1 and
                s['tests'][0]['status'] == 'expected' and len(s['tests'][0]['results']) == 1 and
                s['tests'][0]['results'][0]['status'] == 'passed' for s in specs), 'EXACT_TWO_TEST_OUTCOMES')
        cleanup = json.loads((artifact / 'sql-cleanup.json').read_text(encoding='utf-8'))
        require(cleanup == {'state': 'CLEANED', 'supportedCleaned': True, 'invalidVerified': True, 'uncertain': False}, 'SQL_CLEANUP_UNRESOLVED')
        # No stale process tree remains: Commands.run confirmed an empty Job Object.
        require(owned_resources() == owned, 'RESOURCE_IDENTITY_CHANGED')
        final.update(e2e='PASS', state='TEARDOWN')
        commands.run('compose-down', compose + ['down', '--volumes', '--timeout', '10'], 40)
        require(all(not relevant(lines) for lines in inventory()), 'TEARDOWN_UNRESOLVED')
        final.update(state='PASS', docker='REMOVED_VERIFIED')
    except BaseException as error:
        final['reason'] = str(error) if isinstance(error, Stop) else 'UNEXPECTED_FAILURE'
        final['state'] = 'STOP'
        # No automatic down/retry/cleanup on failure, including ambiguous daemon outcomes.
    finally:
        final['files'] = {str(p.relative_to(artifact)): {'bytes': p.stat().st_size, 'sha256': digest(p)}
                          for p in artifact.rglob('*') if p.is_file()}
        write_new(artifact / 'final.json', final)
    print('RG06B ' + final['state'] + '; run=' + run + '; evidence=quality/browser/.artifacts/<run>/')
    return 0 if final['state'] == 'PASS' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        print('RG06B STOP; no automatic retry; inspect private evidence if created')
        sys.exit(1)
