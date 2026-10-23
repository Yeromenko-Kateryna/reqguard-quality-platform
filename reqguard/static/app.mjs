const uncertainOutcome = 'The request may have reached the server. Check before submitting again; no automatic retry was made.';

function failure(title, message, details = []) {
  return { kind: 'error', title, message, details };
}

function validResult(body) {
  if (!body || typeof body.run_id !== 'string' || !body.run_id || body.provider !== 'fake') return false;
  if (body.status === 'unsupported_fixture') return body.analysis === null;
  const analysis = body.analysis;
  return body.status === 'completed' && analysis &&
    Array.isArray(analysis.ambiguities) && analysis.ambiguities.every(item =>
      item && typeof item.term === 'string' && typeof item.explanation === 'string') &&
    Array.isArray(analysis.missing_measurable_criteria) && analysis.missing_measurable_criteria.every(item => typeof item === 'string') &&
    Array.isArray(analysis.candidate_test_scenarios) && analysis.candidate_test_scenarios.every(item =>
      item && typeof item.title === 'string' && typeof item.expected_result === 'string' &&
      Array.isArray(item.steps) && item.steps.every(step => typeof step === 'string'));
}

// Kept independent of DOM APIs so request/state behavior can be tested with node:test.
export async function submitRequirement(text, { fetchImpl = globalThis.fetch, onState = () => {} } = {}) {
  onState({ kind: 'loading' });
  let response;
  let state;
  try {
    response = await fetchImpl('/analyses', {
      method: 'POST', redirect: 'error',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ requirement_text: text }),
    });
  } catch {
    state = failure('Network error', uncertainOutcome);
  }
  if (response) {
    let body;
    try { body = await response.json(); } catch { /* No raw HTML/error body is displayed. */ }
    if (!response.ok) {
      if (response.status === 422) {
        const details = Array.isArray(body?.detail) ? body.detail.map(item => {
          const location = Array.isArray(item?.loc) ? item.loc.join('.') : 'Input';
          return location + ': ' + (typeof item?.msg === 'string' ? item.msg : 'Invalid value');
        }) : [];
        state = failure('Validation failed (HTTP 422)', 'Please revise the requirement and submit again.', details);
      } else {
        state = failure('Request failed (HTTP ' + response.status + ')', uncertainOutcome);
      }
    } else if (!validResult(body)) {
      state = failure('Unexpected server response', 'No valid result was received. ' + uncertainOutcome);
    } else {
      state = { kind: 'result', body };
    }
  }
  onState(state);
  return state;
}

export function mountUI(doc) {
  const byId = id => doc.getElementById(id);
  const form = byId('analysis-form');
  const button = byId('submit');
  const element = (tag, text) => {
    const node = doc.createElement(tag);
    node.textContent = text;
    return node;
  };
  function render(state) {
    const loading = state.kind === 'loading';
    button.disabled = loading;
    button.textContent = loading ? 'Submitting…' : 'Submit requirement';
    form.setAttribute('aria-busy', String(loading));
    byId('notice').textContent = loading ? 'Submitting the requirement…' : '';
    byId('error').hidden = true;
    byId('result').hidden = true;
    byId('analysis').replaceChildren();
    byId('error-details').replaceChildren();
    if (state.kind === 'error') {
      byId('error-title').textContent = state.title;
      byId('error-message').textContent = state.message;
      for (const detail of state.details) byId('error-details').append(element('li', detail));
      byId('error').hidden = false;
    }
    if (state.kind === 'result') {
      const body = state.body;
      byId('run-id').textContent = body.run_id;
      byId('status').textContent = body.status;
      byId('provider').textContent = body.provider;
      byId('result').dataset.status = body.status;
      byId('result-summary').textContent = body.status === 'completed'
        ? 'Completed: authored analysis is available below.'
        : 'Unsupported fixture: this valid input has no authored analysis. No AI analysis was performed.';
      if (body.analysis) {
        const target = byId('analysis');
        target.append(element('h3', 'Ambiguities'));
        for (const item of body.analysis.ambiguities) {
          const paragraph = element('p', '');
          paragraph.append(element('strong', item.term), doc.createTextNode(' — ' + item.explanation));
          target.append(paragraph);
        }
        target.append(element('h3', 'Missing measurable criteria'));
        const criteria = element('ul', '');
        for (const item of body.analysis.missing_measurable_criteria) criteria.append(element('li', item));
        target.append(criteria, element('h3', 'Candidate test scenarios'));
        for (const item of body.analysis.candidate_test_scenarios) {
          target.append(element('h4', item.title));
          const steps = element('ol', '');
          for (const step of item.steps) steps.append(element('li', step));
          target.append(steps, element('p', 'Expected result: ' + item.expected_result));
        }
      }
      byId('result').hidden = false;
      byId('notice').textContent = 'Response received.';
    }
  }
  let pending = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    try {
      await submitRequirement(byId('requirement').value, { onState: render });
    } finally {
      pending = false;
    }
  });
  button.disabled = false;
}

if (typeof document !== 'undefined') mountUI(document);
