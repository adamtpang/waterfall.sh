import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const root = new URL('../../', import.meta.url);
const html = readFileSync(new URL('leaderboard.html', root), 'utf8');
const css = readFileSync(new URL('leaderboard.css', root), 'utf8');
const script = readFileSync(new URL('leaderboard.js', root), 'utf8');
const board = JSON.parse(readFileSync(new URL('api/leaderboard.json', root), 'utf8'));


function element(initial = {}) {
  return {
    attributes: {},
    children: [],
    listeners: {},
    dataset: {},
    textContent: '',
    addEventListener(event, listener) { this.listeners[event] = listener; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    ...initial,
  };
}


async function settle() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}


async function harness() {
  const body = element();
  const status = element();
  const boardDate = element();
  const boardSource = element();
  const buttons = ['quality', 'cost_per_solved', 'solved_pct', 'value'].map(sort =>
    element({ dataset: { sort } }),
  );
  const headers = buttons.map(button => element({ dataset: { sortHeader: button.dataset.sort } }));
  const ids = {
    'leaderboard-body': body,
    'table-status': status,
    'board-date': boardDate,
    'board-source': boardSource,
  };
  const document = {
    getElementById(id) { return ids[id]; },
    createElement() { return element(); },
    querySelectorAll(selector) {
      if (selector === '[data-sort]') return buttons;
      if (selector === '[data-sort-header]') return headers;
      return [];
    },
    querySelector(selector) {
      const match = selector.match(/^\[data-sort-header="(.+)"\]$/);
      return match ? headers.find(header => header.dataset.sortHeader === match[1]) : null;
    },
  };
  vm.runInNewContext(script, {
    document,
    fetch: async () => ({ ok: true, json: async () => board }),
    Error,
    Number,
  }, { filename: 'leaderboard.js' });
  await settle();
  return { body, buttons, headers, status, boardDate, boardSource };
}


function renderedModel(row) {
  return row.children[1].children[0].textContent;
}


test('page ships a complete value-sorted no-JavaScript snapshot', () => {
  assert.match(html, /Bang for buck: coding models/);
  assert.equal((html.match(/<tr><td>/g) || []).length, 10);
  assert.match(html, /DeepSeek V4 Flash[\s\S]+Claude Fable 5\.1/);
  assert.match(html, /snapshot-2026-09-03/);
  assert.match(html, /Prices move; this row is dated/);
  assert.match(html, /value_raw = quality \/ max\(cost_per_solved, 0\.01\)/);
  assert.doesNotMatch(html + css + script, /—/);
  assert.doesNotMatch(html, /<style|<script(?![^>]+src=)/);
});


test('feed uses the exact normalized value formula', () => {
  const raw = board.rows.map(row => row.quality / Math.max(row.cost_per_solved, 0.01));
  const max = Math.max(...raw);
  board.rows.forEach((row, index) => {
    assert.equal(row.value, Math.round((1000 * raw[index]) / max) / 10);
  });
  assert.deepEqual(board.rows.map(row => row.rank), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
});


test('interactive table loads the feed and defaults to value descending', async () => {
  const page = await harness();
  assert.equal(page.body.children.length, 10);
  assert.equal(renderedModel(page.body.children[0]), 'DeepSeek V4 Flash');
  assert.equal(page.boardDate.textContent, '2026-09-03');
  assert.match(page.boardSource.textContent, /10 snapshot priors, 0 harness rows/);
  assert.match(page.status.textContent, /value descending/);
  const valueHeader = page.headers.find(header => header.dataset.sortHeader === 'value');
  assert.equal(valueHeader.attributes['aria-sort'], 'descending');
});


test('quality, solved percent, and cost per solved are sortable', async () => {
  const page = await harness();
  const quality = page.buttons.find(button => button.dataset.sort === 'quality');
  quality.listeners.click();
  assert.equal(renderedModel(page.body.children[0]), 'Claude Fable 5.1');

  const solved = page.buttons.find(button => button.dataset.sort === 'solved_pct');
  solved.listeners.click();
  assert.equal(renderedModel(page.body.children[0]), 'Claude Fable 5.1');

  const cost = page.buttons.find(button => button.dataset.sort === 'cost_per_solved');
  cost.listeners.click();
  assert.equal(renderedModel(page.body.children[0]), 'DeepSeek V4 Flash');
});


test('badge endpoint returns a model-specific SVG and 404s unknown models', () => {
  const require = createRequire(import.meta.url);
  const handler = require('../../api/badge.js');
  function response() {
    return {
      headers: {}, statusCode: 0, body: '',
      setHeader(key, value) { this.headers[key] = value; },
      status(code) { this.statusCode = code; return this; },
      send(value) { this.body = value; },
    };
  }

  const found = response();
  handler({ query: { model: 'grok-4.6' } }, found);
  assert.equal(found.statusCode, 200);
  assert.match(found.headers['Content-Type'], /image\/svg\+xml/);
  assert.match(found.body, /Grok 4\.6 value/);

  const missing = response();
  handler({ query: { model: 'made-up-model' } }, missing);
  assert.equal(missing.statusCode, 404);
  assert.match(missing.body, /not found/);
});


test('read-only feed handler serves JSON and CSV with explicit content types', () => {
  const require = createRequire(import.meta.url);
  const handler = require('../../api/leaderboard-feed.js');
  function response() {
    return {
      headers: {}, statusCode: 0, body: '',
      setHeader(key, value) { this.headers[key] = value; },
      status(code) { this.statusCode = code; return this; },
      send(value) { this.body = value; },
    };
  }

  const json = response();
  handler({ query: { format: 'json' } }, json);
  assert.equal(json.statusCode, 200);
  assert.match(json.headers['Content-Type'], /application\/json/);
  assert.equal(JSON.parse(json.body).rows.length, 10);

  const csv = response();
  handler({ query: { format: 'csv' } }, csv);
  assert.equal(csv.statusCode, 200);
  assert.match(csv.headers['Content-Type'], /text\/csv/);
  assert.match(csv.body, /^rank,model,effort,quality/);
  assert.match(csv.body, /Grok 4\.6/);
});
