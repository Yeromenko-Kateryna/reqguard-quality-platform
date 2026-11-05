"""Test-only RG-06D identity/evidence admission. No import-time I/O or driver imports."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat


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


def validate_service(container, image, service_id, network, host_port):
    require(type(service_id) is str and re.fullmatch('[a-f0-9]{64}', service_id), 'SERVICE_ID')
    require(container['Id'] == service_id and container['Image'] == image['Id'], 'SERVICE_IDENTITY')
    require(container['State']['Running'] is True and container['State']['Health']['Status'] == 'healthy', 'SERVICE_HEALTH')
    require(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'SERVICE_ARCH')
    require(container['NetworkSettings']['Networks'] and
            {v['NetworkID'] for v in container['NetworkSettings']['Networks'].values()} == {network}, 'SERVICE_NETWORK')
    require(set(container['NetworkSettings']['Ports']) == {'5432/tcp'}, 'SERVICE_EXPOSED_PORTS')
    validate_bindings(container['NetworkSettings']['Ports']['5432/tcp'], host_port)
    require(len(container['NetworkSettings']['Networks']) == 1, 'SERVICE_NETWORK')
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


def api_main():
    # Used only as the child-process entrypoint of the Linux test harness.
    import sys
    import uuid
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    path = Path(os.environ['RG06B_ARTIFACT'])
    require(path == root / 'quality/browser/.artifacts' / os.environ['RG06B_RUN_ID'], 'API_ARTIFACT_BOUNDARY')
    service = parse(read(path, 'service-identity.json'))
    require(service['schema_version'] == 'rg06d-service-v2' and service['run_id'] == path.name, 'API_SERVICE_RECEIPT')
    expected = service['fingerprint']
    import psycopg
    import uvicorn
    def emit(identity):
        receipt_id = uuid.uuid4().hex
        write(path, 'connection-' + receipt_id + '.json', {'receipt_id': receipt_id, 'kind': 'api', 'identity': identity})
    psycopg.connect = guarded_connect(psycopg.connect, expected, emit, service['host_path'], service['host_target'])
    uvicorn.run('reqguard.main:app', host='127.0.0.1', port=int(os.environ['RG06B_API_PORT']), workers=1)


if __name__ == '__main__':
    api_main()
