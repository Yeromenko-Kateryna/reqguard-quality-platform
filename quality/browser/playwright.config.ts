import { defineConfig } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const run = process.env.RG06B_RUN_ID ?? '';
const port = process.env.RG06B_API_PORT ?? '';
const artifact = process.env.RG06B_ARTIFACT ?? '';
const dsn = process.env.DATABASE_URL ?? '';
if (!/^[a-f0-9]{32}$/.test(run) || !/^\d{4,5}$/.test(port) || Number(port) > 65535 ||
    artifact !== path.join(here, '.artifacts', run) || !dsn ||
    !fs.existsSync(path.join(artifact, 'launch.json'))) throw new Error('RG06B_LAUNCHER_REQUIRED');
const db = new URL(dsn);
if (db.protocol !== 'postgresql:' || db.hostname !== '127.0.0.1' ||
    db.username !== 'reqguard_rg06b' || db.pathname !== '/reqguard_rg06b' ||
    db.port !== process.env.RG06B_DB_PORT || !/^[a-f0-9]{64}$/.test(db.password)) {
  throw new Error('RG06B_DATABASE_BOUNDARY');
}
const baseURL = 'http://127.0.0.1:' + port;
export default defineConfig({
  testDir: here, testMatch: 'analyses.spec.ts',
  fullyParallel: false, workers: 1, retries: 0, maxFailures: 1, forbidOnly: true,
  timeout: 30_000, globalTimeout: 120_000, expect: { timeout: 5_000 },
  outputDir: path.join(artifact, 'playwright-results'),
  reporter: [['list'], ['json', { outputFile: path.join(artifact, 'results.json') }]],
  // Use the full bundled Chromium (new headless), whose executable is preflighted.
  projects: [{ name: 'chromium', use: { browserName: 'chromium', channel: 'chromium' } }],
  use: { baseURL, headless: true, actionTimeout: 10_000, navigationTimeout: 15_000,
    trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'off',
    serviceWorkers: 'block' },
  webServer: {
    command: 'uv run --locked --no-sync python -m uvicorn reqguard.main:app --host 127.0.0.1 --port ' + port + ' --workers 1',
    cwd: path.resolve(here, '../..'),
    // DATABASE_URL is inherited from the launcher, not serialized in reporter config.
    env: { PYTHONDONTWRITEBYTECODE: '1' },
    url: baseURL + '/', reuseExistingServer: false, timeout: 30_000,
    stdout: 'pipe', stderr: 'pipe',
  },
});
