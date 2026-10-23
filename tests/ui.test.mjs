import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mountUI, submitRequirement } from '../reqguard/static/app.mjs';

const completed = () => ({
  run_id: '00000000-0000-4000-8000-000000000001', provider: 'fake', status: 'completed',
  analysis: { ambiguities: [{ term: 'quickly', explanation: 'Specify a duration.' }],
    missing_measurable_criteria: ['A measurable limit'],
    candidate_test_scenarios: [{ title: 'Reset', steps: ['Start', 'Finish'], expected_result: 'Within the limit' }] },
});
const reply = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });

test('POST uses the same-origin JSON API and preserves the original text', async () => {
  const states = [];
  let calls = 0;
  const result = await submitRequirement('  synthetic input\n', {
    fetchImpl: async (url, options) => {
      calls++;
      assert.equal(url, '/analyses');
      assert.equal(options.method, 'POST');
      assert.equal(options.headers['Content-Type'], 'application/json');
      assert.equal(options.headers.Accept, 'application/json');
      assert.equal(options.redirect, 'error');
      assert.deepEqual(JSON.parse(options.body), { requirement_text: '  synthetic input\n' });
      return reply(200, completed());
    }, onState: state => states.push(state.kind),
  });
  assert.equal(calls, 1);
  assert.deepEqual(states, ['loading', 'result']);
  assert.equal(result.body.run_id, completed().run_id);
});

test('unsupported_fixture remains a distinct valid result without analysis', async () => {
  const body = { ...completed(), status: 'unsupported_fixture', analysis: null };
  const result = await submitRequirement('other', { fetchImpl: async () => reply(200, body) });
  assert.equal(result.kind, 'result');
  assert.equal(result.body.status, 'unsupported_fixture');
  assert.equal(result.body.analysis, null);
});

test('422 preserves readable validation details without emitting success', async () => {
  const states = [];
  const result = await submitRequirement('', {
    fetchImpl: async () => reply(422, { detail: [{ loc: ['body', 'requirement_text'], msg: 'Invalid <input>' }] }),
    onState: state => states.push(state.kind),
  });
  assert.deepEqual(states, ['loading', 'error']);
  assert.equal(result.title, 'Validation failed (HTTP 422)');
  assert.deepEqual(result.details, ['body.requirement_text: Invalid <input>']);
  assert.equal(result.body, undefined);
});

for (const code of [503, 500]) test('HTTP ' + code + ' never produces a successful result or retries', async () => {
  let calls = 0;
  const result = await submitRequirement('example', { fetchImpl: async () => {
    calls++; return reply(code, { detail: 'Internal diagnostic must not be displayed' });
  } });
  assert.equal(calls, 1);
  assert.equal(result.kind, 'error');
  assert.equal(result.title, 'Request failed (HTTP ' + code + ')');
  assert.match(result.message, /may have reached/);
  assert.doesNotMatch(result.message, /Internal diagnostic/);
});

test('network failure reports an uncertain outcome and performs no retry', async () => {
  let calls = 0;
  const result = await submitRequirement('example', { fetchImpl: async () => {
    calls++; throw new Error('private transport diagnostic');
  } });
  assert.equal(calls, 1);
  assert.equal(result.title, 'Network error');
  assert.match(result.message, /no automatic retry/);
  assert.doesNotMatch(result.message, /private/);
});

test('unreadable successful response is not misreported as a network error or success', async () => {
  const result = await submitRequirement('example', { fetchImpl: async () => ({
    ok: true, status: 200, json: async () => { throw new Error('invalid JSON'); },
  }) });
  assert.equal(result.kind, 'error');
  assert.equal(result.title, 'Unexpected server response');
});

test('malformed analysis is rejected before DOM rendering', async () => {
  const body = completed(); body.analysis.candidate_test_scenarios[0].steps = 'not an array';
  const result = await submitRequirement('example', { fetchImpl: async () => reply(200, body) });
  assert.equal(result.kind, 'error');
});

// A small DOM adapter tests observable rendering/state changes, not browser layout.
class Element {
  children = []; dataset = {}; attributes = {}; hidden = false; disabled = false; value = '';
  constructor(tag = 'div') { this.tag = tag; this.text = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(_) { throw new Error('Unsafe HTML insertion'); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, handler) { this[name] = handler; }
}
function page() {
  const nodes = new Map();
  const doc = {
    getElementById: id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); },
    createElement: tag => new Element(tag),
    createTextNode: text => { const node = new Element('#text'); node.textContent = text; return node; },
  };
  mountUI(doc);
  return { doc, node: doc.getElementById, submit: () => doc.getElementById('analysis-form').submit({ preventDefault() {} }) };
}
async function withFetch(fetchImpl, action) {
  const original = globalThis.fetch;
  globalThis.fetch = fetchImpl;
  try { await action(); } finally { globalThis.fetch = original; }
}

test('rendered results use text nodes for every API field, including markup', async () => {
  const ui = page();
  const payload = '<img src=x onerror="globalThis.injected=true">';
  const body = completed();
  body.analysis.ambiguities = [{ term: payload, explanation: payload }];
  body.analysis.missing_measurable_criteria = [payload];
  body.analysis.candidate_test_scenarios = [{ title: payload, steps: [payload], expected_result: payload }];
  await withFetch(async () => reply(200, body), () => ui.submit());
  assert.equal(ui.node('result').hidden, false);
  assert.equal(ui.node('run-id').textContent, body.run_id);
  assert.equal(ui.node('status').textContent, 'completed');
  assert.equal(ui.node('provider').textContent, 'fake');
  assert.match(ui.node('analysis').textContent, /<img/);
  function allTags(node) { return [node.tag, ...node.children.flatMap(allTags)]; }
  assert.equal(allTags(ui.node('analysis')).includes('img'), false);
});

test('loading disables duplicate submission and hides the previous result; 422 clears success', async () => {
  const ui = page();
  await withFetch(async () => reply(200, completed()), () => ui.submit());
  let finish;
  let calls = 0;
  await withFetch(() => { calls++; return new Promise(resolve => { finish = resolve; }); }, async () => {
    const pending = ui.submit();
    assert.equal(ui.node('submit').disabled, true);
    assert.equal(ui.node('analysis-form').attributes['aria-busy'], 'true');
    assert.equal(ui.node('result').hidden, true);
    await ui.submit();
    assert.equal(calls, 1);
    finish(reply(422, { detail: [{ loc: ['body', 'requirement_text'], msg: 'Blank' }] }));
    await pending;
  });
  assert.equal(ui.node('error').hidden, false);
  assert.equal(ui.node('result').hidden, true);
  assert.equal(ui.node('submit').disabled, false);
  assert.equal(ui.node('analysis-form').attributes['aria-busy'], 'false');
});

test('unsupported result replaces completed analysis instead of retaining stale content', async () => {
  const ui = page();
  await withFetch(async () => reply(200, completed()), () => ui.submit());
  await withFetch(async () => reply(200, { ...completed(), status: 'unsupported_fixture', analysis: null }), () => ui.submit());
  assert.equal(ui.node('status').textContent, 'unsupported_fixture');
  assert.match(ui.node('result-summary').textContent, /No AI analysis was performed/);
  assert.equal(ui.node('analysis').textContent, '');
});
