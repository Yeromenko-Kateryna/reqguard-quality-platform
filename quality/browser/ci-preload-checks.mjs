// Narrow R03 assertions shared by the real test and dependency-free negative tests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function preloadSkip(meta, required) {
  return !required && !fs.existsSync(meta)
    ? 'NOT_RUN_DEPENDENCY_UNAVAILABLE: quality/browser/node_modules/pg/package.json' : false;
}

export function requirePgPackage(meta) {
  assert.ok(fs.existsSync(meta), 'R03_REQUIRED_PG_MISSING');
  assert.equal(JSON.parse(fs.readFileSync(meta, 'utf8')).version, '8.23.1', 'R03_PG_VERSION');
}

export function requirePgResolution(meta, resolved) {
  const packageRoot = path.resolve(path.dirname(meta));
  assert.equal(fs.realpathSync(packageRoot), packageRoot, 'R03_PG_LAYOUT');
  const relative = path.relative(packageRoot, fs.realpathSync(fileURLToPath(resolved)));
  assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'R03_PG_RESOLUTION');
}

export function requirePreloadObservation(value, resolved) {
  assert.deepEqual(Object.keys(value).sort(), ['callbackCount', 'mutations', 'node', 'patched', 'pg', 'resolved']);
  assert.equal(value.node, 'v24.15.0'); assert.equal(value.pg, '8.23.1');
  assert.equal(value.resolved, resolved);
  assert.equal(value.patched, true, 'R03_PRELOAD_MISSING');
  assert.equal(value.mutations, 0, 'R03_MUTATION_NOT_BLOCKED');
  assert.equal(value.callbackCount, 1);
}
