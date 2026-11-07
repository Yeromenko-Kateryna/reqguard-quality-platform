// Real locked pg.Client + real NODE_OPTIONS preload; transport/query seams prevent networking.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { sourceInputs, sourceDigest, serviceImage } from './ci-identity.mjs';
import { preloadSkip, requirePgPackage, requirePgResolution, requirePreloadObservation } from './ci-preload-checks.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const meta = path.join(here, 'node_modules/pg/package.json');
test('actual locked pg receives the NODE_OPTIONS preload before caller mutation', {
  skip: preloadSkip(meta, process.env.RG06D_REQUIRE_PG_PRELOAD_TEST === '1'),
}, () => {
  assert.equal(process.version, 'v24.15.0');
  requirePgPackage(meta);
  const resolved = import.meta.resolve('pg');
  requirePgResolution(meta, resolved);
  const run = randomUUID().replaceAll('-', '');
  const parent = path.join(here, '.artifacts');
  const createdParent = !fs.existsSync(parent);
  if (createdParent) fs.mkdirSync(parent);
  const artifact = path.join(parent, run);
  fs.mkdirSync(artifact);
  try {
    // Expectations are constructed independently before receipt serialization.
    const source = { checkout_sha: 'b'.repeat(40), pr_head_sha: null, pr_base_sha: null, tested_merge_sha: null,
      github_run_id: '123', github_run_attempt: '1', inputs: Object.fromEntries(sourceInputs.map(n => [n, 'a'.repeat(64)])),
      python_lock_sha256: 'a'.repeat(64), node_lock_sha256: 'a'.repeat(64) };
    const expectedSourceDigest = sourceDigest(source);
    const expectedContainer = 'e'.repeat(64), expectedNetwork = 'github_network_fixture', expectedPort = '49123';
    const fingerprint = { db: 'reqguard_rg06b', role: 'reqguard_rg06b', version: '170011', system_id: '1234567' };
    const service = { schema_version: 'rg06d-service-v3', run_id: run, source_identity: structuredClone(source),
      container_id: expectedContainer, engine_id: 'synthetic-engine', endpoint: 'unix:///var/run/docker.sock',
      image: serviceImage, image_id: 'sha256:' + 'e'.repeat(64), network_reference: expectedNetwork,
      network_name: expectedNetwork, network_id: 'f'.repeat(64), attachment_network_name: expectedNetwork,
      attachment_network_id: 'f'.repeat(64), host_port: expectedPort, fingerprint,
      service_observation: { ...fingerprint, address: '127.0.0.1', port: 5432, backend_pid: 99 },
      host_path: { address: '172.18.0.2', port: 5432 }, host_target: { host: '127.0.0.1', port: 49123 },
      published_bindings: [{ HostIp: '0.0.0.0', HostPort: expectedPort }] };
    fs.writeFileSync(path.join(artifact, 'service-identity.json'), JSON.stringify(service), { flag: 'wx' });
    const program = `
      import pg from 'pg'; import assert from 'node:assert/strict'; import fs from 'node:fs';
      import { identitySql } from './ci-identity.mjs';
      assert.equal(pg.Client.prototype.connect[Symbol.for('reqguard.ci.identity-hook')], true);
      let mutations = 0;
      function client(failure, matches = false) {
        const c = new pg.Client({host:'127.0.0.1',port:49123});
        assert.equal(typeof c._connect, 'function');
        c._connect = cb => queueMicrotask(() => cb(failure)); // Real connect(), no socket connect.
        c.end = async () => { c.testClosed = true; };
        c.query = async sql => {
          assert.equal(sql, identitySql);
          return {rows:[{db:'reqguard_rg06b',role:'reqguard_rg06b',version:'170011',system_id:matches?'1234567':'999',
            address:'172.18.0.2',port:5432,backend_pid:123}]};
        };
        return c;
      }
      const p = client();
      await assert.rejects(async () => { await p.connect(); mutations++; }, /IDENTITY_REJECTED/);
      assert.equal(p.testClosed,true);
      const c = client(); let callbacks=0;
      await new Promise(resolve => {
        assert.equal(c.connect(error => {
          callbacks++; assert.match(error.message,/IDENTITY_REJECTED/); resolve();
        }), undefined);
      });
      assert.equal(callbacks,1); assert.equal(c.testClosed,true);
      const failure = new Error('synthetic driver failure');
      await assert.rejects(client(failure).connect(), error => error === failure);
      await client(undefined, true).connect(); // Positive handshake, no socket or caller SQL.
      assert.equal(mutations,0);
      console.log(JSON.stringify({node:process.version,pg:JSON.parse(fs.readFileSync('./node_modules/pg/package.json')).version,
        resolved:import.meta.resolve('pg'),patched:true,mutations,callbackCount:callbacks}));
    `;
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', program], {
      cwd: here, encoding: 'utf8', timeout: 10000,
      env: { ...process.env, NODE_OPTIONS: '--import=' + pathToFileURL(path.join(here, 'ci-identity.mjs')).href,
        RG06D_NODE_IDENTITY: '1', RG06B_RUN_ID: run, RG06B_ARTIFACT: artifact,
        GITHUB_RUN_ID: source.github_run_id, GITHUB_RUN_ATTEMPT: source.github_run_attempt, GITHUB_SHA: source.checkout_sha,
        RG06D_EXPECTED_SOURCE_IDENTITY_SHA256: expectedSourceDigest, RG06D_SERVICE_ID: expectedContainer,
        RG06D_SERVICE_NETWORK: expectedNetwork, RG06B_DB_PORT: expectedPort },
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stderr);
    const observed = JSON.parse(result.stdout);
    requirePreloadObservation(observed, resolved);
    console.log(result.stdout.trim());
  } finally {
    // Delete only the exact random directory this test created, never prior artifacts.
    assert.equal(path.dirname(path.resolve(artifact)), path.resolve(parent));
    assert.match(path.basename(artifact), /^[a-f0-9]{32}$/);
    fs.rmSync(artifact, { recursive: true });
    if (createdParent) fs.rmdirSync(parent);
  }
});
