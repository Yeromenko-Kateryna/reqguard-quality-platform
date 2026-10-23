// SOURCE ONLY: do not execute under RG-05-WIN32-BRIDGE-SYNTHETIC-SOURCE-01.
// Future entry: Node 24.15.0 node:test with TypeScript stripping; no packages.
// RG05_SYNTHETIC_ADDON must explicitly name a separately built external addon.
// Only in-memory synthetic:// fixtures are passed to the bridge. No child,
// network, database, actual admission, scratch files or timers are used here.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

type Ref = object;
type State = 'PREPARED' | 'HELD' | 'FROZEN' | 'RELEASED';
interface Audit {
  evidence: 'synthetic'; realOperations: number; createAttempts: number;
  modelCreates: number; leaseQueries: number; processQueries: number;
  modelCloses: number; modelProcessCloses: number; deletes: number;
  reopens: number; duplicates: number; trace: readonly string[];
}
interface Status {
  evidence: 'synthetic'; state: State; reason: string | null;
  remainingMs: bigint; admissionSupported: false; audit: Audit;
}
interface Bridge {
  bridgeInfo(): { evidence: 'synthetic'; admissionSupported: false; dispatchSupported: false };
  prepareScratch(config: unknown): Ref;
  acquireScratchLease(session: Ref): { evidence: 'synthetic'; state: 'HELD'; lock: object; owner: object };
  checkLease(session: Ref, work: bigint): { evidence: 'synthetic' };
  observeProcess(session: Ref, pid: number, expected: unknown): Ref;
  checkProcess(session: Ref, process: Ref): { evidence: 'synthetic' };
  freeze(session: Ref, reason: 'CALLER_STOP'): Status;
  status(session: Ref): Status;
}
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const addon = process.env.RG05_SYNTHETIC_ADDON;
assert.ok(addon && path.isAbsolute(addon), 'Explicit absolute external addon path required');
const relative = path.relative(repo, addon);
assert.ok(relative.startsWith('..' + path.sep) || path.isAbsolute(relative), 'Addon must be external');
assert.equal(path.extname(addon), '.node');
// The sole future native load. This test source is NOT executed in this task.
const bridge = createRequire(import.meta.url)(addon) as Bridge;
const info = bridge.bridgeInfo();
assert.equal(info.evidence, 'synthetic');
assert.equal(info.admissionSupported, false);
assert.equal(info.dispatchSupported, false);

let sequence = 0;
function config(scenario = 'success', extra: Record<string, unknown> = {}) {
  const suffix = (++sequence).toString(16).padStart(12, '0');
  return {
    schema: 1, runUuid: `00000000-0000-4000-8000-${suffix}`,
    scratchRoot: `synthetic://scratch/case-${sequence}`,
    trustedRunnerSid: 'S-1-5-21-1-2-3-1001', expiresAtUnixMs: 1_010_000n,
    maxLifetimeMs: 10_000n, settlementReserveMs: 100n,
    synthetic: { scenario }, ...extra,
  };
}
function expected(extra: Record<string, unknown> = {}) {
  return { pid: 7, creationTime100ns: 1n, executablePath: 'synthetic://process/fixture',
    executableSha256: 'a'.repeat(64), tokenUserSid: 'S-1-5-21-1-2-3-1001', ...extra };
}
function prepare(scenario = 'success') { return bridge.prepareScratch(config(scenario)); }
function held(scenario = 'success') {
  const s = prepare(scenario); bridge.acquireScratchLease(s); return s;
}
function refused(action: () => unknown, code: string, extra: Record<string, unknown> = {}) {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof Error);
    const e = error as Error & Record<string, unknown>;
    assert.equal(e.code, code); assert.equal(e.evidence, 'synthetic');
    assert.equal(e.message, 'RG05 synthetic operation refused');
    for (const [key, value] of Object.entries(extra)) assert.equal(e[key], value);
    for (const key of ['code', 'operation', 'win32Code', 'state', 'effect']) assert.ok(Object.hasOwn(e, key));
    return true;
  });
}
function audit(s: Ref, state: State = 'FROZEN') {
  const status = bridge.status(s);
  assert.equal(status.evidence, 'synthetic'); assert.equal(status.state, state);
  assert.equal(status.admissionSupported, false); assert.ok(Object.isFrozen(status));
  const a = status.audit;
  assert.equal(a.realOperations, 0); assert.equal(a.deletes, 0);
  assert.equal(a.reopens, 0); assert.equal(a.duplicates, 0);
  assert.ok(Object.isFrozen(a)); assert.ok(Object.isFrozen(a.trace)); return a;
}

test('control: synthetic acquisition and two checks retain one modeled lease', () => {
  const s = prepare(); assert.equal(bridge.status(s).state, 'PREPARED');
  const lease = bridge.acquireScratchLease(s);
  assert.equal(lease.evidence, 'synthetic'); assert.equal(lease.state, 'HELD');
  assert.ok(Object.isFrozen(lease)); assert.ok(Object.isFrozen(lease.lock)); assert.ok(Object.isFrozen(lease.owner));
  const p = bridge.observeProcess(s, 7, expected());
  assert.equal(bridge.checkProcess(s, p).evidence, 'synthetic');
  assert.equal(bridge.checkLease(s, 1n).evidence, 'synthetic');
  assert.equal(bridge.checkLease(s, 1n).evidence, 'synthetic');
  const a = audit(s, 'HELD'); assert.equal(a.modelCreates, 1); assert.equal(a.createAttempts, 1);
  assert.equal(a.modelCloses, 0);
  assert.deepEqual(a.trace.slice(0, 5), ['prepare', 'create.attempt', 'create.success', 'identity.query', 'inheritance.check']);
});

test('N01: strict types, own fields, accessors, NUL, overflow, arity and forged sessions', () => {
  for (const invalid of [null, undefined, [], 'config']) {
    refused(() => bridge.prepareScratch(invalid), 'RG05_ARGUMENT', { effect: 'NONE' });
  }
  for (const patch of [{ schema: '1' }, { extra: true }, { runUuid: 'bad\0uuid' },
    { maxLifetimeMs: -1n }, { maxLifetimeMs: 1n << 70n }, { maxLifetimeMs: 10_000 },
    { trustedRunnerSid: 'invalid' }, { synthetic: { scenario: 'unknown' } }]) {
    refused(() => bridge.prepareScratch(config('success', patch)), 'RG05_ARGUMENT', { effect: 'NONE' });
  }
  let getterCalls = 0;
  const c = config(); Object.defineProperty(c, 'schema', { get() { ++getterCalls; return 1; } });
  refused(() => bridge.prepareScratch(c), 'RG05_ARGUMENT'); assert.equal(getterCalls, 0);
  const sym = config(); Object.defineProperty(sym, Symbol('extra'), { value: true });
  refused(() => bridge.prepareScratch(sym), 'RG05_ARGUMENT');
  refused(() => bridge.acquireScratchLease({}), 'RG05_ARGUMENT');
  const s = held();
  refused(() => Reflect.apply(bridge.checkLease, null, [s, 1n, 'extra']), 'RG05_ARGUMENT');
  assert.equal(audit(s).createAttempts, 1);
  for (const work of [-1n, 1n << 70n, 1, undefined]) {
    const invalid = held();
    refused(() => Reflect.apply(bridge.checkLease, null, [invalid, work]), 'RG05_ARGUMENT'); audit(invalid);
  }
  const missing = held();
  refused(() => Reflect.apply(bridge.checkLease, null, [missing]), 'RG05_ARGUMENT'); audit(missing);
  for (const pid of [0, -1, 1.5, 4294967296, NaN, Infinity]) {
    const invalid = held();
    refused(() => bridge.observeProcess(invalid, pid, expected()), 'RG05_ARGUMENT'); audit(invalid);
  }
});

test('N02: real, relative, UNC, ADS, sync and reparse-looking paths are never accepted', () => {
  for (const scratchRoot of ['C:\\ReqGuardLocal\\rg05-v2', '.\\scratch', '\\\\host\\share',
    'C:\\scratch:stream', 'C:\\Users\\runner\\OneDrive\\scratch', 'C:\\junction\\scratch',
    'synthetic://scratch/../real', 'synthetic://scratch/a\0b']) {
    refused(() => bridge.prepareScratch(config('success', { scratchRoot })),
      scratchRoot.includes('\0') ? 'RG05_ARGUMENT' : 'RG05_PATH_DENIED', { effect: 'NONE' });
  }
});

test('N03: collision codes never reopen, reclaim or retry', () => {
  for (const [scenario, win32Code] of [['collision-exists', 80], ['collision-already', 183], ['collision-sharing', 32]] as const) {
    const s = prepare(scenario);
    refused(() => bridge.acquireScratchLease(s), 'RG05_COLLISION', { win32Code, effect: 'NONE' });
    const a = audit(s); assert.equal(a.modelCreates, 0); assert.equal(a.createAttempts, 1);
    refused(() => bridge.acquireScratchLease(s), 'RG05_STATE'); assert.equal(audit(s).createAttempts, 1);
  }
});

test('N04: null/invalid modeled handle refuses usable lease', () => {
  for (const scenario of ['null-handle', 'invalid-handle']) {
    const s = prepare(scenario);
    refused(() => bridge.acquireScratchLease(s), 'RG05_OS', { win32Code: 6, effect: 'UNKNOWN' });
    assert.equal(audit(s).modelCreates, 0);
  }
});
test('N05: failed post-create observation retains the consumed modeled lease', () => {
  const s = prepare('post-create-query');
  refused(() => bridge.acquireScratchLease(s), 'RG05_OS', { effect: 'CREATED', win32Code: 5 });
  const a = audit(s); assert.equal(a.modelCreates, 1); assert.equal(a.modelCloses, 0);
  assert.deepEqual(a.trace, ['prepare', 'create.attempt', 'create.success', 'identity.query']);
});
test('N06: uncertain create consumes namespace and forbids retry', () => {
  const c = config('uncertain-create'); const s = bridge.prepareScratch(c);
  refused(() => bridge.acquireScratchLease(s), 'RG05_OS', { effect: 'UNKNOWN' });
  refused(() => bridge.acquireScratchLease(s), 'RG05_STATE'); assert.equal(audit(s).createAttempts, 1);
  const other = bridge.prepareScratch(config('success', { scratchRoot: c.scratchRoot }));
  refused(() => bridge.acquireScratchLease(other), 'RG05_COLLISION'); audit(other);
});
test('N07: file, volume, parent, SID and ACL drift freeze irreversibly', () => {
  for (const scenario of ['file-drift', 'volume-drift', 'parent-drift', 'sid-drift', 'acl-drift']) {
    const s = held(scenario);
    refused(() => bridge.checkLease(s, 1n), 'RG05_IDENTITY');
    assert.equal(audit(s).modelCloses, 0);
    refused(() => bridge.checkLease(s, 1n), 'RG05_STATE'); audit(s);
  }
  const s = held('invalidated'); refused(() => bridge.checkLease(s, 1n), 'RG05_OS', { win32Code: 6 }); audit(s);
});
test('N08: inheritance bit refuses before HELD', () => {
  const s = prepare('inheritance'); refused(() => bridge.acquireScratchLease(s), 'RG05_IDENTITY');
  const a = audit(s); assert.equal(a.modelCreates, 1); assert.ok(!a.trace.includes('held'));
});
test('N09: wrong creation time/hash/path/SID, reused PID and exited process refuse', () => {
  for (const patch of [{ pid: 8 }, { creationTime100ns: 2n }, { executableSha256: 'b'.repeat(64) },
    { executablePath: 'synthetic://process/other' }, { tokenUserSid: 'S-1-5-21-1-2-3-1002' }]) {
    const s = held(); refused(() => bridge.observeProcess(s, 7, expected(patch)), 'RG05_IDENTITY'); audit(s);
  }
  for (const scenario of ['pid-reuse', 'process-exit']) {
    const s = held(scenario); refused(() => bridge.observeProcess(s, 7, expected()), 'RG05_IDENTITY'); audit(s);
  }
  for (const scenario of ['pid-reuse-after-observe', 'process-exit-after-observe']) {
    const s = held(scenario); const p = bridge.observeProcess(s, 7, expected());
    refused(() => bridge.checkProcess(s, p), 'RG05_IDENTITY');
    assert.equal(audit(s).processQueries, 2);
  }
});
test('N10: process query/wait failure preserves the injected numeric code', () => {
  for (const [scenario, win32Code] of [['process-query', 5], ['process-wait', 6]] as const) {
    const s = held(scenario);
    refused(() => bridge.observeProcess(s, 7, expected()), 'RG05_OS', { win32Code });
    const a = audit(s); assert.equal(a.processQueries, 1); assert.equal(a.modelProcessCloses, 0);
    assert.equal(a.trace.at(-1), scenario === 'process-query' ? 'process.query' : 'process.wait');
  }
});
test('N11: either deadline, either clock regression, or clock failure freezes', () => {
  for (const scenario of ['wall-expiry', 'mono-expiry', 'wall-regression', 'mono-regression', 'clock-failure']) {
    const s = held(scenario);
    refused(() => bridge.checkLease(s, 1n), scenario === 'clock-failure' ? 'RG05_OS' : 'RG05_EXPIRED');
    assert.equal(bridge.status(s).remainingMs, 0n); audit(s);
    refused(() => bridge.acquireScratchLease(s), 'RG05_STATE'); audit(s);
  }
});
test('N12: equal/below required work plus reserve refuses', () => {
  for (const work of [9900n, 9901n, 10000n]) {
    const s = held(); refused(() => bridge.checkLease(s, work), 'RG05_BUDGET'); audit(s);
  }
  const control = held(); assert.equal(bridge.checkLease(control, 9899n).evidence, 'synthetic');
});
test('N13: explicit freeze, invalid sequence and repeated acquisition cannot rearm', () => {
  const c = config(); const s = bridge.prepareScratch(c); bridge.acquireScratchLease(s);
  assert.equal(bridge.freeze(s, 'CALLER_STOP').state, 'FROZEN');
  assert.equal(bridge.freeze(s, 'CALLER_STOP').state, 'FROZEN');
  refused(() => bridge.acquireScratchLease(s), 'RG05_STATE');
  refused(() => bridge.checkLease(s, 1n), 'RG05_STATE');
  refused(() => bridge.prepareScratch(c), 'RG05_STATE');
  assert.equal(audit(s).modelCreates, 1);
  const twice = held(); refused(() => bridge.acquireScratchLease(twice), 'RG05_STATE'); audit(twice);
  const early = prepare(); refused(() => bridge.checkLease(early, 1n), 'RG05_STATE');
  assert.equal(audit(early).createAttempts, 0);
});
test('R02: registration allocation failure irrevocably consumes the UUID', () => {
  const c = config('registration-failure');
  refused(() => bridge.prepareScratch(c), 'RG05_INTERNAL',
    { operation: 'prepareScratch', state: null, effect: 'NONE' });
  // Remove the fault and change the namespace: refusal must depend on the UUID.
  const replacement = { ...c, scratchRoot: c.scratchRoot + '-replacement',
    synthetic: { scenario: 'success' } };
  refused(() => bridge.prepareScratch(replacement), 'RG05_STATE',
    { operation: 'prepareScratch', state: null, effect: 'NONE' });
  refused(() => bridge.prepareScratch(c), 'RG05_STATE');
  // A distinct UUID still works; there is no environment reset or retry gate.
  const other = held(); assert.equal(audit(other, 'HELD').modelCreates, 1);
});
test('N14: observation copies, forged/cloned and cross-session process refs confer no authority', () => {
  const s = prepare(); const lease = bridge.acquireScratchLease(s);
  refused(() => bridge.checkLease({ ...lease }, 1n), 'RG05_ARGUMENT');
  assert.equal(bridge.status(s).state, 'HELD');
  refused(() => bridge.checkProcess(s, {}), 'RG05_ARGUMENT'); audit(s);
  const owner = held(); const p = bridge.observeProcess(owner, 7, expected());
  const other = held(); refused(() => bridge.checkProcess(other, p), 'RG05_IDENTITY'); audit(other);
  const copied = held(); refused(() => bridge.checkProcess(copied, { ...p }), 'RG05_ARGUMENT'); audit(copied);
  const cloned = held();
  // Hosts may reject native wrappers during cloning. Otherwise the clone loses
  // native authority and must be rejected by the bridge.
  let clone: object | undefined;
  try { clone = structuredClone(cloned); }
  catch (error: unknown) { assert.equal((error as Error).name, 'DataCloneError'); }
  if (clone) refused(() => bridge.checkLease(clone, 1n), 'RG05_ARGUMENT');
  assert.equal(bridge.status(cloned).state, 'HELD');
});
test('N15: modeled teardown closes each modeled object once and preserves stale namespace', () => {
  const c = config('teardown'); const s = bridge.prepareScratch(c); bridge.acquireScratchLease(s);
  bridge.observeProcess(s, 7, expected());
  bridge.freeze(s, 'CALLER_STOP'); bridge.freeze(s, 'CALLER_STOP');
  const a = audit(s, 'RELEASED'); assert.equal(a.modelCloses, 1); assert.equal(a.modelProcessCloses, 1);
  assert.deepEqual(a.trace.slice(-4), ['freeze', 'teardown', 'freeze', 'teardown']);
  refused(() => bridge.acquireScratchLease(s), 'RG05_STATE'); audit(s, 'RELEASED');
  const next = bridge.prepareScratch(config('success', { scratchRoot: c.scratchRoot }));
  refused(() => bridge.acquireScratchLease(next), 'RG05_COLLISION'); audit(next);
});
test('N16: two modeled claimants acquire at most once; stale refuses without deletion', () => {
  const firstConfig = config(); const first = bridge.prepareScratch(firstConfig);
  const second = bridge.prepareScratch(config('success', { scratchRoot: firstConfig.scratchRoot }));
  bridge.acquireScratchLease(first);
  refused(() => bridge.acquireScratchLease(second), 'RG05_COLLISION');
  assert.equal(audit(first, 'HELD').modelCreates + audit(second).modelCreates, 1);
  const staleConfig = config('stale'); const stale = bridge.prepareScratch(staleConfig);
  refused(() => bridge.acquireScratchLease(stale), 'RG05_COLLISION');
  assert.equal(audit(stale).modelCreates, 0);
  const retry = bridge.prepareScratch(config('success', { scratchRoot: staleConfig.scratchRoot }));
  refused(() => bridge.acquireScratchLease(retry), 'RG05_COLLISION'); audit(retry);
});
