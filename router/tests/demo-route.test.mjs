// Tests for api/demo-route.js (the public /demo backend). No network: fetch is faked.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const handler = require('../../api/demo-route.js');
const { splitClauses, estimateSavings, decide, createRateLimiter, route, MAX_PROMPT_CHARS } = handler.helpers;

const EASY = 'Write a Python function that reverses a string';
const HARD = 'explain the tradeoffs of a lock-free queue design for our distributed scheduler';

function jevAnswer(choice, conf, ctx = 0.05) {
  return { answers: { route: { choice, probabilities: { [choice]: conf } }, needs_context: { noul: ctx } }, usage: { cost: 0.00002 } };
}

function fakeFetch({ jev, chat = [] }) {
  const calls = [];
  const fn = async (url, init) => {
    const body = JSON.parse(init.body);
    calls.push({ url, body });
    if (url.endsWith('/alpha/decisions')) {
      const reply = jev(body.state);
      return { ok: true, json: async () => reply };
    }
    const next = chat.shift() || { ok: true, data: { choices: [{ message: { content: 'def rev(s): return s[::-1]' } }], usage: { cost: 0.000005 } } };
    return { ok: next.ok, status: next.status || 200, json: async () => next.data };
  };
  fn.calls = calls;
  return fn;
}

test('clauses split on the same joiners as the Python router', () => {
  assert.deepEqual(splitClauses(`${EASY}, then ${HARD}`), [EASY, HARD]);
  assert.deepEqual(splitClauses(`${EASY} and then ${HARD}`), [EASY, HARD]);
  assert.deepEqual(splitClauses('Rebrand then ship'), ['Rebrand then ship']);
});

test('savings use the same formula as router/tracker.py', () => {
  const s = estimateSavings('a'.repeat(400), 'b'.repeat(400), 0);
  assert.equal(s.claude_equivalent_usd, 0.0018);
  assert.equal(s.saved_per_1000_usd, 1.8);
  assert.equal(s.tokens_off_claude, 200);
  assert.equal(estimateSavings('a'.repeat(4), '', 5).saved_usd, 0);
});

test('free that needs outside context goes to Claude; unsure free stays with Claude', () => {
  assert.equal(decide({ route: { choice: 'free', probabilities: { free: 0.9 } }, needs_context: { noul: 0.93 } }).routing, 'claude');
  assert.equal(decide({ route: { choice: 'free', probabilities: { free: 0.4 } }, needs_context: { noul: 0 } }).routing, 'claude');
  assert.equal(decide(null).routing, 'claude');
  assert.equal(decide({ route: { choice: 'free', probabilities: { free: 0.98 } }, needs_context: { noul: 0.02 } }).routing, 'free');
});

test('a mixed prompt sends only the easy clause to the cheap model', async () => {
  const fetchImpl = fakeFetch({ jev: state => (state.includes('lock-free') ? jevAnswer('claude', 0.95, 0.4) : jevAnswer('free', 0.99)) });
  const out = await route(`${EASY}, then ${HARD}`, { key: 'k', fetchImpl });
  assert.equal(out.routing, 'split');
  assert.equal(out.free_prompt, EASY);
  assert.equal(out.claude_prompt, HARD);
  const chat = fetchImpl.calls.filter(c => c.url.endsWith('/chat/completions'));
  assert.equal(chat.length, 1);
  assert.equal(chat[0].body.messages[1].content, EASY);
  assert.equal(chat[0].body.max_tokens, 500);
  assert.deepEqual(chat[0].body.reasoning, { effort: 'low' });
  assert.ok(out.savings.saved_usd > 0);
  assert.equal(out.cost_usd, 0.000045);
});

test('the cascade falls through a failing model', async () => {
  const fetchImpl = fakeFetch({ jev: () => jevAnswer('free', 0.99), chat: [{ ok: false, status: 429, data: {} }] });
  const out = await route(EASY, { key: 'k', models: ['a/one', 'b/two'], fetchImpl });
  assert.equal(out.model_used, 'b/two');
  assert.deepEqual(out.attempts.map(a => a.status), ['failed', 'ok']);
});

test('all-Claude prompts never call a cheap model', async () => {
  const fetchImpl = fakeFetch({ jev: () => jevAnswer('claude', 0.9) });
  const out = await route(HARD, { key: 'k', fetchImpl });
  assert.equal(out.routing, 'claude');
  assert.equal(out.routed, false);
  assert.equal(out.savings, null);
  assert.equal(fetchImpl.calls.filter(c => c.url.endsWith('/chat/completions')).length, 0);
});

test('rate limiter caps per minute, per day, and per instance', () => {
  let t = 0;
  const allow = createRateLimiter({ perMinute: 2, perDay: 3, instancePerDay: 4 }, () => t);
  assert.ok(allow('a').ok); assert.ok(allow('a').ok);
  assert.equal(allow('a').ok, false);
  t += 61_000;
  assert.ok(allow('a').ok);
  t += 61_000;
  assert.equal(allow('a').ok, false);
  assert.ok(allow('b').ok);
  assert.equal(allow('c').ok, false);
});

function fakeResponse() {
  const res = { code: 0, payload: null, headers: {} };
  res.setHeader = (k, v) => { res.headers[k] = v; };
  res.status = code => { res.code = code; return res; };
  res.json = payload => { res.payload = payload; return res; };
  return res;
}

test('handler refuses without a key, spends nothing, and checks the prompt', async () => {
  const saved = process.env.WATERFALL_DEMO_OPENROUTER_KEY;
  delete process.env.WATERFALL_DEMO_OPENROUTER_KEY;
  let res = fakeResponse();
  await handler({ method: 'POST', body: { prompt: EASY }, headers: {} }, res);
  assert.equal(res.code, 503);
  process.env.WATERFALL_DEMO_OPENROUTER_KEY = 'k';
  res = fakeResponse();
  await handler({ method: 'GET', body: {}, headers: {} }, res);
  assert.equal(res.code, 405);
  res = fakeResponse();
  await handler({ method: 'POST', body: { prompt: 'x'.repeat(MAX_PROMPT_CHARS + 1) }, headers: {} }, res);
  assert.equal(res.code, 400);
  res = fakeResponse();
  await handler({ method: 'POST', body: { prompt: '   ' }, headers: {} }, res);
  assert.equal(res.code, 400);
  if (saved === undefined) delete process.env.WATERFALL_DEMO_OPENROUTER_KEY; else process.env.WATERFALL_DEMO_OPENROUTER_KEY = saved;
});
