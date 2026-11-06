"""Test-only RG-06D identity/evidence admission. No import-time I/O or driver imports."""
import ast
import dis
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from types import CodeType


class AdmissionError(Exception):
    pass


def require(value, code):
    if not value:
        raise AdmissionError(code)


def shape(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'ADMISSION_FIELDS')
    return value


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 1_000_000, 'ADMISSION_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'ADMISSION_DUPLICATE_KEY')
            result[key] = value
        return result
    def constant(_):
        raise AdmissionError('ADMISSION_NONFINITE')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise AdmissionError('ADMISSION_JSON') from None


def read(directory, name):
    path = Path(directory) / name
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
            and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'ADMISSION_FILE')
    require(0 < info.st_size <= 1_000_000, 'ADMISSION_SIZE')
    with path.open('rb') as stream:
        raw = stream.read(1_000_001)
    parse(raw)
    return raw


def write(directory, name, value):
    with (Path(directory) / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, allow_nan=False, sort_keys=True)
        stream.write('\n')


SOURCE_KEYS = ('checkout_sha', 'pr_head_sha', 'pr_base_sha', 'tested_merge_sha',
               'github_run_id', 'github_run_attempt', 'inputs', 'python_lock_sha256', 'node_lock_sha256')


OFFICIAL_REPOSITORY = 'Yeromenko-Kateryna/reqguard-quality-platform'


def source_oid(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'SOURCE_COMMIT_OID')
    return value


DIAGNOSTIC_NAME = 'failure-diagnostic.json'
DIAGNOSTIC_LIMIT = 2048
DIAGNOSTIC_DENIAL = '.failure-capture-unavailable'
DIAGNOSTIC_STAGES = ('EARLY_CHECKS', 'SOURCE_INTEGRITY', 'OWNERSHIP_UNIT', 'PG_PRELOAD',
                     'RUNTIME_PACKAGES', 'POSTGRESQL_ADMISSION', 'API_SERVER', 'CHROMIUM',
                     'EVIDENCE_VALIDATION', 'PROCESS_CLEANUP')
DIAGNOSTIC_CLEANUP = ('PENDING', 'COMPLETED', 'FAILED_OR_UNVERIFIED')
DIAGNOSTIC_CODES = {
    'EARLY_CHECKS': ('LINUX_PYTHON_VERSION', 'SUBREAPER_UNAVAILABLE', 'NODE_VERSION', 'NPM_VERSION', 'UV_VERSION'),
    'SOURCE_INTEGRITY': ('SOURCE_OR_LOCK_CHANGED',),
    'OWNERSHIP_UNIT': (),
    'PG_PRELOAD': ('PRELOAD_REQUIRED_MODE', 'PRELOAD_PG_MISSING', 'PRELOAD_PG_VERSION'),
    'RUNTIME_PACKAGES': ('PYTHON_LOCK_MISMATCH', 'NODE_PACKAGE_VERSION', 'CHROMIUM_REVISION', 'CHROMIUM_BOUNDARY'),
    'POSTGRESQL_ADMISSION': ('DB_PORT', 'CI_SERVICE_CREDENTIAL', 'HOSTED_RUNNER_REQUIRED', 'DOCKER_OVERRIDE',
                             'JOB_DOCKER_ENDPOINT', 'ENGINE_ID', 'SERVICE_ID', 'SERVICE_IMAGE_DIGEST',
                             'DB_IDENTITY', 'DB_NOT_FRESH', 'DB_NOT_EMPTY'),
    'API_SERVER': ('PORT_COLLISION', 'SERVER_EXIT_BEFORE_READY', 'SERVER_READINESS_TIMEOUT', 'AMBIENT_NODE_OPTIONS'),
    'CHROMIUM': ('PLAYWRIGHT_OR_SERVER_FAILED', 'EXACT_THREE_SCENARIOS', 'EXACT_THREE_RESULTS'),
    'EVIDENCE_VALIDATION': (),
    'PROCESS_CLEANUP': ('PROCESS_CLEANUP_NOT_VERIFIED',),
}


def diagnostic_binding(run, source):
    validate_source(source, source)
    require(type(run) is str and re.fullmatch('[a-f0-9]{32}', run), 'DIAGNOSTIC_RUN')
    for key in ('github_run_id', 'github_run_attempt'):
        require(len(source[key]) <= 20, 'DIAGNOSTIC_RUN')
    identity = {key: source[key] for key in ('github_run_id', 'github_run_attempt')}
    identity['execution_id'] = run
    reference = {'checkout_sha': source['checkout_sha'], 'source_identity_sha256': hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()}
    return identity, reference


def validate_failure(raw, run, source):
    require(type(raw) is bytes and 0 < len(raw) <= DIAGNOSTIC_LIMIT, 'DIAGNOSTIC_SIZE')
    value = parse(raw)
    require(type(value) is dict, 'DIAGNOSTIC_FIELDS')
    version = value.get('schema_version')
    require(type(version) is str and version in
            ('rg06d-failure-diagnostic-v1', 'rg06d-failure-diagnostic-v2'), 'DIAGNOSTIC_VERSION')
    keys = ('schema_version', 'run_identity', 'source_identity_reference',
            'last_completed_runtime_stage', 'first_failed_runtime_stage',
            'allowlisted_failure_code', 'cleanup_status')
    shape(value, keys + (('first_admission_error_code', 'first_admission_call_site')
                         if version == 'rg06d-failure-diagnostic-v2' else ()))
    identity, reference = diagnostic_binding(run, source)
    shape(value['run_identity'], identity)
    shape(value['source_identity_reference'], reference)
    require(all(type(v) is str and len(v) <= 64 for v in value['run_identity'].values())
            and value['run_identity'] == identity, 'DIAGNOSTIC_RUN')
    require(all(type(v) is str and len(v) <= 64 for v in value['source_identity_reference'].values())
            and value['source_identity_reference'] == reference, 'DIAGNOSTIC_SOURCE')
    for key in ('last_completed_runtime_stage', 'first_failed_runtime_stage',
                'allowlisted_failure_code', 'cleanup_status'):
        require(type(value[key]) is str and len(value[key]) <= 64, 'DIAGNOSTIC_STRING')
    stage = value['first_failed_runtime_stage']
    require(stage in DIAGNOSTIC_STAGES, 'DIAGNOSTIC_STAGE')
    index = DIAGNOSTIC_STAGES.index(stage)
    require(value['last_completed_runtime_stage'] == (DIAGNOSTIC_STAGES[index - 1] if index else 'NONE'),
            'DIAGNOSTIC_TRANSITION')
    require(value['allowlisted_failure_code'] in (*DIAGNOSTIC_CODES[stage], 'ADMISSION_REJECTED', 'EXECUTION_EXCEPTION'),
            'DIAGNOSTIC_CODE')
    require(value['cleanup_status'] in DIAGNOSTIC_CLEANUP, 'DIAGNOSTIC_CLEANUP')
    if version == 'rg06d-failure-diagnostic-v2':
        validate_first_admission(value)
    return value


def validate_first_admission(value):
    code, site = value['first_admission_error_code'], value['first_admission_call_site']
    require(all(type(v) is str and 0 < len(v) <= 64 for v in (code, site)), 'DIAGNOSTIC_FIRST_TYPE')
    broad = value['allowlisted_failure_code']
    if value['first_failed_runtime_stage'] != 'POSTGRESQL_ADMISSION':
        require((code, site) == ('NOT_APPLICABLE', 'NOT_APPLICABLE'), 'DIAGNOSTIC_FIRST_STAGE')
        return
    if broad == 'EXECUTION_EXCEPTION':
        require((code, site) == ('EXECUTION_EXCEPTION', 'UNRESOLVED'), 'DIAGNOSTIC_FIRST_PAIR')
        return
    family = 'R.' if broad != 'ADMISSION_REJECTED' else ('A.', 'P.')
    compatible = {entry[0] for entry in FIRST_ERROR_REGISTRY
                  if entry[0].startswith(family) and entry[1] == code}
    if broad == 'ADMISSION_REJECTED' and code == 'UNRESOLVED':
        require(site == 'UNRESOLVED', 'DIAGNOSTIC_FIRST_PAIR')
    else:
        require(bool(compatible) and (broad == 'ADMISSION_REJECTED' or code == broad)
                and (site == 'UNRESOLVED' or site in compatible), 'DIAGNOSTIC_FIRST_PAIR')


def capture_directory(directory):
    """Owned, existing execution directory; never create or repair a foreign tree."""
    directory = Path(directory)
    diagnostic_path(directory)
    require(re.fullmatch('[a-f0-9]{32}', directory.name) is not None, 'DIAGNOSTIC_RUN')
    info = directory.lstat()
    if hasattr(os, 'geteuid'):
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'DIAGNOSTIC_OWNER')
    return info.st_dev, info.st_ino


def capture_denied(directory):
    capture_directory(directory)
    # lstat, not exists: dangling symlinks and inspection errors also deny.
    try:
        (Path(directory) / DIAGNOSTIC_DENIAL).lstat()
    except FileNotFoundError:
        return False
    return True


def begin_capture(directory):
    identity = capture_directory(directory)
    final = diagnostic_path(directory)
    require(not final.exists() and not final.is_symlink(), 'DIAGNOSTIC_CAPTURE_EXISTS')
    marker = Path(directory) / DIAGNOSTIC_DENIAL
    with marker.open('xb') as stream:
        marker_info = os.fstat(stream.fileno())
        stream.write(b'CAPTURE_NOT_CONFIRMED\n')
        stream.flush()
        os.fsync(stream.fileno())
    require(capture_directory(directory) == identity, 'DIAGNOSTIC_DIRECTORY_CHANGED')
    return identity, (marker_info.st_dev, marker_info.st_ino)


def confirm_capture(directory, identity, raw, run, source):
    require(capture_directory(directory) == identity[0], 'DIAGNOSTIC_DIRECTORY_CHANGED')
    require(read_failure(directory, run, source) == raw, 'DIAGNOSTIC_CAPTURE_CHANGED')
    marker = Path(directory) / DIAGNOSTIC_DENIAL
    info = marker.lstat()
    require(stat.S_ISREG(info.st_mode) and not marker.is_symlink()
            and (info.st_dev, info.st_ino) == identity[1]
            and not getattr(info, 'st_file_attributes', 0) & 0x400
            and info.st_nlink == 1 and info.st_size == 22, 'DIAGNOSTIC_MARKER')
    with marker.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == identity[1]
                and stat.S_ISREG(opened.st_mode) and opened.st_size == 22,
                'DIAGNOSTIC_MARKER')
        require(stream.read(23) == b'CAPTURE_NOT_CONFIRMED\n', 'DIAGNOSTIC_MARKER')
    marker.unlink()


def ast_fingerprint(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def function_nodes(tree):
    result = {}
    def visit(node, prefix=''):
        if isinstance(node, ast.FunctionDef):
            prefix = prefix + '.<locals>.' + node.name if prefix else node.name
            result[prefix] = node
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)
    visit(tree)
    return result


def nested_codes(code):
    yield code
    for child in code.co_consts:
        if isinstance(child, CodeType):
            yield from nested_codes(child)


def registry_model(source, runner_codes):
    """Re-admit source and loaded code; no registry lookup by mutable line number."""
    paths = {'A': Path(__file__), 'C': Path(__file__).with_name('run_rg06d_ci.py')}
    loaded = FIRST_ERROR_HELPER_CODES + runner_codes
    models = {}
    for module, path in paths.items():
        raw = path.read_bytes()
        require(source['inputs'].get('scripts/' + path.name) == hashlib.sha256(raw).hexdigest(),
                'DIAGNOSTIC_REGISTRY_SOURCE')
        nodes = function_nodes(ast.parse(raw))
        compiled = {code.co_qualname: code for code in nested_codes(
            compile(raw, str(path), 'exec', dont_inherit=True, optimize=0))}
        for label, live in loaded:
            if label != module:
                continue
            name = live.co_qualname
            require((module, name) in FIRST_ERROR_FUNCTION_HASHES
                    and ast_fingerprint(nodes[name]) == FIRST_ERROR_FUNCTION_HASHES[module, name]
                    and live == compiled[name], 'DIAGNOSTIC_REGISTRY_CODE')
            models[module, name] = (live, nodes[name])
    require(len(FIRST_ERROR_REGISTRY) == 62
            and len({entry[0] for entry in FIRST_ERROR_REGISTRY}) == 62,
            'DIAGNOSTIC_REGISTRY_DUPLICATE')
    for identifier, code, chain in FIRST_ERROR_REGISTRY:
        require(type(identifier) is str and len(identifier) <= 64
                and re.fullmatch('[A-Z0-9._]+', identifier) and chain, 'DIAGNOSTIC_REGISTRY_ID')
        for module, name, fingerprint in chain:
            node = models[module, name][1]
            require(sum(ast_fingerprint(n) == fingerprint for n in ast.walk(node)
                        if isinstance(n, (ast.Call, ast.Raise))) == 1, 'DIAGNOSTIC_REGISTRY_OPERATION')
    return models


def traceback_operation(trace, node):
    """Match an instruction's full span; CACHE belongs to its preceding opcode."""
    owner = None
    instruction = None
    for item in dis.get_instructions(trace.tb_frame.f_code, show_caches=True, adaptive=False):
        if item.opname != 'CACHE':
            owner = item
        if item.offset == trace.tb_lasti:
            if item.opname == 'CACHE':
                if owner is None or owner.positions != item.positions:
                    return None
                instruction = owner
            else:
                instruction = item
            break
    if instruction is None or instruction.opname not in ('CALL', 'RAISE_VARARGS'):
        return None
    pos = instruction.positions
    if None in (pos.lineno, pos.end_lineno, pos.col_offset, pos.end_col_offset):
        return None
    matches = [n for n in ast.walk(node) if isinstance(n, (ast.Call, ast.Raise))
               and (n.lineno, n.end_lineno, n.col_offset, n.end_col_offset) ==
               (pos.lineno, pos.end_lineno, pos.col_offset, pos.end_col_offset)]
    return ast_fingerprint(matches[0]) if len(matches) == 1 else None


def attribute_first_error(error, stage, source, runner_codes, stop_type):
    """Only the caught object supplies the code. Schema membership is not provenance."""
    args = error.args if type(error) in (AdmissionError, stop_type) else ()
    candidate = args[0] if len(args) == 1 and type(args[0]) is str else None
    if stage != 'POSTGRESQL_ADMISSION':
        broad = (candidate if type(error) is stop_type and candidate in DIAGNOSTIC_CODES[stage]
                 else 'ADMISSION_REJECTED' if type(error) is AdmissionError else 'EXECUTION_EXCEPTION')
        return broad, 'NOT_APPLICABLE', 'NOT_APPLICABLE'
    helper = type(error) is AdmissionError
    fallback = ('ADMISSION_REJECTED', 'UNRESOLVED', 'UNRESOLVED') if helper else (
        'EXECUTION_EXCEPTION', 'EXECUTION_EXCEPTION', 'UNRESOLVED')
    if type(error) not in (AdmissionError, stop_type) or candidate is None:
        return fallback
    try:
        models = registry_model(source, runner_codes)
        traces = []
        trace = error.__traceback__
        while trace is not None:
            if len(traces) == 64:
                return fallback
            traces.append(trace)
            trace = trace.tb_next
        if not traces:
            return fallback
        own = {id(live): (module, name, node) for (module, name), (live, node) in models.items()}
        known = []
        for trace in reversed(traces):
            record = own.get(id(trace.tb_frame.f_code))
            if record is None:
                # Only JSON's known implementation frames may intervene in parser hooks.
                if known and known[-1][1].startswith('parse') and trace.tb_frame.f_code in (
                        json.loads.__code__, json.JSONDecoder.decode.__code__, json.JSONDecoder.raw_decode.__code__):
                    continue
                break
            module, name, node = record
            known.append((module, name, traceback_operation(trace, node)))
        family = ('A.', 'P.') if helper else 'R.'
        eligible = [entry for entry in FIRST_ERROR_REGISTRY
                    if entry[0].startswith(family) and entry[1] == candidate]
        if not eligible:
            return fallback
        # Shared require is necessary, never sufficient. Direct lexical parser raises
        # are separately registered; a familiar code raised elsewhere is unsupported.
        shared = ('A' if helper else 'C', 'require')
        if known and known[0][:2] == shared:
            root = models[shared][1]
            raises = [ast_fingerprint(n) for n in ast.walk(root) if isinstance(n, ast.Raise)]
            if known[0][2] not in raises:
                return fallback
            known = known[1:]
        elif not (helper and known and known[0][1] in ('parse', 'parse.<locals>.constant')):
            return fallback
        # A supported actual leaf is required even to preserve the original code.
        supported = [entry for entry in eligible if known and entry[2][0] == known[0]]
        if not supported:
            return fallback
        broad = 'ADMISSION_REJECTED' if helper else candidate
        exact = [entry[0] for entry in supported if tuple(known) == entry[2]]
        return broad, candidate, exact[0] if len(exact) == 1 else 'UNRESOLVED'
    except Exception:
        return fallback


def diagnostic_path(directory):
    directory = Path(directory)
    require('..' not in directory.parts, 'DIAGNOSTIC_PATH')
    for parent in (directory, *directory.absolute().parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not parent.is_symlink()
                and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'DIAGNOSTIC_PATH')
    return directory / DIAGNOSTIC_NAME


def read_failure(directory, run, source):
    path = diagnostic_path(directory)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
            and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'DIAGNOSTIC_FILE')
    require(0 < info.st_size <= DIAGNOSTIC_LIMIT, 'DIAGNOSTIC_SIZE')
    with path.open('rb') as stream:
        raw = stream.read(DIAGNOSTIC_LIMIT + 1)
    validate_failure(raw, run, source)
    return raw


def atomic_failure(directory, raw, run, source):
    value = validate_failure(raw, run, source)
    path = diagnostic_path(directory)
    if path.exists() or path.is_symlink():
        previous = validate_failure(read_failure(directory, run, source), run, source)
        require({k: v for k, v in value.items() if k != 'cleanup_status'} ==
                {k: v for k, v in previous.items() if k != 'cleanup_status'}, 'DIAGNOSTIC_FIRST_FAILURE')
        require(previous['cleanup_status'] == 'PENDING' or previous == value, 'DIAGNOSTIC_CLEANUP_UPDATE')
    fd, temporary = tempfile.mkstemp(prefix='.failure-diagnostic-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        validate_failure(Path(temporary).read_bytes(), run, source)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def repository_identity(value):
    require(type(value) is dict and type(value.get('owner')) is dict, 'SOURCE_REPOSITORY_FIELDS')
    owner = value['owner']
    require(type(owner.get('login')) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9-]*', owner['login'])
            and type(owner.get('id')) is int and owner['id'] > 0, 'SOURCE_REPOSITORY_OWNER')
    require(type(value.get('name')) is str and re.fullmatch('[A-Za-z0-9_.-]+', value['name'])
            and value.get('full_name') == owner['login'] + '/' + value['name']
            and type(value.get('id')) is int and value['id'] > 0, 'SOURCE_REPOSITORY_IDENTITY')
    return value['full_name'], value['id'], owner['login'], owner['id']


def source_branch(value):
    # Git branch names only, never revision expressions or command options.
    require(type(value) is str and bool(value) and not value.startswith(('/', '-', '.'))
            and not value.endswith(('/', '.')) and '..' not in value and '@{' not in value
            and not re.search(r'[\x00-\x20\x7f~^:?*\[\\]', value)
            and all(part and not part.startswith('.') and not part.endswith('.lock')
                    for part in value.split('/')), 'SOURCE_BRANCH')
    return value


def validate_execution_context(head, event, env):
    """Bind declarations to execution; caller separately verifies real Git objects.

    PR merge_commit_sha is advisory only and intentionally not consumed. Forks
    retain the existing PR trigger policy, with distinct, consistent repo IDs,
    owner/label and head-ref bindings; no arbitrary repository is trusted as base.
    """
    source_oid(head)
    require(head == source_oid(env.get('GITHUB_SHA')), 'CHECKOUT_EVENT_SHA')
    require(type(event) is dict, 'SOURCE_EVENT_OBJECT')
    official = repository_identity(event.get('repository'))
    require(env.get('GITHUB_REPOSITORY') == official[0] == OFFICIAL_REPOSITORY
            and env.get('GITHUB_REPOSITORY_ID') == str(official[1])
            and env.get('GITHUB_REPOSITORY_OWNER') == official[2]
            and env.get('GITHUB_REPOSITORY_OWNER_ID') == str(official[3]), 'SOURCE_REPOSITORY_CONTEXT')
    kind = env.get('GITHUB_EVENT_NAME')
    if kind == 'pull_request':
        pr = event.get('pull_request')
        require(type(pr) is dict, 'SOURCE_PR_FIELDS')
        number = event.get('number')
        require(type(number) is int and number > 0 and type(pr.get('number')) is int
                and pr['number'] == number, 'SOURCE_PR_NUMBER')
        require(env.get('GITHUB_REF') == f'refs/pull/{number}/merge', 'SOURCE_PR_REF')
        for side, context in (('base', 'GITHUB_BASE_REF'), ('head', 'GITHUB_HEAD_REF')):
            value = pr.get(side)
            require(type(value) is dict, 'SOURCE_PR_FIELDS')
            source_oid(value.get('sha'))
            ref = source_branch(value.get('ref'))
            identity = repository_identity(value.get('repo'))
            require(env.get(context) == ref and value.get('label') == identity[2] + ':' + ref,
                    'SOURCE_PR_BRANCH_CONTEXT')
            if side == 'base':
                require(identity == official, 'SOURCE_PR_BASE_REPOSITORY')
            else:
                # Same name must mean same stable ID and vice versa.
                require((identity[0] == official[0]) == (identity[1] == official[1]),
                        'SOURCE_PR_HEAD_REPOSITORY')
                require((identity[2] == official[2]) == (identity[3] == official[3]),
                        'SOURCE_PR_HEAD_OWNER')
                if identity[0] == official[0]:
                    require(identity == official, 'SOURCE_PR_HEAD_REPOSITORY')
                else:
                    require(value['repo'].get('fork') is True, 'SOURCE_PR_HEAD_FORK')
                user = value.get('user')
                if user is not None:
                    require(type(user) is dict and user.get('login') == identity[2]
                            and type(user.get('id')) is int and user['id'] == identity[3],
                            'SOURCE_PR_HEAD_USER')
        return pr
    # Explicit paths already exposed by this workflow; all other events reject.
    require(kind in ('push', 'workflow_dispatch'), 'SOURCE_EVENT_KIND')
    require('pull_request' not in event and not env.get('GITHUB_HEAD_REF')
            and not env.get('GITHUB_BASE_REF'), 'SOURCE_NON_PR_CONTEXT')
    if kind == 'push':
        require(env.get('GITHUB_REF') == event.get('ref') == 'refs/heads/main'
                and event.get('after') == head and event.get('deleted') is False, 'SOURCE_PUSH_CONTEXT')
    else:
        ref = source_branch(event.get('ref'))
        require(env.get('GITHUB_REF') == 'refs/heads/' + ref, 'SOURCE_DISPATCH_CONTEXT')
    return None


def validate_source(source, expected):
    shape(source, SOURCE_KEYS)
    require(source == expected, 'SOURCE_MISMATCH')
    for key in ('checkout_sha', 'pr_head_sha', 'pr_base_sha', 'tested_merge_sha'):
        value = source[key]
        require((value is None and key != 'checkout_sha') or
                (type(value) is str and re.fullmatch('[0-9a-f]{40}', value)), 'SOURCE_SHA')
    if source['tested_merge_sha'] is not None:
        require(source['tested_merge_sha'] == source['checkout_sha']
                and source['pr_head_sha'] is not None and source['pr_base_sha'] is not None, 'SOURCE_MERGE')
    require((source['pr_head_sha'] is None) == (source['pr_base_sha'] is None), 'SOURCE_PR')
    for key in ('github_run_id', 'github_run_attempt'):
        require(type(source[key]) is str and re.fullmatch('[1-9][0-9]*', source[key]), 'SOURCE_RUN')
    require(type(source['inputs']) is dict and bool(source['inputs']), 'SOURCE_INPUTS')
    require(all(type(k) is str and type(v) is str and re.fullmatch('[a-f0-9]{64}', v)
                for k, v in source['inputs'].items()), 'SOURCE_HASH')
    require(source['python_lock_sha256'] == source['inputs'].get('uv.lock') and
            source['node_lock_sha256'] == source['inputs'].get('quality/browser/package-lock.json'), 'SOURCE_LOCK')


IDENTITY_SQL = """SELECT current_database()::text AS db, current_user::text AS role,
 current_setting('server_version_num') AS version,
 (SELECT system_identifier::text FROM pg_control_system()) AS system_id,
 inet_server_addr()::text AS address, inet_server_port() AS port,
 pg_backend_pid() AS backend_pid"""
FINGERPRINT_KEYS = ('db', 'role', 'version', 'system_id')
OBSERVATION_KEYS = (*FINGERPRINT_KEYS, 'address', 'port', 'backend_pid')


def validate_identity(observed, expected, path):
    shape(observed, OBSERVATION_KEYS)
    shape(expected, FINGERPRINT_KEYS)
    shape(path, ('address', 'port'))
    require({k: observed[k] for k in FINGERPRINT_KEYS} == expected, 'BACKEND_IDENTITY_MISMATCH')
    require(observed['db'] == observed['role'] == 'reqguard_rg06b' and observed['version'] == '170011', 'BACKEND_PRINCIPAL')
    require(type(observed['system_id']) is str and re.fullmatch('[1-9][0-9]*', observed['system_id']), 'BACKEND_SYSTEM')
    require(type(path['address']) is str and ipaddress.ip_address(path['address']).version == 4
            and not ipaddress.ip_address(path['address']).is_unspecified, 'BACKEND_PATH')
    require(type(observed['address']) is str and observed['address'] == path['address'] and
            type(observed['port']) is int and type(path['port']) is int
            and observed['port'] == path['port'] == 5432, 'BACKEND_ADDRESS')
    require(type(observed['backend_pid']) is int and observed['backend_pid'] > 0, 'BACKEND_PID')


def validate_client_target(host, port, target):
    shape(target, ('host', 'port'))
    require(target['host'] == host == '127.0.0.1' and type(port) is int
            and type(target['port']) is int and port == target['port']
            and 1024 <= port <= 65535, 'CLIENT_TARGET')


def validate_bindings(mappings, host_port):
    # Policy applies only after hosted-runner/local-daemon admission in RG-06D.
    # https://docs.docker.com/engine/network/port-publishing/#setting-the-default-bind-address-for-containers
    # Workflow publishes 5432/tcp without an IP: Docker's normalized IPv4 wildcard
    # binds include 127.0.0.1. An optional IPv6 wildcard companion is supported,
    # but IPv6-only, empty, duplicate and mixed-specific-interface binds are not.
    require(type(host_port) is str and host_port.isascii() and host_port.isdecimal()
            and 1024 <= int(host_port) <= 65535, 'SERVICE_PORT')
    require(type(mappings) is list and 1 <= len(mappings) <= 2, 'SERVICE_BINDINGS')
    addresses = []
    for item in mappings:
        shape(item, ('HostIp', 'HostPort'))
        require(item['HostPort'] == host_port, 'SERVICE_PORT')
        require(type(item['HostIp']) is str, 'SERVICE_HOSTIP')
        addresses.append(item['HostIp'])
    require(sorted(addresses) in (['0.0.0.0'], ['0.0.0.0', '::']), 'SERVICE_HOSTIP')


def observe(connection):
    # A dedicated read-only transaction finishes before the connection is handed back.
    require(connection.info.transaction_status == 0, 'IDENTITY_CONNECTION_NOT_IDLE')
    autocommit = connection.autocommit
    with connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute("SET LOCAL statement_timeout = '5s'")
        with connection.cursor() as cursor:
            cursor.execute(IDENTITY_SQL)
            values = cursor.fetchone()
            require(values is not None, 'IDENTITY_MISSING')
            result = dict(zip(OBSERVATION_KEYS, values, strict=True))
    require(connection.info.transaction_status == 0 and connection.autocommit == autocommit, 'IDENTITY_TRANSACTION_STATE')
    return result


def guarded_connect(original, expected, emit, path, target):
    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)  # Preserve original connection failures.
        try:
            validate_client_target(connection.info.host, connection.info.port, target)
            observed = observe(connection)
            validate_identity(observed, expected, path)
            emit(observed)  # Evidence failure also prevents INSERT.
            return connection
        except BaseException:
            try:
                connection.close()
            except BaseException:
                pass
            raise
    return connect


def validate_service(container, image, service_id, network, host_port, network_name):
    require(type(service_id) is str and re.fullmatch('[a-f0-9]{64}', service_id), 'SERVICE_ID')
    require(container['Id'] == service_id and container['Image'] == image['Id'], 'SERVICE_IDENTITY')
    require(container['State']['Running'] is True and container['State']['Health']['Status'] == 'healthy', 'SERVICE_HEALTH')
    require(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'SERVICE_ARCH')
    require(type(container.get('NetworkSettings')) is dict
            and type(container['NetworkSettings'].get('Networks')) is dict, 'SERVICE_NETWORK')
    require(len(container['NetworkSettings']['Networks']) == 1, 'SERVICE_NETWORK')
    require(classify_network_reference(network) == 'ID'
            and classify_network_reference(network_name) == 'NAME'
            and all(type(v) is dict and classify_network_reference(v.get('NetworkID')) == 'ID'
                    and 'IPAddress' in v for v in container['NetworkSettings']['Networks'].values()), 'SERVICE_NETWORK')
    require(container['NetworkSettings']['Networks'] and
            {v['NetworkID'] for v in container['NetworkSettings']['Networks'].values()} == {network}, 'SERVICE_NETWORK')
    require(set(container['NetworkSettings']['Ports']) == {'5432/tcp'}, 'SERVICE_EXPOSED_PORTS')
    validate_bindings(container['NetworkSettings']['Ports']['5432/tcp'], host_port)
    require(set(container['NetworkSettings']['Networks']) == {network_name}, 'SERVICE_NETWORK')
    address = next(iter(container['NetworkSettings']['Networks'].values()))['IPAddress']
    require(type(address) is str and ipaddress.ip_address(address).version == 4
            and not ipaddress.ip_address(address).is_unspecified
            and not ipaddress.ip_address(address).is_loopback, 'SERVICE_ADDRESS')
    require(not any(m['Type'] == 'bind' for m in container['Mounts']), 'SERVICE_BIND')
    # Only a fresh job-local PGDATA mount is allowed, never an arbitrary extra mount.
    require(len(container['Mounts']) == 1 and container['Mounts'][0]['Type'] == 'volume'
            and container['Mounts'][0]['Destination'] == '/var/lib/postgresql/data', 'SERVICE_STORAGE')


OWNERSHIP_KEYS = ('schema_version', 'run_id', 'source_identity', 'scenario', 'foreign_run_id',
                  'registry_owner', 'ownership_rejection', 'sql_dispatch_count', 'delete_dispatch_count',
                  'foreign_row_before', 'foreign_row_after', 'preservation_verified',
                  'preservation_verified_before_teardown', 'fixture_teardown')


def validate_ownership(raw, preservation_raw, run, source):
    before, final = parse(preservation_raw), parse(raw)
    shape(before, OWNERSHIP_KEYS)
    shape(final, (*OWNERSHIP_KEYS, 'preservation_sha256'))
    require(final['preservation_sha256'] == hashlib.sha256(preservation_raw).hexdigest(), 'PRESERVATION_HASH')
    require({k: v for k, v in final.items() if k not in ('fixture_teardown', 'preservation_sha256')} ==
            {k: v for k, v in before.items() if k != 'fixture_teardown'}, 'PRESERVATION_CHANGED')
    require(before['fixture_teardown'] == 'NOT_ATTEMPTED' and final['fixture_teardown'] == 'COMMITTED_BASELINE_RESTORED', 'FIXTURE_TEARDOWN')
    require(final['schema_version'] == 'rg06d-ownership-v1' and final['run_id'] == run
            and type(run) is str and re.fullmatch('[a-f0-9]{32}', run), 'OWNERSHIP_RUN')
    validate_source(final['source_identity'], source)
    require(final['scenario'] == 'foreign-row-rejection' and final['ownership_rejection'] == 'OwnershipRejected', 'OWNERSHIP_REJECTION')
    require(type(final['registry_owner']) is str and re.fullmatch('[a-f0-9]{32}', final['registry_owner'])
            and final['registry_owner'] != run, 'REGISTRY_OWNER')
    for key in ('sql_dispatch_count', 'delete_dispatch_count'):
        require(type(final[key]) is int and final[key] == 0, 'UNAUTHORIZED_DISPATCH')
    require(final['preservation_verified'] is True and final['preservation_verified_before_teardown'] is True, 'PRESERVATION_ORDER')
    row = final['foreign_row_before']
    shape(row, ('run_id', 'provider', 'status', 'original_input', 'analysis_payload', 'created_at', 'sql_null'))
    require(type(final['foreign_run_id']) is str and re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}', final['foreign_run_id']), 'FOREIGN_ID')
    require(row['run_id'] == final['foreign_run_id'] and row['provider'] == 'fake' and
            row['status'] == 'unsupported_fixture' and row['analysis_payload'] is None and row['sql_null'] is True,
            'FOREIGN_ROW')
    require(row['original_input'] == 'RG06B synthetic foreign fixture ' + final['registry_owner'], 'FOREIGN_MARKER')
    from datetime import datetime
    require(type(row['created_at']) is str and datetime.fromisoformat(row['created_at']).utcoffset() is not None, 'FOREIGN_TIMESTAMP')
    require(final['foreign_row_after'] == row, 'FOREIGN_CHANGED')
    shape(final['foreign_row_after'], row)
    require(all(type(final['foreign_row_after'][k]) is type(v) for k, v in row.items()), 'FOREIGN_TYPES')


UNIT_NAMES = (
    'unowned existing UUID is rejected before the actual SQL execution boundary',
    'verified creation evidence permits exactly one positive cleanup',
    'wrong-run, preexisting-row and changed-row evidence do not confer cleanup authority',
    'ambiguous COMMIT blocks every further cleanup without destructive retry',
)


def validate_unit(value, run, source):
    shape(value, ('schema_version', 'run_id', 'source_identity', 'exit_code', 'report'))
    require(value['schema_version'] == 'rg06d-unit-v1' and value['run_id'] == run, 'UNIT_RUN')
    validate_source(value['source_identity'], source)
    require(type(value['exit_code']) is int and value['exit_code'] == 0, 'UNIT_EXIT')
    report = shape(value['report'], ('cases', 'summary'))
    require(type(report['cases']) is list and len(report['cases']) == 4, 'UNIT_COUNT')
    require(sorted(c['name'] for c in report['cases']) == sorted(UNIT_NAMES), 'UNIT_NAMES')
    for case in report['cases']:
        shape(case, ('name', 'passed', 'skip', 'todo', 'nesting'))
        require(case['passed'] is True and case['skip'] is False and case['todo'] is False
                and type(case['nesting']) is int and case['nesting'] == 0, 'UNIT_CASE')
    expected = {'tests': 4, 'passed': 4, 'failed': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0, 'suites': 0}
    shape(report['summary'], expected)
    require(all(type(v) is int for v in report['summary'].values()) and report['summary'] == expected, 'UNIT_SUMMARY')


PRELOAD_NAME = 'actual locked pg receives the NODE_OPTIONS preload before caller mutation'


def validate_preload(value, run, source):
    shape(value, ('schema_version', 'run_id', 'source_identity', 'exit_code', 'pg_version', 'report'))
    require(value['schema_version'] == 'rg06d-preload-v1' and value['run_id'] == run, 'PRELOAD_RUN')
    validate_source(value['source_identity'], source)
    require(type(value['exit_code']) is int and value['exit_code'] == 0, 'PRELOAD_EXIT')
    require(value['pg_version'] == '8.23.1', 'PRELOAD_PG_VERSION')
    report = shape(value['report'], ('cases', 'summary'))
    require(type(report['cases']) is list and len(report['cases']) == 1, 'PRELOAD_COUNT')
    case = shape(report['cases'][0], ('name', 'passed', 'skip', 'todo', 'nesting'))
    require(case['name'] == PRELOAD_NAME and case['passed'] is True and case['skip'] is False
            and case['todo'] is False and type(case['nesting']) is int and case['nesting'] == 0, 'PRELOAD_CASE')
    expected = {'tests': 1, 'passed': 1, 'failed': 0, 'cancelled': 0, 'skipped': 0, 'todo': 0, 'suites': 0}
    shape(report['summary'], expected)
    require(all(type(v) is int for v in report['summary'].values())
            and report['summary'] == expected, 'PRELOAD_SUMMARY')


def validate_connections(value, run, source, expected, path):
    shape(value, ('schema_version', 'run_id', 'source_identity', 'connections'))
    require(value['schema_version'] == 'rg06d-connections-v1' and value['run_id'] == run, 'CONNECTION_RUN')
    validate_source(value['source_identity'], source)
    connections = value['connections']
    # Existing three scenarios open one verifier connection and two API connections.
    require(type(connections) is list and sorted(c['kind'] for c in connections) == ['api', 'api', 'verifier'], 'CONNECTION_COUNTS')
    require(len({c['receipt_id'] for c in connections}) == 3, 'CONNECTION_DUPLICATE')
    for item in connections:
        shape(item, ('receipt_id', 'kind', 'identity'))
        require(type(item['receipt_id']) is str and re.fullmatch('[a-f0-9]{32}', item['receipt_id']), 'CONNECTION_RECEIPT_ID')
        validate_identity(item['identity'], expected, path)




SERVICE_INPUTS = ('pyproject.toml', 'uv.lock', 'db/001_init.sql', 'reqguard/main.py', 'reqguard/persistence.py', 'reqguard/static/index.html', 'reqguard/static/app.mjs', 'reqguard/static/style.css', 'quality/browser/package.json', 'quality/browser/package-lock.json', 'quality/browser/analyses.spec.ts', 'quality/browser/playwright.config.ts', 'quality/browser/playwright.ci.config.ts', 'scripts/run_rg06d_ci.py', '.github/workflows/rg06d-e2e.yml', 'quality/browser/owned-cleanup.ts', 'quality/browser/owned-cleanup.test.ts', 'quality/browser/ci-identity.mjs', 'quality/browser/unit-reporter.mjs', 'scripts/rg06d_admission.py', 'scripts/test_rg06d_admission.py', 'quality/browser/ci-identity.test.mjs', 'quality/browser/ci-preload.integration.test.mjs', 'quality/browser/ci-preload-checks.mjs', 'quality/browser/ci-preload-gate.test.mjs')
SERVICE_IMAGE = 'postgres:17.11-bookworm@sha256:ec4dfc6571f04fe0731ce948c1500d676af49a7224392dcc6995cc1ee33a94bb'

SERVICE_KEYS = ('schema_version', 'run_id', 'source_identity', 'container_id', 'engine_id',
                'endpoint', 'image', 'image_id', 'network_reference', 'network_name', 'network_id',
                'attachment_network_name', 'attachment_network_id', 'host_port', 'fingerprint',
                'service_observation', 'host_path', 'host_target', 'published_bindings')
CHILD_EXPECTATIONS = ('RG06B_RUN_ID', 'RG06B_ARTIFACT', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
                      'GITHUB_SHA', 'RG06D_EXPECTED_SOURCE_IDENTITY_SHA256', 'RG06D_SERVICE_ID',
                      'RG06D_SERVICE_NETWORK', 'RG06B_DB_PORT')


def classify_network_reference(value):
    if type(value) is not str: return 'REJECT'
    if re.fullmatch(r'[a-f0-9]{64}', value): return 'ID'
    if re.fullmatch(r'[a-f0-9]+', value): return 'REJECT'
    if re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}', value): return 'NAME'
    return 'REJECT'


def validate_network(network, reference):
    kind = classify_network_reference(reference)
    require(kind != 'REJECT', 'SERVICE_NETWORK')
    shape(network, ('Id', 'Name'))
    require(classify_network_reference(network['Id']) == 'ID'
            and classify_network_reference(network['Name']) == 'NAME', 'SERVICE_NETWORK')
    require(network['Id' if kind == 'ID' else 'Name'] == reference, 'SERVICE_NETWORK')
    return network


def validate_source_domain(source):
    # D0 validate_source and diagnostic_binding retain their existing wider behavior.
    validate_source(source, source)
    require(set(source['inputs']) == set(SERVICE_INPUTS), 'SOURCE_PRODUCER_DOMAIN')
    return source


def canonical_source_bytes(source):
    validate_source_domain(source)
    return json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def validate_service_receipt(service, run, source, env):
    shape(service, SERVICE_KEYS)
    require(service['schema_version'] == 'rg06d-service-v3' and service['run_id'] == run
            and type(run) is str and re.fullmatch('[a-f0-9]{32}', run), 'SERVICE_RECEIPT')
    validate_source_domain(service['source_identity'])
    validate_source(service['source_identity'], source)
    require(source['github_run_id'] == env['GITHUB_RUN_ID']
            and source['github_run_attempt'] == env['GITHUB_RUN_ATTEMPT'], 'SERVICE_CONTEXT')
    for key in ('container_id', 'engine_id', 'endpoint', 'image', 'image_id', 'network_reference',
                'network_name', 'network_id', 'attachment_network_name', 'attachment_network_id', 'host_port'):
        require(type(service[key]) is str and 0 < len(service[key]) <= 512, 'SERVICE_RECEIPT_TYPE')
        service[key].encode('utf-8')  # Escaped unpaired surrogates are not Unicode scalar values.
    require(classify_network_reference(service['container_id']) == 'ID'
            and service['container_id'] == env['RG06D_SERVICE_ID']
            and service['host_port'] == env['RG06B_DB_PORT']
            and service['endpoint'] == 'unix:///var/run/docker.sock' and service['image'] == SERVICE_IMAGE
            and re.fullmatch('sha256:[a-f0-9]{64}', service['image_id']), 'SERVICE_CONTEXT')
    expected_reference = env['RG06D_SERVICE_NETWORK']
    require(classify_network_reference(expected_reference) != 'REJECT'
            and classify_network_reference(service['network_reference']) == classify_network_reference(expected_reference)
            and service['network_reference'] == expected_reference, 'SERVICE_NETWORK')
    validate_network({'Id': service['network_id'], 'Name': service['network_name']}, expected_reference)
    require(classify_network_reference(service['attachment_network_id']) == 'ID'
            and classify_network_reference(service['attachment_network_name']) == 'NAME'
            and service['attachment_network_id'] == service['network_id']
            and service['attachment_network_name'] == service['network_name'], 'SERVICE_NETWORK')
    validate_bindings(service['published_bindings'], service['host_port'])
    validate_client_target('127.0.0.1', int(service['host_port']), service['host_target'])
    validate_identity(service['service_observation'], service['fingerprint'], {'address': '127.0.0.1', 'port': 5432})
    shape(service['host_path'], ('address', 'port'))
    host = service['host_path']
    require(type(host['address']) is str and ipaddress.ip_address(host['address']).version == 4
            and not ipaddress.ip_address(host['address']).is_loopback
            and not ipaddress.ip_address(host['address']).is_unspecified
            and type(host['port']) is int and host['port'] == 5432, 'SERVICE_HOST_PATH')
    return service


def child_artifact(env, root):
    require(all(type(env.get(k)) is str and bool(env[k]) for k in CHILD_EXPECTATIONS), 'CHILD_EXPECTATIONS')
    require(re.fullmatch('[a-f0-9]{32}', env['RG06B_RUN_ID'])
            and re.fullmatch('[a-f0-9]{40}', env['GITHUB_SHA'])
            and re.fullmatch('[a-f0-9]{64}', env['RG06D_EXPECTED_SOURCE_IDENTITY_SHA256'])
            and re.fullmatch('[a-f0-9]{64}', env['RG06D_SERVICE_ID']), 'CHILD_EXPECTATIONS')
    require(all(re.fullmatch('[1-9][0-9]*', env[k]) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
            and classify_network_reference(env['RG06D_SERVICE_NETWORK']) != 'REJECT'
            and re.fullmatch('[0-9]+', env['RG06B_DB_PORT'])
            and 1024 <= int(env['RG06B_DB_PORT']) <= 65535, 'CHILD_EXPECTATIONS')
    expected = root / 'quality/browser/.artifacts' / env['RG06B_RUN_ID']
    require(env['RG06B_ARTIFACT'] == str(expected), 'CHILD_ARTIFACT')
    diagnostic_path(expected)  # Existing ancestor/symlink/reparse and traversal policy.
    return expected


def validate_child_service(service, env):
    source = validate_source_domain(service['source_identity'])
    require(source['checkout_sha'] == env['GITHUB_SHA']
            and source['github_run_id'] == env['GITHUB_RUN_ID']
            and source['github_run_attempt'] == env['GITHUB_RUN_ATTEMPT']
            and hashlib.sha256(canonical_source_bytes(source)).hexdigest() ==
                env['RG06D_EXPECTED_SOURCE_IDENTITY_SHA256'], 'CHILD_SOURCE')
    # The received source has now been compared to independent parent digest/CI values.
    return validate_service_receipt(service, env['RG06B_RUN_ID'], source, env)


def read_child_service(directory):
    path = directory / 'service-identity.json'
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
            and not getattr(before, 'st_file_attributes', 0) & 0x400
            and 0 < before.st_size <= 65536, 'CHILD_FILE')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'CHILD_FILE')
        raw = stream.read(65537)
        after = os.fstat(stream.fileno())
    require(0 < len(raw) <= 65536 and before.st_size == after.st_size == len(raw)
            and before.st_mtime_ns == after.st_mtime_ns
            and (path.lstat().st_dev, path.lstat().st_ino) == (before.st_dev, before.st_ino), 'CHILD_FILE')
    return parse(raw)


def api_main():
    # Used only as the child-process entrypoint of the Linux test harness.
    import sys
    import uuid
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    try:
        path = child_artifact(os.environ, root)
        service = validate_child_service(read_child_service(path), os.environ)
    except Exception:
        print('RG06D_API_RECEIPT_REJECTED', file=sys.stderr)
        return 1
    expected = service['fingerprint']
    import psycopg
    import uvicorn
    def emit(identity):
        receipt_id = uuid.uuid4().hex
        write(path, 'connection-' + receipt_id + '.json', {'receipt_id': receipt_id, 'kind': 'api', 'identity': identity})
    psycopg.connect = guarded_connect(psycopg.connect, expected, emit, service['host_path'], service['host_target'])
    uvicorn.run('reqguard.main:app', host='127.0.0.1', port=int(os.environ['RG06B_API_PORT']), workers=1)


if __name__ == '__main__':
    raise SystemExit(api_main())


# Reviewed semantic sites. SHA-256 values bind normalized AST operations, not lines.
FIRST_ERROR_REGISTRY = (
    ('R.PG.PORT', 'DB_PORT', (('C', 'run_tests', '760bc43470115ff3426ae3b8257a0538593b3dec852ddec2b4023d7f17487956'),)),
    ('R.PG.CREDENTIAL', 'CI_SERVICE_CREDENTIAL', (('C', 'run_tests', '11018020dc0c95b5e3e44b3badb262172a5687a8249a3e955160a24d328fdc6c'),)),
    ('R.PG.DB_ID', 'DB_IDENTITY', (('C', 'run_tests', '92b173e9852fd5145ec64a35f6d441841b44e1244cb5b05c65df3080a9cef333'),)),
    ('R.PG.FRESH', 'DB_NOT_FRESH', (('C', 'run_tests', '494e97c914bbcc60b52da20ef520e6e6f078ac555a63564e303ad7a5b1a89f70'),)),
    ('R.PG.EMPTY', 'DB_NOT_EMPTY', (('C', 'run_tests', 'a9c62e74c9422ee1536f2152731f314cce04b03aaf4deeaf90a6c245a94379c2'),)),
    ('R.SVC.HOSTED', 'HOSTED_RUNNER_REQUIRED', (('C', 'service_admission', 'ed85b483c228cdbb1a0c9c014f6434e788b647e0da015e88b324c08ca8459754'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('R.SVC.NO_OVERRIDE', 'DOCKER_OVERRIDE', (('C', 'service_admission', '321d15d3403a31d3ed3a9fc0aac83b10e45867f316b40e0837178795e82967dc'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('R.SVC.ENDPOINT', 'JOB_DOCKER_ENDPOINT', (('C', 'service_admission', '19aa029f5b940fcc01729cdea90b3801ebd9ff4b488cdd09d7e3cfa8eb339f42'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('R.SVC.ENGINE', 'ENGINE_ID', (('C', 'service_admission', 'b803fe9fa543f21b5237494f49275022fa5f86a2d1060b0ab033e10537a55294'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('R.SVC.ID', 'SERVICE_ID', (('C', 'service_admission', '18f38a09d2adf6ef01aaf34e75ebb8851fb883ed9c6ebac0496c5ddcfa925a88'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('R.SVC.DIGEST', 'SERVICE_IMAGE_DIGEST', (('C', 'service_admission', '439c6a2d3124de3b0b24c38b7b8aa3651b965c950e81db55c09776fa2554b8a1'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.ID', 'SERVICE_ID', (('A', 'validate_service', '8addd2f9b052c429813d2ad653ecd031cee4d72feb94fe8b33f271e18779913c'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.IDENTITY', 'SERVICE_IDENTITY', (('A', 'validate_service', '39bcadd3558e679bbdece7938f7076c043cc83a2a448de30c36cd929e2668f5e'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.HEALTH', 'SERVICE_HEALTH', (('A', 'validate_service', '41e7ea800299fe9ad9418c422dbb74cff3faf415b9a2bde55bfae161a6183160'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.ARCH', 'SERVICE_ARCH', (('A', 'validate_service', '83571c748a09f54c91eee23a33333bfbc85979e0db6cee217c282fbdad7b808d'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.NETWORK_ID_SET', 'SERVICE_NETWORK', (('A', 'validate_service', '5f36dd577109d645f0dcae9ca65cc8eb33115bbba81a2c18df4c09ff458db19f'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.PORT_KEYS', 'SERVICE_EXPOSED_PORTS', (('A', 'validate_service', 'ae33c48e39feee2fd055ad61287c3b4f5b1b8085cf849f122783de25c6d99c20'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.NETWORK_COUNT', 'SERVICE_NETWORK', (('A', 'validate_service', '96397de25e349a3c93ddd3d8c50c44310b556d716aeab9a9f6abe879ede1785b'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.ADDRESS', 'SERVICE_ADDRESS', (('A', 'validate_service', '9560e5d36879081cb14912591e7c4d8621e8c4ca40e138738896fddd4a66356e'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.NO_BIND', 'SERVICE_BIND', (('A', 'validate_service', 'bb17c1e23f993781e04b175c7a666ecf5cc796c38eb3443a90190924578be4c5'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVC.PGDATA', 'SERVICE_STORAGE', (('A', 'validate_service', '09baa2e4bb39156ac35498ebfafc62c9980a1c902bfa203b6e54d913a8e7cc72'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.PORT_INPUT', 'SERVICE_PORT', (('A', 'validate_bindings', '14738e5ea9b60ca0e96eb2959497af50cc4dfd8512bc1cdf9a7dfb9364a8ed74'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.COUNT', 'SERVICE_BINDINGS', (('A', 'validate_bindings', '361722cb7a483d7de27999fb4982fe0d15f1fe424a351660206703bd82524a42'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.ITEM_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_bindings', '15a6ca75a362284c5d0216a024516fc6318dc38cc479ea7c4982bfdf4b16e6a7'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.PORT_MATCH', 'SERVICE_PORT', (('A', 'validate_bindings', '35060dbf7c3a1710573dbc6963eff8938a376d12aeb6f72d2879cb94611c4182'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.IP_TYPE', 'SERVICE_HOSTIP', (('A', 'validate_bindings', 'c6d6c9dc715ece54e5eed561f8021cd4321ecc5d85a959ea604c8d0044738653'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.BIND.IP_SET', 'SERVICE_HOSTIP', (('A', 'validate_bindings', '9c0fb25d8e41d22cf7d26a5f72e89c0ac051d09407f258c9d0c5d8f28fbb69a6'), ('A', 'validate_service', 'deb5a4e2dc8fdb7754659f2c0e677fa2038a6870d755247756bf6334033fea19'), ('C', 'service_admission', 'd2a0e2a2a2aa8b1e58a7068659df0b9fa077f872cea9d1c15a9b2586fbdce263'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.OBS_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', '344ac419fad4fa33a11edf7235937b5a5238f35d4e79ff1e4f542befff5dc2e3'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.FP_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', 'c76301082df8ac9853579fcf5ce1db69e53e08452da12d6198c7dd0cc8a766b6'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.PATH_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', '88087867c4ed9bcd9f0c69e3122c5845bfa52f2d6e0cf3a0cfede94e7261a1a5'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.FP_MATCH', 'BACKEND_IDENTITY_MISMATCH', (('A', 'validate_identity', 'a6b2b2fa69949044953ff269f0bb2cbb917b8583327143c556b00b899bcf8e61'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.PRINCIPAL', 'BACKEND_PRINCIPAL', (('A', 'validate_identity', '069bc53db72a01a4e8794bbf6d5ed49e57c323d7377ef4c63c733ded262f3343'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.SYSTEM', 'BACKEND_SYSTEM', (('A', 'validate_identity', 'b4d9fa7640b09c026faa14d04a001865040951992b5829a6ae61f03ad71b0968'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.PATH', 'BACKEND_PATH', (('A', 'validate_identity', 'ea278a19b56e0c588ddcea3eb205ac80b1cd8fe0efa39cfac90b66b7ce42fbe1'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.ADDRESS', 'BACKEND_ADDRESS', (('A', 'validate_identity', '9af1548e650e5593eba4281d136bbd484e8f5613133d5a2127c552c15afed61b'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.SVCID.PID', 'BACKEND_PID', (('A', 'validate_identity', '4abc573906873e15821dc22221dd529bd4e18a0c7557de78fcd839ec56b4bae1'), ('C', 'service_admission', '0d20d62cdbf632b2fc9da34bb9e65b482cbc8089714932657cc3c96200d576aa'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('A.HOSTID.OBS_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', '344ac419fad4fa33a11edf7235937b5a5238f35d4e79ff1e4f542befff5dc2e3'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.FP_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', 'c76301082df8ac9853579fcf5ce1db69e53e08452da12d6198c7dd0cc8a766b6'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.PATH_FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_identity', '88087867c4ed9bcd9f0c69e3122c5845bfa52f2d6e0cf3a0cfede94e7261a1a5'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.FP_MATCH', 'BACKEND_IDENTITY_MISMATCH', (('A', 'validate_identity', 'a6b2b2fa69949044953ff269f0bb2cbb917b8583327143c556b00b899bcf8e61'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.PRINCIPAL', 'BACKEND_PRINCIPAL', (('A', 'validate_identity', '069bc53db72a01a4e8794bbf6d5ed49e57c323d7377ef4c63c733ded262f3343'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.SYSTEM', 'BACKEND_SYSTEM', (('A', 'validate_identity', 'b4d9fa7640b09c026faa14d04a001865040951992b5829a6ae61f03ad71b0968'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.PATH', 'BACKEND_PATH', (('A', 'validate_identity', 'ea278a19b56e0c588ddcea3eb205ac80b1cd8fe0efa39cfac90b66b7ce42fbe1'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.ADDRESS', 'BACKEND_ADDRESS', (('A', 'validate_identity', '9af1548e650e5593eba4281d136bbd484e8f5613133d5a2127c552c15afed61b'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.HOSTID.PID', 'BACKEND_PID', (('A', 'validate_identity', '4abc573906873e15821dc22221dd529bd4e18a0c7557de78fcd839ec56b4bae1'), ('C', 'run_tests', 'c91469bb6bc0ed9827f7c0f03437d98ace9cca3636ac03a785437a97adf37c37'))),
    ('A.TARGET.FIELDS', 'ADMISSION_FIELDS', (('A', 'shape', 'f7ec4707e4f0c935f97370846797f55c44db7653983a78221fea8d0606861434'), ('A', 'validate_client_target', 'c5fe6dad08eecd1f4b0d191c49269ab2b995bfad439cf21cc2803cb7116d4e74'), ('C', 'run_tests', 'c54e67affff0519cef83945997ce04e0df8eddde6067b2ce39334a07e6dab163'))),
    ('A.TARGET.MATCH', 'CLIENT_TARGET', (('A', 'validate_client_target', 'd01845e8dceeaa21d81ca1aadb5a337e6a743a84cc425ed11210a0c9365fd33e'), ('C', 'run_tests', 'c54e67affff0519cef83945997ce04e0df8eddde6067b2ce39334a07e6dab163'))),
    ('A.OBS.IDLE', 'IDENTITY_CONNECTION_NOT_IDLE', (('A', 'observe', 'bc7703db92dd7adc3c9e66334891cb15f4f19f035d2fde2a09f6bb023e275106'), ('C', 'run_tests', '590b01776fc98b4201339ccd38f982ab6deb1170ec88bd984bcf82550c43bce0'))),
    ('A.OBS.ROW', 'IDENTITY_MISSING', (('A', 'observe', '4e6b34e7ad3fd895e9464f680d5b8bbff4bfced22d46c3ff0fc7978a8c2ffe0c'), ('C', 'run_tests', '590b01776fc98b4201339ccd38f982ab6deb1170ec88bd984bcf82550c43bce0'))),
    ('A.OBS.TX_END', 'IDENTITY_TRANSACTION_STATE', (('A', 'observe', 'e03656e463e4344977f26e27c614dcd88c6d8395081923d9c58b56ae4b1c8854'), ('C', 'run_tests', '590b01776fc98b4201339ccd38f982ab6deb1170ec88bd984bcf82550c43bce0'))),
    ('P.CONTAINER.SIZE', 'ADMISSION_SIZE', (('A', 'parse', '9e879d17b6bb6ecce8376c71815c39cbd51bd54d5e50a02d4a40e894ba4ba589'), ('C', 'service_admission', '0919edebdb8747ffc87cb489bfa1ddf5004863818aa051c12cd33b4cef998785'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.CONTAINER.DUPLICATE', 'ADMISSION_DUPLICATE_KEY', (('A', 'parse.<locals>.pairs', '6a94a3ee0f0923d97393de748791c68a7cefc16b758432eb18c478798dcba5f6'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', '0919edebdb8747ffc87cb489bfa1ddf5004863818aa051c12cd33b4cef998785'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.CONTAINER.NONFINITE', 'ADMISSION_NONFINITE', (('A', 'parse.<locals>.constant', 'fe00cc081878eff5d8e9bf88c7e30fb1bb3e362c2df46d24b667e23d20ad24f4'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', '0919edebdb8747ffc87cb489bfa1ddf5004863818aa051c12cd33b4cef998785'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.CONTAINER.JSON', 'ADMISSION_JSON', (('A', 'parse', '3f41418c7aa2b530cd1fdb13cb8c6093f69da2fc6059c990e731e6ea42344813'), ('C', 'service_admission', '0919edebdb8747ffc87cb489bfa1ddf5004863818aa051c12cd33b4cef998785'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.IMAGE.SIZE', 'ADMISSION_SIZE', (('A', 'parse', '9e879d17b6bb6ecce8376c71815c39cbd51bd54d5e50a02d4a40e894ba4ba589'), ('C', 'service_admission', 'cc2ea967cea58644aec88810218ba4aee052a798884eabf8323b0c6ee6590aad'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.IMAGE.DUPLICATE', 'ADMISSION_DUPLICATE_KEY', (('A', 'parse.<locals>.pairs', '6a94a3ee0f0923d97393de748791c68a7cefc16b758432eb18c478798dcba5f6'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', 'cc2ea967cea58644aec88810218ba4aee052a798884eabf8323b0c6ee6590aad'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.IMAGE.NONFINITE', 'ADMISSION_NONFINITE', (('A', 'parse.<locals>.constant', 'fe00cc081878eff5d8e9bf88c7e30fb1bb3e362c2df46d24b667e23d20ad24f4'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', 'cc2ea967cea58644aec88810218ba4aee052a798884eabf8323b0c6ee6590aad'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.IMAGE.JSON', 'ADMISSION_JSON', (('A', 'parse', '3f41418c7aa2b530cd1fdb13cb8c6093f69da2fc6059c990e731e6ea42344813'), ('C', 'service_admission', 'cc2ea967cea58644aec88810218ba4aee052a798884eabf8323b0c6ee6590aad'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.PSQL.SIZE', 'ADMISSION_SIZE', (('A', 'parse', '9e879d17b6bb6ecce8376c71815c39cbd51bd54d5e50a02d4a40e894ba4ba589'), ('C', 'service_admission', '7a8bd9ab002b546d6dac81b2ca01b80d5ef896cc0d97228669edcd6c13012609'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.PSQL.DUPLICATE', 'ADMISSION_DUPLICATE_KEY', (('A', 'parse.<locals>.pairs', '6a94a3ee0f0923d97393de748791c68a7cefc16b758432eb18c478798dcba5f6'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', '7a8bd9ab002b546d6dac81b2ca01b80d5ef896cc0d97228669edcd6c13012609'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.PSQL.NONFINITE', 'ADMISSION_NONFINITE', (('A', 'parse.<locals>.constant', 'fe00cc081878eff5d8e9bf88c7e30fb1bb3e362c2df46d24b667e23d20ad24f4'), ('A', 'parse', 'cd97788a4359e646afd0649face0855e41938cd3738aa3e8bbb6b2e07dec9710'), ('C', 'service_admission', '7a8bd9ab002b546d6dac81b2ca01b80d5ef896cc0d97228669edcd6c13012609'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
    ('P.PSQL.JSON', 'ADMISSION_JSON', (('A', 'parse', '3f41418c7aa2b530cd1fdb13cb8c6093f69da2fc6059c990e731e6ea42344813'), ('C', 'service_admission', '7a8bd9ab002b546d6dac81b2ca01b80d5ef896cc0d97228669edcd6c13012609'), ('C', 'run_tests', 'f86d192706a8864ca6a2c848452d0739825af851e55b12f4f7053094e3a9f297'))),
)


FIRST_ERROR_HELPER_CODES = tuple(('A', code) for f in (require, shape, parse, validate_service,
    validate_bindings, validate_identity, validate_client_target, observe) for code in
    (nested_codes(f.__code__) if f is parse else (f.__code__,)))


FIRST_ERROR_FUNCTION_HASHES = {
    ('A', 'require'): '2c87fcb719ea6926e19c5f0aa7181d237f4bc16a2cfca703c00c51a9771d0cb1',
    ('A', 'shape'): '591fccfd5ae5148362f020ebf2eea35be0cdd6c1200f70dc055d760a409fe319',
    ('A', 'parse'): '231ee7d9a47e3a56ded5945cef152759c6c3e14e7369b160fa0c3b9b5d7dd895',
    ('A', 'parse.<locals>.pairs'): '437d2af775ff146249c87aed7f4418d17a154eac1a1646251feb794007aa11d7',
    ('A', 'parse.<locals>.constant'): '210e79266c47524300ca4b784d1007959af5207ac570d57bc7dca28c43c2ce9c',
    ('A', 'validate_identity'): '2c3a00301efa0b2629ab3394879f16b4502fae06f8cb3a8813e565e7420f3be2',
    ('A', 'validate_client_target'): 'd5b5bb06e0e53e2cd9f4bf67d2253c8b396cd86b67c1f192c0856f2233b0d1eb',
    ('A', 'validate_bindings'): 'dd2de9537ecd9610270e5ba496c9535a33b7aaad86e1a06d38e6b2fee473c8c0',
    ('A', 'observe'): 'f862eb2ef3388f6fda78b8e5322257b1605a64cf491480b0e8ca931717c8c18d',
    ('A', 'validate_service'): '23f17491251d67675ac1b93cad00bb187dae59dba7b36b5d66c62eac92c73f63',
    ('C', 'require'): 'ba2fe4aedf7ede9bf717f2378bb6e7735b27a15ffd6793b6e1772a21374ecc22',
    ('C', 'service_admission'): 'a15aa87a1e120e452e01508535dbac176b7aa1c109d0ead4b669427a91dba12b',
    ('C', 'run_tests'): '900acffbda5f09811708e3b3d499eb6008534749177ceee31b3801f7b8b8d642',
}
