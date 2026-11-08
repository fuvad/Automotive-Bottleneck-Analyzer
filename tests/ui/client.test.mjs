import test from 'node:test';
import assert from 'node:assert/strict';
import {api, APIError, makeRequest, pollOnce, retryDelay, contextParent, utcInput} from '../../src/bottleneck_analyzer/api/static/client.mjs';

test('constructs scope and both scenarios without changing defaults', () => {
  for (const method of ['repair_duration', 'failure_rate']) {
    const request = makeRequest({dataset: 'fixture', question: 'Analyze', hours: '4,5,4', scenario: true, target: 'Hemming', method, percentage: 30});
    assert.deepEqual(request.scope.utc_hours, [4,5]);
    assert.equal(request.scenario.request.method, method);
    assert.equal(request.scenario.days, undefined);
  }
  assert.throws(() => makeRequest({hours: '25'}));
  assert.throws(() => makeRequest({scenario: true}));
});
test('active and unconfirmed polls never POST or invent completion', async () => {
  for (const execution of ['active', 'unconfirmed', 'not_started']) {
    const paths = [];
    const view = await pollOnce('id', async path => { paths.push(path); return {payload: {final_confirmed: false, execution}}; });
    assert.equal(view.keepPolling, execution === 'active');
    assert.equal(view.result, null);
    assert.deepEqual(paths, ['/api/investigations/id']);
  }
});
test('all terminal outcomes are retrieved by GET with metrics unchanged', async () => {
  for (const outcome of ['completed', 'incomplete', 'clarification_required', 'unsupported', 'failed']) {
    const view = await pollOnce('id', async path => path.endsWith('/result') ? {status: 200, payload: {outcome, historical: {historical_jph: 46.88}, simulation: {baseline: {mean: 46.255889}}}} : {payload: {final_confirmed: true}});
    assert.equal(view.result.outcome, outcome);
    assert.equal(view.result.historical.historical_jph, 46.88);
    assert.equal(view.result.simulation.baseline.mean, 46.255889);
  }
});
test('HTTP errors retain API status and safe code; no implicit retries', async () => {
  let calls = 0;
  await assert.rejects(api('/api/datasets', {}, async () => {
    calls++; return {ok: false, status: 503, json: async () => ({error: {code: 'unavailable', message: 'Database unavailable'}})};
  }), error => error instanceof APIError && error.status === 503 && error.code === 'unavailable');
  assert.equal(calls, 1);
  assert.deepEqual([0,1,2,3,4].map(retryDelay), [2000,4000,8000,10000,10000]);
});

test('follow-ups use only a confirmed parent in the same dataset and period', () => {
  const scope = {dataset: 'fixture', start_time: '2026-09-01T00:00:00Z', end_time: '2026-10-01T00:00:00Z'};
  const turn = {id: 'parent', final: true, scope};
  assert.equal(contextParent([turn], scope), 'parent');
  assert.equal(contextParent([turn], {...scope, dataset: 'other'}), undefined);
  assert.equal(contextParent([turn], {...scope, end_time: '2026-09-02T00:00:00Z'}), undefined);
  assert.equal(contextParent([{...turn, final: false}], scope), undefined);
  assert.equal(contextParent([], scope), undefined);
  assert.equal(makeRequest({...scope, question: 'Why?', previous_investigation_id: 'parent'}).previous_investigation_id, 'parent');
  assert.equal(makeRequest({...scope, question: 'New chat'}).previous_investigation_id, undefined);
});

test('UTC selectors normalize timezone offsets before displaying wall time', () => {
  assert.equal(utcInput('2026-09-01T05:30:00+05:30'), '2026-09-01T00:00:00');
  assert.equal(utcInput('2026-09-01T00:00:00Z'), '2026-09-01T00:00:00');
});
