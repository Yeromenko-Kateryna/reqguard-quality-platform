// Test-process-only preload. Importing for deterministic tests needs no pg package.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { isIP } from 'node:net';

export const identitySql = `SELECT current_database()::text AS db, current_user::text AS role,
 current_setting('server_version_num') AS version,
 (SELECT system_identifier::text FROM pg_control_system()) AS system_id,
 inet_server_addr()::text AS address, inet_server_port() AS port,
 pg_backend_pid() AS backend_pid`;

export function verifyIdentity(observed, expected, serverPath) {
  assert.deepEqual(Object.keys(expected).sort(), ['db', 'role', 'system_id', 'version']);
  assert.deepEqual(Object.keys(observed).sort(), [...Object.keys(expected), 'address', 'port', 'backend_pid'].sort());
  const { backend_pid, address, port, ...fingerprint } = observed;
  assert.deepEqual(fingerprint, expected, 'RG06D_BACKEND_IDENTITY_MISMATCH');
  assert.deepEqual(Object.keys(serverPath).sort(), ['address', 'port']);
  assert.equal(isIP(serverPath.address), 4); assert.notEqual(serverPath.address, '0.0.0.0');
  assert.equal(address, serverPath.address);
  assert.equal(port, 5432); assert.equal(serverPath.port, 5432);
  assert.equal(typeof expected.system_id, 'string'); assert.match(expected.system_id, /^[1-9][0-9]*$/);
  assert.equal(expected.db, 'reqguard_rg06b'); assert.equal(expected.role, 'reqguard_rg06b');
  assert.equal(expected.version, '170011');
  assert.ok(Number.isInteger(backend_pid) && backend_pid > 0);
}

export function installIdentityHook(Client, expected, emit, serverPath, target) {
  const original = Client.prototype.connect;
  async function admit(client) {
    try {
      assert.deepEqual(Object.keys(target).sort(), ['host', 'port']);
      assert.equal(target.host, '127.0.0.1');
      assert.ok(Number.isInteger(target.port) && target.port >= 1024 && target.port <= 65535);
      assert.equal(client.connectionParameters.host, target.host);
      assert.equal(client.connectionParameters.port, target.port);
      // New pg clients execute this SELECT in autocommit: no BEGIN or open transaction.
      const result = await client.query(identitySql);
      assert.equal(result.rows.length, 1);
      verifyIdentity(result.rows[0], expected, serverPath);
      emit(result.rows[0]);
    } catch {
      try { await client.end(); } catch { /* Do not hide admission failure. */ }
      throw new Error('RG06D_NODE_IDENTITY_REJECTED');
    }
  }
  Client.prototype.connect = function (callback) {
    if (typeof callback === 'function') {
      return original.call(this, error => {
        if (error) { callback(error); return; }
        admit(this).then(() => callback(null), callback);
      });
    }
    return original.call(this).then(async value => { await admit(this); return value; });
  };
  Object.defineProperty(Client.prototype.connect, Symbol.for('reqguard.ci.identity-hook'), { value: true });
  return () => { Client.prototype.connect = original; };
}


export const sourceInputs = Object.freeze(["pyproject.toml", "uv.lock", "db/001_init.sql", "reqguard/main.py", "reqguard/persistence.py", "reqguard/static/index.html", "reqguard/static/app.mjs", "reqguard/static/style.css", "quality/browser/package.json", "quality/browser/package-lock.json", "quality/browser/analyses.spec.ts", "quality/browser/playwright.config.ts", "quality/browser/playwright.ci.config.ts", "scripts/run_rg06d_ci.py", ".github/workflows/rg06d-e2e.yml", "quality/browser/owned-cleanup.ts", "quality/browser/owned-cleanup.test.ts", "quality/browser/ci-identity.mjs", "quality/browser/unit-reporter.mjs", "scripts/rg06d_admission.py", "scripts/test_rg06d_admission.py", "quality/browser/ci-identity.test.mjs", "quality/browser/ci-preload.integration.test.mjs", "quality/browser/ci-preload-checks.mjs", "quality/browser/ci-preload-gate.test.mjs"]);
export const serviceImage = 'postgres:17.11-bookworm@sha256:ec4dfc6571f04fe0731ce948c1500d676af49a7224392dcc6995cc1ee33a94bb';

const rejectReceipt = () => { throw new Error('RG06D_NODE_RECEIPT_REJECTED'); };
const need = value => { if (!value) rejectReceipt(); };
const object = value => value !== null && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype;
const shape = (value, keys) => {
  need(object(value)); const actual = Object.keys(value).sort(), expected = [...keys].sort();
  need(actual.length === expected.length && actual.every((key, i) => key === expected[i]));
};
const match = (pattern, value) => typeof value === 'string' && pattern.exec(value)?.[0] === value;
const sha40 = value => match(/^[a-f0-9]{40}$/, value);
const sha64 = value => match(/^[a-f0-9]{64}$/, value);
export const sourceKeys = Object.freeze(['checkout_sha', 'pr_head_sha', 'pr_base_sha', 'tested_merge_sha',
  'github_run_id', 'github_run_attempt', 'inputs', 'python_lock_sha256', 'node_lock_sha256']);
export const serviceKeys = Object.freeze(['schema_version', 'run_id', 'source_identity', 'container_id', 'engine_id',
  'endpoint', 'image', 'image_id', 'network_reference', 'network_name', 'network_id', 'attachment_network_name',
  'attachment_network_id', 'host_port', 'fingerprint', 'service_observation', 'host_path', 'host_target', 'published_bindings']);
export const childExpectations = Object.freeze(['RG06B_RUN_ID', 'RG06B_ARTIFACT', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
  'GITHUB_SHA', 'RG06D_EXPECTED_SOURCE_IDENTITY_SHA256', 'RG06D_SERVICE_ID', 'RG06D_SERVICE_NETWORK', 'RG06B_DB_PORT']);

export function classifyNetworkReference(value) {
  if (typeof value !== 'string') return 'REJECT';
  if (match(/^[a-f0-9]{64}$/, value)) return 'ID';
  if (match(/^[a-f0-9]+$/, value)) return 'REJECT';
  if (match(/^[a-z][a-z0-9_.-]{0,127}$/, value)) return 'NAME';
  return 'REJECT';
}

export function parseReceiptJson(raw) {
  need(Buffer.isBuffer(raw) && raw.length > 0 && raw.length <= 65536);
  const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw);
  need(!text.startsWith('\uFEFF'));
  let i = 0, tokens = 0;
  const token = () => { need(++tokens <= 8192); };
  const ws = () => { while (i < text.length && /[ \t\r\n]/.test(text[i])) i++; };
  function string() {
    token(); need(text[i] === '"'); const start = i++;
    while (i < text.length) {
      const ch = text[i++];
      if (ch === '"') {
        const result = JSON.parse(text.slice(start, i)); // One scanned string token only.
        for (let n = 0; n < result.length; n++) {
          const c = result.charCodeAt(n);
          if (c >= 0xd800 && c <= 0xdbff) {
            const next = result.charCodeAt(++n); need(next >= 0xdc00 && next <= 0xdfff);
          } else need(!(c >= 0xdc00 && c <= 0xdfff));
        }
        return result;
      }
      need(ch.charCodeAt(0) >= 0x20);
      if (ch === '\\') {
        need(i < text.length); const esc = text[i++];
        if (esc === 'u') { need(/^[a-fA-F0-9]{4}$/.test(text.slice(i, i + 4))); i += 4; }
        else need('"\\/bfnrt'.includes(esc));
      }
    }
    rejectReceipt();
  }
  function value(depth) {
    ws(); const ch = text[i];
    if (ch === '"') return string();
    if (ch === '{' || ch === '[') {
      need(depth < 32); token(); i++;
      const isObject = ch === '{', result = isObject ? {} : [], keys = new Set();
      const end = isObject ? '}' : ']'; ws();
      if (text[i] === end) { token(); i++; return result; }
      while (i < text.length) {
        if (isObject) {
          ws(); const key = string(); need(!keys.has(key)); keys.add(key); ws();
          need(text[i++] === ':'); token();
          // Own-key definition handles __proto__ without invoking any prototype setter.
          Object.defineProperty(result, key, { value: value(depth + 1), enumerable: true, writable: true, configurable: true });
        } else result.push(value(depth + 1));
        ws(); token();
        if (text[i] === end) { i++; return result; }
        need(text[i++] === ','); ws();
      }
      rejectReceipt();
    }
    for (const [word, result] of [['true', true], ['false', false], ['null', null]]) {
      if (text.startsWith(word, i)) { token(); i += word.length; return result; }
    }
    const number = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(text.slice(i));
    need(number); token(); i += number[0].length; const result = Number(number[0]); need(Number.isFinite(result)); return result;
  }
  const result = value(0); ws(); need(i === text.length); return result;
}

export function canonicalSource(source) {
  shape(source, sourceKeys); need(sha40(source.checkout_sha));
  for (const key of ['pr_head_sha', 'pr_base_sha', 'tested_merge_sha']) need(source[key] === null || sha40(source[key]));
  need((source.pr_head_sha === null) === (source.pr_base_sha === null));
  if (source.tested_merge_sha !== null) need(source.tested_merge_sha === source.checkout_sha && source.pr_head_sha !== null && source.pr_base_sha !== null);
  need(match(/^[1-9][0-9]*$/, source.github_run_id) && match(/^[1-9][0-9]*$/, source.github_run_attempt));
  shape(source.inputs, sourceInputs); need(Object.values(source.inputs).every(sha64));
  need(source.python_lock_sha256 === source.inputs['uv.lock'] && source.node_lock_sha256 === source.inputs['quality/browser/package-lock.json']);
  function stable(value) {
    if (value === null) return 'null';
    if (typeof value === 'string') { need(match(/^[\x20-\x7e]*$/, value)); return JSON.stringify(value); }
    need(object(value));
    return '{' + Object.keys(value).sort().map(k => {
      need(match(/^[\x20-\x7e]*$/, k)); return JSON.stringify(k) + ':' + stable(value[k]);
    }).join(',') + '}';
  }
  return Buffer.from(stable(source), 'ascii');
}
export const sourceDigest = source => createHash('sha256').update(canonicalSource(source)).digest('hex');

export function validateChildEnvironment(env) {
  need(childExpectations.every(k => typeof env[k] === 'string' && env[k].length > 0));
  need(match(/^[a-f0-9]{32}$/, env.RG06B_RUN_ID) && sha40(env.GITHUB_SHA) && sha64(env.RG06D_SERVICE_ID)
    && sha64(env.RG06D_EXPECTED_SOURCE_IDENTITY_SHA256));
  need(match(/^[1-9][0-9]*$/, env.GITHUB_RUN_ID) && match(/^[1-9][0-9]*$/, env.GITHUB_RUN_ATTEMPT)
    && classifyNetworkReference(env.RG06D_SERVICE_NETWORK) !== 'REJECT'
    && match(/^[0-9]+$/, env.RG06B_DB_PORT) && Number(env.RG06B_DB_PORT) >= 1024 && Number(env.RG06B_DB_PORT) <= 65535);
}
export function validateServiceReceipt(service, env) {
  validateChildEnvironment(env); shape(service, serviceKeys);
  need(service.schema_version === 'rg06d-service-v3' && service.run_id === env.RG06B_RUN_ID);
  need(sourceDigest(service.source_identity) === env.RG06D_EXPECTED_SOURCE_IDENTITY_SHA256);
  const source = service.source_identity;
  need(source.checkout_sha === env.GITHUB_SHA && source.github_run_id === env.GITHUB_RUN_ID && source.github_run_attempt === env.GITHUB_RUN_ATTEMPT);
  for (const key of ['container_id', 'engine_id', 'endpoint', 'image', 'image_id', 'network_reference', 'network_name', 'network_id', 'attachment_network_name', 'attachment_network_id', 'host_port']) {
    need(typeof service[key] === 'string' && service[key].length > 0 && service[key].length <= 512);
  }
  need(service.container_id === env.RG06D_SERVICE_ID && sha64(service.container_id) && service.host_port === env.RG06B_DB_PORT
    && service.image === serviceImage && service.endpoint === 'unix:///var/run/docker.sock' && match(/^sha256:[a-f0-9]{64}$/, service.image_id));
  const kind = classifyNetworkReference(env.RG06D_SERVICE_NETWORK);
  need(service.network_reference === env.RG06D_SERVICE_NETWORK && classifyNetworkReference(service.network_reference) === kind);
  need(classifyNetworkReference(service.network_name) === 'NAME' && classifyNetworkReference(service.attachment_network_name) === 'NAME'
    && classifyNetworkReference(service.network_id) === 'ID' && classifyNetworkReference(service.attachment_network_id) === 'ID');
  need(service.network_name === service.attachment_network_name && service.network_id === service.attachment_network_id);
  need(kind === 'NAME' ? service.network_name === service.network_reference : service.network_id === service.network_reference);
  verifyIdentity(service.service_observation, service.fingerprint, { address: '127.0.0.1', port: 5432 });
  shape(service.host_path, ['address', 'port']); shape(service.host_target, ['host', 'port']);
  need(isIP(service.host_path.address) === 4 && !service.host_path.address.startsWith('127.') && service.host_path.address !== '0.0.0.0'
    && service.host_path.port === 5432 && service.host_target.host === '127.0.0.1'
    && Number.isSafeInteger(service.host_target.port) && service.host_target.port === Number(service.host_port));
  need(Array.isArray(service.published_bindings) && service.published_bindings.length >= 1 && service.published_bindings.length <= 2);
  const ips = service.published_bindings.map(binding => {
    shape(binding, ['HostIp', 'HostPort']); need(binding.HostPort === service.host_port && typeof binding.HostIp === 'string'); return binding.HostIp;
  }).sort();
  need(JSON.stringify(ips) === '["0.0.0.0"]' || JSON.stringify(ips) === '["0.0.0.0","::"]');
  return service;
}

function regularDirectory(directory) {
  for (let current = directory;; current = path.dirname(current)) {
    const info = fs.lstatSync(current); need(info.isDirectory() && !info.isSymbolicLink());
    if (path.dirname(current) === current) break;
  }
}
export function readChildService(env) {
  validateChildEnvironment(env);
  const here = path.dirname(fileURLToPath(import.meta.url));
  const expected = path.join(here, '.artifacts', env.RG06B_RUN_ID);
  need(env.RG06B_ARTIFACT === expected); regularDirectory(expected);
  const filename = path.join(expected, 'service-identity.json'), before = fs.lstatSync(filename);
  need(before.isFile() && !before.isSymbolicLink() && before.size > 0 && before.size <= 65536);
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
  let raw;
  try {
    const opened = fs.fstatSync(fd); need(opened.dev === before.dev && opened.ino === before.ino);
    const buffer = Buffer.alloc(65537); let count = 0, size;
    while (count < buffer.length && (size = fs.readSync(fd, buffer, count, buffer.length - count, null)) > 0) count += size;
    const after = fs.fstatSync(fd), current = fs.lstatSync(filename);
    need(count > 0 && count <= 65536 && after.size === count && before.size === count && after.mtimeMs === before.mtimeMs
      && current.dev === before.dev && current.ino === before.ino && !current.isSymbolicLink());
    raw = buffer.subarray(0, count);
  } finally { fs.closeSync(fd); }
  return validateServiceReceipt(parseReceiptJson(raw), env);
}

if (process.env.RG06D_NODE_IDENTITY === '1') {
  try {
    const service = readChildService(process.env);
    const { default: pg } = await import('pg');
    installIdentityHook(pg.Client, service.fingerprint, identity => {
      const receipt_id = randomUUID().replaceAll('-', '');
      fs.writeFileSync(path.join(process.env.RG06B_ARTIFACT, 'connection-' + receipt_id + '.json'),
        JSON.stringify({ receipt_id, kind: 'verifier', identity }) + '\n', { flag: 'wx' });
    }, service.host_path, service.host_target);
  } catch {
    process.stderr.write('RG06D_NODE_RECEIPT_REJECTED\n');
    process.exit(1);
  }
}
