import { test, expect } from '@playwright/test';
import pg from 'pg';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

test.describe.configure({ mode: 'serial' });
const fixture = 'The user can quickly reset their password';
const artifact = process.env.RG06B_ARTIFACT!;
const run = process.env.RG06B_RUN_ID!;
const uuid4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const fields = 'run_id::text, provider, status, original_input, analysis_payload, created_at::text, analysis_payload IS NULL AS sql_null';
const analysis = {
  ambiguities: [{ term: 'quickly', explanation: "The word 'quickly' does not specify a measurable duration." }],
  missing_measurable_criteria: ['Define the maximum allowed password-reset duration and its start/end events.'],
  candidate_test_scenarios: [{ title: 'Reset a password within the agreed time limit', steps: [
    'Start a password reset for a synthetic user and record the start time.',
    'Complete the reset using a valid reset link and record the end time.',
    'Compare elapsed time with the agreed maximum duration.',
  ], expected_result: 'The password is reset within the agreed limit; the limit must first be specified.' }],
};
let client: pg.Client | undefined;
let baseline: any[] = [];
let sentinel: any;
let owned: any;
let uncertain = true;
let inFlight = false;
let supportedCleaned = false;
let invalidVerified = false;

function receipt(name: string, value: unknown) {
  fs.writeFileSync(path.join(artifact, name), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}
async function sql(text: string, values: any[] = []) {
  try { return await client!.query(text, values); }
  catch { uncertain = true; throw new Error('RG06B_SQL_OUTCOME_UNCERTAIN'); }
}
async function snapshot() {
  return (await sql('SELECT ' + fields + ' FROM public.analyses ORDER BY run_id')).rows;
}
async function removeOwned(row: any, expectedAfter: any[]) {
  try {
    await sql('BEGIN');
    expect((await sql('SELECT ' + fields + ' FROM public.analyses WHERE run_id=$1::uuid FOR UPDATE', [row.run_id])).rows).toEqual([row]);
    expect((await sql('DELETE FROM public.analyses WHERE run_id=$1::uuid RETURNING run_id', [row.run_id])).rowCount).toBe(1);
    expect(await snapshot()).toEqual(expectedAfter);
    await sql('COMMIT');
    expect(await snapshot()).toEqual(expectedAfter);
  } catch (error) {
    uncertain = true;
    try { await client!.query('ROLLBACK'); } catch { /* An uncertain COMMIT remains uncertain. */ }
    throw error;
  }
}
async function evidence(name: string, value: unknown) {
  receipt(name + '.json', value);
  await test.info().attach(name, { body: JSON.stringify(value, null, 2), contentType: 'application/json' });
}

test.beforeAll(async () => {
  client = new pg.Client({ connectionString: process.env.DATABASE_URL,
    connectionTimeoutMillis: 5_000, query_timeout: 7_000, statement_timeout: 5_000,
    application_name: 'rg06b-independent-verifier', options: '-c timezone=UTC' });
  client.on('error', () => { uncertain = true; });
  try { await client.connect(); } catch { throw new Error('RG06B_SQL_CONNECT_FAILED'); }
  const identity = (await sql("SELECT current_database() AS db, current_user AS role, current_setting('server_version_num') AS version")).rows[0];
  expect(identity).toEqual({ db: 'reqguard_rg06b', role: 'reqguard_rg06b', version: '170011' });
  const columns = (await sql("SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema=$1 AND table_name=$2 ORDER BY ordinal_position", ['public', 'analyses'])).rows;
  expect(columns.map(r => [r.column_name, r.data_type, r.is_nullable, r.column_default])).toEqual([
    ['run_id', 'uuid', 'NO', null], ['provider', 'text', 'NO', null], ['status', 'text', 'NO', null],
    ['original_input', 'text', 'NO', null], ['analysis_payload', 'jsonb', 'YES', null],
    ['created_at', 'timestamp with time zone', 'NO', 'CURRENT_TIMESTAMP'],
  ]);
  const constraints = (await sql("SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid='public.analyses'::regclass ORDER BY conname")).rows;
  expect(constraints).toEqual([
    { conname: 'analyses_analysis_consistency', definition: "CHECK ((((status = 'completed'::text) AND (analysis_payload IS NOT NULL) AND (jsonb_typeof(analysis_payload) = 'object'::text)) OR ((status = 'unsupported_fixture'::text) AND (analysis_payload IS NULL))))" },
    { conname: 'analyses_pkey', definition: 'PRIMARY KEY (run_id)' },
    { conname: 'analyses_status_valid', definition: "CHECK ((status = ANY (ARRAY['completed'::text, 'unsupported_fixture'::text])))" },
  ]);
  expect(await snapshot()).toEqual([]);
  const id = randomUUID();
  receipt('sentinel-plan.json', { run, run_id: id });
  await sql('INSERT INTO public.analyses(run_id,provider,status,original_input,analysis_payload) VALUES($1::uuid,$2,$3,$4,NULL)',
    [id, 'fake', 'unsupported_fixture', 'RG06B owned sentinel ' + run]);
  baseline = await snapshot();
  expect(baseline).toHaveLength(1);
  sentinel = baseline[0];
  expect(sentinel).toMatchObject({ run_id: id, provider: 'fake', status: 'unsupported_fixture',
    original_input: 'RG06B owned sentinel ' + run, analysis_payload: null, sql_null: true });
  receipt('baseline.json', { identity, columns, constraints, rows: baseline });
  uncertain = false;
});

test('supported fixture: browser HTTP 200, visible result, independent committed SQL row', async ({ page }) => {
  await page.goto('/');
  await page.locator('#requirement').fill(fixture);
  let posts = 0;
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname === '/analyses') posts++; });
  let verifiedOwnership = false;
  try {
    inFlight = true;
    const responsePromise = page.waitForResponse(r => r.request().method() === 'POST' && r.url() === process.env.RG06B_BASE_URL + '/analyses');
    const [response] = await Promise.all([responsePromise, page.locator('#submit').click()]);
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({ requirement_text: fixture });
    const body = await response.json();
    expect(body.run_id).toMatch(uuid4);
    receipt('supported-response-id.json', { run_id: body.run_id });
    expect(body).toEqual({ run_id: body.run_id, provider: 'fake', status: 'completed', analysis });
    const rows = (await sql('SELECT ' + fields + ' FROM public.analyses WHERE run_id=$1::uuid', [body.run_id])).rows;
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({ run_id: body.run_id, provider: body.provider, status: body.status,
      original_input: fixture, analysis_payload: body.analysis, created_at: expect.any(String), sql_null: false });
    expect(Number.isFinite(Date.parse(rows[0].created_at))).toBe(true);
    const after = await snapshot();
    expect(after.filter(r => r.run_id !== body.run_id)).toEqual(baseline);
    expect(after).toHaveLength(baseline.length + 1);
    owned = rows[0]; verifiedOwnership = true; inFlight = false;
    await evidence('supported-sql', { response: body, before: baseline, after, verified: true,
      browserVersion: page.context().browser()!.version() });
    await expect(page.locator('#result')).toBeVisible();
    await expect(page.locator('#run-id')).toHaveText(body.run_id);
    await expect(page.locator('#provider')).toHaveText('fake');
    await expect(page.locator('#status')).toHaveText('completed');
    for (const text of [analysis.ambiguities[0].term, analysis.ambiguities[0].explanation,
      ...analysis.missing_measurable_criteria, analysis.candidate_test_scenarios[0].title,
      ...analysis.candidate_test_scenarios[0].steps, analysis.candidate_test_scenarios[0].expected_result]) {
      await expect(page.locator('#analysis')).toContainText(text);
    }
    expect(posts).toBe(1);
  } catch (error) { if (!verifiedOwnership) uncertain = true; throw error; }
  finally {
    if (verifiedOwnership && !uncertain) {
      await removeOwned(owned, baseline); owned = undefined; supportedCleaned = true;
      receipt('supported-cleanup.json', { remainingOwnedRows: 0, sentinelUnchanged: true });
    }
  }
});

test('invalid whitespace: actual FastAPI HTTP 422 and unchanged SQL snapshot', async ({ page }) => {
  if (uncertain || !supportedCleaned) throw new Error('RG06B_PREVIOUS_OUTCOME_UNCERTAIN');
  const before = await snapshot();
  expect(before).toEqual(baseline);
  await page.goto('/');
  // The product form uses novalidate. Assert a real POST, not client-side rejection.
  const invalid = ' \t\n';
  await page.locator('#requirement').fill(invalid);
  let posts = 0;
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname === '/analyses') posts++; });
  let settled = false;
  try {
    inFlight = true;
    const responsePromise = page.waitForResponse(r => r.request().method() === 'POST' && r.url() === process.env.RG06B_BASE_URL + '/analyses');
    const [response] = await Promise.all([responsePromise, page.locator('#submit').click()]);
    expect(response.status()).toBe(422);
    expect(response.request().postDataJSON()).toEqual({ requirement_text: invalid });
    const body = await response.json();
    expect(body.detail.length).toBeGreaterThan(0);
    expect(body.detail[0].loc).toEqual(['body', 'requirement_text']);
    const after = await snapshot();
    expect(after).toEqual(before);
    settled = true; inFlight = false;
    await evidence('invalid-sql', { status: 422, before, after, noDelta: true });
    await expect(page.locator('#error-title')).toHaveText('Validation failed (HTTP 422)');
    await expect(page.locator('#error-details')).toContainText('requirement_text');
    await expect(page.locator('#result')).toBeHidden();
    expect(posts).toBe(1); invalidVerified = true;
  } catch (error) { if (!settled) uncertain = true; throw error; }
});

test.afterAll(async () => {
  let state = 'UNRESOLVED';
  try {
    if (!uncertain && !inFlight && sentinel && !owned) {
      expect(await snapshot()).toEqual(baseline);
      await removeOwned(sentinel, []); state = 'CLEANED';
    }
  } finally {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      if (client) await Promise.race([client.end(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('SQL_CLOSE_TIMEOUT')), 5_000);
      })]);
    } catch { state = 'UNRESOLVED'; }
    finally { clearTimeout(timer); }
    receipt('sql-cleanup.json', { state, supportedCleaned, invalidVerified, uncertain: uncertain || inFlight });
    if (state !== 'CLEANED') throw new Error('RG06B_DATABASE_RETAINED_UNRESOLVED');
  }
});
