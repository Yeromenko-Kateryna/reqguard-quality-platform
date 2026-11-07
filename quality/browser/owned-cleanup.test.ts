import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createOwnedCleanup, OwnershipRejected, type AnalysisRow, type Query } from './owned-cleanup.ts';

const run = 'a'.repeat(32);
const row: AnalysisRow = {
  run_id: '00000001-0000-4000-8000-000000000001',
  provider: 'fake', status: 'unsupported_fixture',
  original_input: '  synthetic foreign fixture  ', analysis_payload: null,
  created_at: '2026-01-01 00:00:00+00', sql_null: true,
};
const evidence = () => ({ run, operation: 'supported-http' as const, before: [], after: [structuredClone(row)] });

test('unowned existing UUID is rejected before the actual SQL execution boundary', async () => {
  let calls = 0, deletes = 0, uncertain = false;
  const query: Query = async text => {
    calls++;
    if (/\bDELETE\b/i.test(text)) { deletes++; throw new Error('DELETE_REACHED_SQL_BOUNDARY'); }
    return { rows: [structuredClone(row)], rowCount: 1 };
  };
  const active = createOwnedCleanup(run, query, () => { uncertain = true; }, async () => {});
  await assert.rejects(active.removeOwned(structuredClone(row), []), OwnershipRejected);
  assert.equal(deletes, 0, 'Any DELETE submission must fail this regression');
  assert.equal(calls, 0, 'No SQL, including BEGIN, is permitted for an unowned request');
  assert.equal(uncertain, false, 'A pre-dispatch refusal is not an uncertain SQL outcome');
});

test('verified creation evidence permits exactly one positive cleanup', async () => {
  let deletes = 0, commits = 0, reads = 0;
  const query: Query = async text => {
    if (text === 'BEGIN') return { rows: [], rowCount: null };
    if (text.endsWith('FOR UPDATE')) return { rows: [structuredClone(row)], rowCount: 1 };
    if (text.startsWith('DELETE')) { deletes++; return { rows: [{ run_id: row.run_id }], rowCount: 1 }; }
    if (text === 'COMMIT') { commits++; return { rows: [], rowCount: null }; }
    if (text.startsWith('SELECT')) { reads++; return { rows: [], rowCount: 0 }; }
    throw new Error('UNEXPECTED_SQL');
  };
  const owner = createOwnedCleanup(run, query, () => assert.fail('Unexpected uncertain outcome'), async () => {});
  owner.registerCreated(row, evidence());
  await owner.removeOwned(structuredClone(row), []);
  assert.equal(deletes, 1); assert.equal(commits, 1); assert.equal(reads, 2);
  await assert.rejects(owner.removeOwned(row, []), OwnershipRejected);
  assert.equal(deletes, 1);
});

test('wrong-run, preexisting-row and changed-row evidence do not confer cleanup authority', async () => {
  let calls = 0;
  const owner = createOwnedCleanup(run, async () => { calls++; throw new Error('SQL_NOT_ALLOWED'); }, () => {}, async () => {});
  assert.throws(() => owner.registerCreated(row, { ...evidence(), run: 'b'.repeat(32) }));
  assert.throws(() => owner.registerCreated(row, { ...evidence(), before: [row], after: [row] }));
  await assert.rejects(owner.removeOwned(row, []), OwnershipRejected);
  owner.registerCreated(row, evidence());
  await assert.rejects(owner.removeOwned({ ...row, original_input: 'different input' }, []), OwnershipRejected);
  assert.equal(calls, 0);
});

test('ambiguous COMMIT blocks every further cleanup without destructive retry', async () => {
  let deletes = 0, commits = 0, rollbacks = 0, uncertain = false;
  const query: Query = async text => {
    if (text.endsWith('FOR UPDATE')) return { rows: [structuredClone(row)], rowCount: 1 };
    if (text.startsWith('DELETE')) { deletes++; return { rows: [{ run_id: row.run_id }], rowCount: 1 }; }
    if (text === 'COMMIT') { commits++; throw new Error('SYNTHETIC_COMMIT_ACK_LOST'); }
    return { rows: [], rowCount: 0 };
  };
  const owner = createOwnedCleanup(run, query, () => { uncertain = true; }, async () => { rollbacks++; });
  owner.registerCreated(row, evidence());
  await assert.rejects(owner.removeOwned(row, []), /SYNTHETIC_COMMIT_ACK_LOST/);
  await assert.rejects(owner.removeOwned(row, []), /RG06B_CLEANUP_OUTCOME_UNCERTAIN/);
  assert.equal(deletes, 1); assert.equal(commits, 1); assert.equal(rollbacks, 1);
  assert.equal(uncertain, true);
});
