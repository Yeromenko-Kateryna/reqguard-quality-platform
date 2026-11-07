import { test } from 'node:test';
import assert from 'node:assert/strict';
import { installIdentityHook as install, identitySql, verifyIdentity } from './ci-identity.mjs';

const expected = { db: 'reqguard_rg06b', role: 'reqguard_rg06b', version: '170011',
  system_id: '1234567' };
const serverPath = { address: '172.18.0.2', port: 5432 };
const target = { host: '127.0.0.1', port: 49123 };
const installIdentityHook = (Client, expected, emit) => install(Client, expected, emit, serverPath, target);
function driver(row = { ...expected, ...serverPath, backend_pid: 123 }, failure) {
  return class Client {
    calls = []; closed = false;
    connectionParameters = { ...target };
    connect(callback) {
      this.calls.push('connect');
      if (callback) { queueMicrotask(() => callback(failure)); return undefined; }
      return failure ? Promise.reject(failure) : Promise.resolve(undefined);
    }
    async query(sql) { this.calls.push(sql); return { rows: [row] }; }
    async end() { this.closed = true; }
  };
}

test('promise connection admission precedes caller INSERT on every physical client', async () => {
  const Client = driver(); let receipts = 0;
  const restore = installIdentityHook(Client, expected, () => { receipts++; });
  for (let i = 0; i < 2; i++) {
    const client = new Client();
    assert.equal(await client.connect(), undefined);
    await client.query('INSERT synthetic');
    assert.deepEqual(client.calls, ['connect', identitySql, 'INSERT synthetic']);
    assert.equal(client.closed, false);
  }
  assert.equal(receipts, 2); restore();
});

test('callback connection preserves return and delays caller until admission', async () => {
  const Client = driver(); installIdentityHook(Client, expected, () => {});
  const client = new Client();
  await new Promise((resolve, reject) => {
    const result = client.connect(error => error ? reject(error) : resolve());
    assert.equal(result, undefined);
  });
  assert.deepEqual(client.calls, ['connect', identitySql]);
});

test('backend mismatch closes connection and prevents caller mutation', async () => {
  const Client = driver({ ...expected, ...serverPath, system_id: '999', backend_pid: 123 });
  installIdentityHook(Client, expected, () => assert.fail('No successful receipt'));
  const client = new Client();
  await assert.rejects(async () => { await client.connect(); await client.query('INSERT forbidden'); }, /IDENTITY_REJECTED/);
  assert.equal(client.closed, true);
  assert.deepEqual(client.calls, ['connect', identitySql]);
});

test('missing identity and receipt-write failure both prevent connection handoff', async () => {
  for (const row of [null, { ...expected, ...serverPath, backend_pid: 123 }]) {
    const Client = driver(row); installIdentityHook(Client, expected, () => { throw new Error('DISK_FAILURE'); });
    const client = new Client();
    await assert.rejects(client.connect(), /IDENTITY_REJECTED/);
    assert.equal(client.closed, true);
  }
});

test('original driver failure propagates without identity SQL or fallback', async () => {
  const failure = new Error('synthetic connect failure');
  const Client = driver(undefined, failure); installIdentityHook(Client, expected, () => {});
  const client = new Client();
  await assert.rejects(client.connect(), error => error === failure);
  assert.deepEqual(client.calls, ['connect']);
});

test('callback mismatch reports failure once before mutation', async () => {
  const Client = driver({ ...expected, ...serverPath, port: 5555, backend_pid: 123 });
  installIdentityHook(Client, expected, () => {});
  const client = new Client(); let callbacks = 0;
  await new Promise(resolve => client.connect(error => {
    callbacks++; assert.match(error.message, /IDENTITY_REJECTED/); resolve();
  }));
  assert.equal(callbacks, 1); assert.equal(client.closed, true);
});

test('same cluster through separately admitted paths does not require equal addresses or PIDs', () => {
  verifyIdentity({ ...expected, ...serverPath, backend_pid: 10 }, expected, serverPath);
  const local = { address: '127.0.0.1', port: 5432 };
  verifyIdentity({ ...expected, ...local, backend_pid: 20 }, expected, local);
  assert.throws(() => verifyIdentity({ ...expected, ...local, backend_pid: 20 }, expected, serverPath));
});

test('wrong cluster principal version and unsupported client target fail before mutation', async () => {
  for (const change of [{ system_id: '999' }, { db: 'other' }, { role: 'other' },
    { version: '170012' }, { system_id: undefined }, { address: '192.0.2.1' }]) {
    const Client = driver({ ...expected, ...serverPath, backend_pid: 123, ...change });
    installIdentityHook(Client, expected, () => assert.fail());
    const client = new Client();
    await assert.rejects(client.connect(), /IDENTITY_REJECTED/);
    assert.equal(client.closed, true);
  }
  const Client = driver(); installIdentityHook(Client, expected, () => assert.fail());
  const client = new Client(); client.connectionParameters.host = '192.0.2.2';
  await assert.rejects(client.connect(), /IDENTITY_REJECTED/);
  assert.deepEqual(client.calls, ['connect']);
});

test('failed identity query closes the actual admitted client without INSERT handoff', async () => {
  const Client = driver(); installIdentityHook(Client, expected, () => assert.fail());
  const client = new Client();
  client.query = async () => { throw new Error('synthetic permission denied'); };
  await assert.rejects(client.connect(), /IDENTITY_REJECTED/);
  assert.equal(client.closed, true);
});
