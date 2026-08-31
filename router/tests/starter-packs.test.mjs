import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const html = readFileSync(new URL('../../workshop/starter-packs.html', import.meta.url), 'utf8');
const packs = JSON.parse(readFileSync(new URL('../../workshop/packs.json', import.meta.url), 'utf8'));
const catalog = JSON.parse(readFileSync(new URL('../../workshop/catalog.json', import.meta.url), 'utf8'));
const script = readFileSync(new URL('../../workshop/starter-packs.js', import.meta.url), 'utf8');

assert.match(html, /<script src="\/workshop\/starter-packs\.js" defer><\/script>/);


function element(initial = {}) {
  return {
    attributes: {},
    listeners: {},
    innerHTML: '',
    textContent: '',
    className: '',
    value: '',
    disabled: false,
    focused: false,
    selected: false,
    addEventListener(event, listener) {
      this.listeners[event] = listener;
    },
    focus() {
      this.focused = true;
    },
    select() {
      this.selected = true;
    },
    ...initial,
  };
}


function responseFor(data, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => data };
}


async function settle() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}


async function makeHarness({
  href = 'https://waterfall.sh/workshop/starter-packs',
  packData = packs,
  catalogData = catalog,
  responseOptions = {},
  clipboard,
  execCommand,
  networkError = false,
} = {}) {
  const ids = [
    'class-grid', 'quiz-root', 'quiz-progress', 'result-title', 'result-sigil',
    'result-root', 'setup-prompt', 'copy-prompt', 'start-over', 'pack-status',
  ];
  const elements = Object.fromEntries(ids.map(id => [id, element()]));
  elements['copy-prompt'].disabled = true;
  elements['start-over'].disabled = true;
  const location = { href, search: new URL(href).search };
  const historyCalls = [];
  const fetchCalls = [];
  const context = {
    document: {
      getElementById(id) {
        return elements[id];
      },
      execCommand,
    },
    fetch(url) {
      fetchCalls.push(url);
      if (networkError) return Promise.reject(new Error('network down'));
      if (url.endsWith('packs.json')) return Promise.resolve(responseFor(packData, responseOptions.packs));
      return Promise.resolve(responseFor(catalogData, responseOptions.catalog));
    },
    navigator: { clipboard },
    history: {
      replaceState(_state, _title, url) {
        location.href = url.toString();
        location.search = url.search;
        historyCalls.push(url.toString());
      },
    },
    location,
    URL,
    URLSearchParams,
    Map,
  };
  vm.runInNewContext(script, context, { filename: 'workshop/starter-packs.html' });
  await settle();
  return { elements, fetchCalls, historyCalls, location };
}


function delegatedTarget(dataset) {
  return { closest: () => ({ dataset }) };
}


test('successful load renders six classes and the first quiz question', async () => {
  const harness = await makeHarness();

  assert.equal((harness.elements['class-grid'].innerHTML.match(/class="class-card"/g) || []).length, 6);
  assert.match(harness.elements['quiz-root'].innerHTML, new RegExp(packs.quiz[0].question));
  assert.equal(harness.elements['quiz-progress'].textContent, `1 / ${packs.quiz.length}`);
  assert.deepEqual(harness.fetchCalls, ['/workshop/packs.json', '/workshop/catalog.json']);
  assert.equal(harness.elements['pack-status'].textContent, 'Choose directly or answer the quiz.');
});


test('direct class selection builds an approval-first prompt and shareable URL', async () => {
  const harness = await makeHarness();
  harness.elements['class-grid'].listeners.click({ target: delegatedTarget({ class: 'forge-knight' }) });

  assert.equal(harness.elements['result-title'].textContent, 'Forge Knight');
  assert.equal(harness.elements['result-sigil'].textContent, 'FK');
  assert.match(harness.elements['result-root'].innerHTML, /Claude Sonnet 5 High/);
  assert.match(harness.elements['result-root'].innerHTML, /GitHub MCP Server/);
  assert.match(harness.elements['setup-prompt'].value, /Ask me to approve the proposed changes/);
  assert.match(harness.elements['setup-prompt'].value, /Do not install, authenticate, edit global configuration/);
  assert.match(harness.elements['setup-prompt'].value, /Never print, copy, commit, or publish credentials/);
  assert.equal(new URL(harness.location.href).searchParams.get('class'), 'forge-knight');
  assert.equal(harness.elements['copy-prompt'].disabled, false);
});


test('quiz scores answers and recommends the data class', async () => {
  const harness = await makeHarness();
  const quiz = harness.elements['quiz-root'];

  for (const option of ['systems', 'focused', 'connected', 'data']) {
    quiz.listeners.click({ target: delegatedTarget({ option }) });
  }

  assert.equal(harness.elements['result-title'].textContent, 'Data Druid');
  assert.match(harness.elements['result-root'].innerHTML, /Neon MCP Server/);
  assert.match(quiz.innerHTML, /Quiz complete/);
  assert.equal(new URL(harness.location.href).searchParams.get('class'), 'data-druid');
});


test('valid class deep link opens the selected starter pack', async () => {
  const harness = await makeHarness({
    href: 'https://waterfall.sh/workshop/starter-packs?class=sentinel',
  });

  assert.equal(harness.elements['result-title'].textContent, 'Sentinel');
  assert.match(harness.elements['setup-prompt'].value, /read-only inspection/);
  assert.equal(harness.historyCalls.length, 0);
});


test('copy uses the clipboard and reports success', async () => {
  let copied = '';
  const harness = await makeHarness({
    clipboard: { writeText: async value => { copied = value; } },
  });
  harness.elements['class-grid'].listeners.click({ target: delegatedTarget({ class: 'lean-ranger' }) });
  await harness.elements['copy-prompt'].listeners.click();

  assert.equal(copied, harness.elements['setup-prompt'].value);
  assert.equal(harness.elements['pack-status'].textContent, 'Setup prompt copied.');
  assert.equal(harness.elements['pack-status'].className, 'pack-status success');
});


test('copy falls back to selection and gives manual recovery when blocked', async () => {
  const fallback = await makeHarness({ execCommand: () => false });
  fallback.elements['class-grid'].listeners.click({ target: delegatedTarget({ class: 'lorekeeper' }) });
  await fallback.elements['copy-prompt'].listeners.click();

  assert.equal(fallback.elements['setup-prompt'].selected, true);
  assert.equal(fallback.elements['setup-prompt'].focused, true);
  assert.match(fallback.elements['pack-status'].textContent, /copy it manually/);
  assert.equal(fallback.elements['pack-status'].className, 'pack-status error');
});


test('HTTP, network, and malformed data failures keep raw JSON recovery links', async () => {
  const unsafeCatalog = structuredClone(catalog);
  unsafeCatalog.collections[0].items[0].url = 'javascript:alert(1)';
  const cases = [
    { responseOptions: { packs: { ok: false, status: 503 } } },
    { networkError: true },
    { packData: { archetypes: [], quiz: [] } },
    { catalogData: unsafeCatalog },
  ];
  for (const options of cases) {
    const harness = await makeHarness(options);
    assert.match(harness.elements['class-grid'].innerHTML, /packs\.json/);
    assert.match(harness.elements['quiz-root'].innerHTML, /Quiz unavailable/);
    assert.equal(harness.elements['pack-status'].className, 'pack-status error');
  }
});


test('start over clears the selection, prompt, and URL state', async () => {
  const harness = await makeHarness();
  harness.elements['class-grid'].listeners.click({ target: delegatedTarget({ class: 'guild-master' }) });
  harness.elements['start-over'].listeners.click();

  assert.equal(harness.elements['setup-prompt'].value, '');
  assert.equal(harness.elements['copy-prompt'].disabled, true);
  assert.equal(harness.elements['result-title'].textContent, 'Choose a class to begin.');
  assert.equal(new URL(harness.location.href).searchParams.has('class'), false);
  assert.match(harness.elements['quiz-root'].innerHTML, new RegExp(packs.quiz[0].question));
});
