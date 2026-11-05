// Dependency-free R03 admission tests, not evidence of real pg preload execution.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { preloadSkip, requirePgPackage, requirePgResolution, requirePreloadObservation } from './ci-preload-checks.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
test('missing dependency skips locally but is not skippable in explicit required mode', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'rg06d-preload-'));
  try {
    const meta = path.join(temp, 'package.json');
    assert.match(preloadSkip(meta, false), /NOT_RUN_DEPENDENCY_UNAVAILABLE/);
    assert.equal(preloadSkip(meta, true), false);
    assert.throws(() => requirePgPackage(meta), /R03_REQUIRED_PG_MISSING/);
  } finally { fs.rmSync(temp, { recursive: true }); }
});

test('incorrect installed version and package resolution outside expected layout are rejected', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'rg06d-preload-'));
  try {
    const pkg = path.join(temp, 'pg'); fs.mkdirSync(pkg);
    const meta = path.join(pkg, 'package.json');
    fs.writeFileSync(meta, JSON.stringify({ version: '8.23.0' }));
    assert.throws(() => requirePgPackage(meta), /R03_PG_VERSION/);
    fs.writeFileSync(meta, JSON.stringify({ version: '8.23.1' }));
    requirePgPackage(meta);
    const entry = path.join(pkg, 'entry.mjs'); fs.writeFileSync(entry, '');
    requirePgResolution(meta, pathToFileURL(entry).href);
    const other = path.join(temp, 'other.mjs'); fs.writeFileSync(other, '');
    assert.throws(() => requirePgResolution(meta, pathToFileURL(other).href), /R03_PG_RESOLUTION/);
  } finally { fs.rmSync(temp, { recursive: true }); }
});

test('missing or wrong preload, package version and mutation evidence cannot pass', () => {
  const resolved = 'file:///synthetic/node_modules/pg/index.js';
  const good = { node: 'v24.15.0', pg: '8.23.1', resolved, patched: true, mutations: 0, callbackCount: 1 };
  requirePreloadObservation(good, resolved);
  for (const change of [{ patched: false }, { patched: undefined }, { mutations: 1 },
    { pg: '8.23.0' }, { resolved: 'file:///other/pg.js' }, { callbackCount: 0 }]) {
    assert.throws(() => requirePreloadObservation({ ...good, ...change }, resolved));
  }
});

test('actual test runner fails rather than skipping when required pg is missing', {
  skip: fs.existsSync(path.join(here, 'node_modules/pg/package.json')) && 'Missing-package negative is covered by isolated fixture when pg is installed',
}, () => {
  // This is a new runner, not a worker of the enclosing node:test invocation.
  const env = { ...process.env, RG06D_REQUIRE_PG_PRELOAD_TEST: '1' };
  delete env.NODE_TEST_CONTEXT;
  const result = spawnSync(process.execPath, ['--test', '--test-reporter',
    pathToFileURL(path.join(here, 'unit-reporter.mjs')).href,
    path.join(here, 'ci-preload.integration.test.mjs')], {
    cwd: here, encoding: 'utf8', timeout: 10000,
    env,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  const report = JSON.parse(result.stdout);
  assert.equal(report.cases.length, 1);
  assert.equal(report.cases[0].name, 'actual locked pg receives the NODE_OPTIONS preload before caller mutation');
  assert.equal(report.cases[0].skip, false);
  assert.equal(report.cases[0].passed, false);
  assert.equal(report.summary.failed, 1);
});
