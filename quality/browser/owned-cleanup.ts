import { deepStrictEqual, strictEqual } from 'node:assert';
import { isDeepStrictEqual } from 'node:util';

export interface AnalysisRow {
  run_id: string; provider: string; status: string; original_input: string;
  analysis_payload: unknown; created_at: string; sql_null: boolean;
}
export const analysisFields = 'run_id::text, provider, status, original_input, analysis_payload, created_at::text, analysis_payload IS NULL AS sql_null';
export type Query = (text: string, values?: any[]) => Promise<{ rows: any[]; rowCount: number | null }>;
type CreationEvidence = {
  run: string;
  operation: 'sentinel-insert' | 'foreign-fixture-insert' | 'supported-http' | 'unsupported-http';
  before: AnalysisRow[]; after: AnalysisRow[];
};

export class OwnershipRejected extends Error {
  constructor() { super('RG06B_UNOWNED_CLEANUP'); }
}

// Test-scoped authority: only trusted setup/HTTP verification code registers a
// committed single-row creation delta. A SELECT or caller-supplied UUID is not a grant.
// This process-local registry does not establish RG-05 writer fencing or a lease.
export function createOwnedCleanup(
  run: string, query: Query, onUncertain: () => void, rollback: () => Promise<unknown>,
) {
  if (!/^[a-f0-9]{32}$/.test(run)) throw new Error('RG06B_CLEANUP_RUN_REQUIRED');
  const registry = new Map<string, { run: string; operation: CreationEvidence['operation']; row: AnalysisRow }>();
  let blocked = false;
  const snapshot = async () => (await query('SELECT ' + analysisFields + ' FROM public.analyses ORDER BY run_id')).rows;
  return {
    registerCreated(row: AnalysisRow, evidence: CreationEvidence) {
      if (blocked) throw new Error('RG06B_CLEANUP_OUTCOME_UNCERTAIN');
      strictEqual(evidence.run, run, 'Creation evidence belongs to a different test run');
      strictEqual(['sentinel-insert', 'foreign-fixture-insert', 'supported-http', 'unsupported-http'].includes(evidence.operation), true);
      strictEqual(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(row.run_id), true);
      strictEqual(registry.has(row.run_id), false, 'Duplicate ownership registration');
      strictEqual(new Set(evidence.before.map(r => r.run_id)).size, evidence.before.length);
      strictEqual(new Set(evidence.after.map(r => r.run_id)).size, evidence.after.length);
      strictEqual(evidence.before.some(r => r.run_id === row.run_id), false, 'Preexisting rows cannot acquire ownership');
      deepStrictEqual(evidence.after.filter(r => r.run_id === row.run_id), [row]);
      deepStrictEqual(evidence.after.filter(r => r.run_id !== row.run_id), evidence.before);
      registry.set(row.run_id, { run, operation: evidence.operation, row: structuredClone(row) });
    },
    async removeOwned(row: AnalysisRow, expectedAfter: AnalysisRow[]) {
      if (blocked) throw new Error('RG06B_CLEANUP_OUTCOME_UNCERTAIN');
      const grant = registry.get(row?.run_id);
      // Deliberately outside the transaction: reject before BEGIN, SELECT or DELETE.
      if (!grant || grant.run !== run || !isDeepStrictEqual(grant.row, row)) throw new OwnershipRejected();
      try {
        await query('BEGIN');
        deepStrictEqual((await query('SELECT ' + analysisFields + ' FROM public.analyses WHERE run_id=$1::uuid FOR UPDATE', [row.run_id])).rows, [grant.row]);
        strictEqual((await query('DELETE FROM public.analyses WHERE run_id=$1::uuid RETURNING run_id', [row.run_id])).rowCount, 1);
        deepStrictEqual(await snapshot(), expectedAfter);
        await query('COMMIT');
        deepStrictEqual(await snapshot(), expectedAfter);
        registry.delete(row.run_id);
      } catch (error) {
        blocked = true;
        onUncertain();
        // Retain existing rollback handling; never retry DELETE or COMMIT.
        // A rollback acknowledgment cannot resolve an ambiguous COMMIT.
        try { await rollback(); } catch { /* Retain unresolved state. */ }
        throw error;
      }
    },
  };
}
