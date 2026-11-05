// Test-process-only preload. Importing for deterministic tests needs no pg package.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
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

if (process.env.RG06D_NODE_IDENTITY === '1') {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const run = process.env.RG06B_RUN_ID;
  assert.match(run ?? '', /^[a-f0-9]{32}$/);
  const artifact = path.join(here, '.artifacts', run);
  assert.equal(process.env.RG06B_ARTIFACT, artifact);
  const service = JSON.parse(fs.readFileSync(path.join(artifact, 'service-identity.json'), 'utf8'));
  assert.equal(service.schema_version, 'rg06d-service-v2'); assert.equal(service.run_id, run);
  const expected = service.fingerprint;
  assert.notEqual(service.host_path.address, '127.0.0.1');
  const { default: pg } = await import('pg');
  installIdentityHook(pg.Client, expected, identity => {
    const receipt_id = randomUUID().replaceAll('-', '');
    fs.writeFileSync(path.join(artifact, 'connection-' + receipt_id + '.json'),
      JSON.stringify({ receipt_id, kind: 'verifier', identity }) + '\n', { flag: 'wx' });
  }, service.host_path, service.host_target);
}
