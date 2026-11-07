// Adapter over the standard Node TestsStream, not human-readable console output.
export default async function* reporter(source) {
  const cases = [];
  let summary;
  for await (const { type, data } of source) {
    if (type === 'test:pass' || type === 'test:fail') {
      cases.push({ name: data.name, passed: type === 'test:pass', skip: Boolean(data.skip),
        todo: Boolean(data.todo), nesting: data.nesting });
    }
    if (type === 'test:summary' && data.file === undefined) {
      if (summary) throw new Error('RG06D_DUPLICATE_UNIT_SUMMARY');
      const c = data.counts;
      summary = Object.fromEntries(['tests', 'passed', 'failed', 'cancelled', 'skipped', 'todo', 'suites'].map(k => [k, c[k]]));
    }
  }
  yield JSON.stringify({ cases, summary }) + '\n';
}
