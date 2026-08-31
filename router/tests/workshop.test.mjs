import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const html = readFileSync(new URL('../../workshop/index.html', import.meta.url), 'utf8');
const catalog = JSON.parse(readFileSync(new URL('../../workshop/catalog.json', import.meta.url), 'utf8'));
const workshopScript = readFileSync(new URL('../../workshop/workshop.js', import.meta.url), 'utf8');

assert.match(html, /<script src="\/workshop\/workshop\.js" defer><\/script>/);


function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}


function element(initial = {}) {
  return {
    attributes: {},
    listeners: {},
    addEventListener(event, listener) {
      this.listeners[event] = listener;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    ...initial,
  };
}


function responseFor(data = catalog, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => data,
  };
}


async function settle() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}


async function makeHarness({
  href = 'https://waterfall.sh/workshop/',
  response = Promise.resolve(responseFor()),
} = {}) {
  const root = element({ innerHTML: '<div class="empty">Loading the workshop catalog...</div>' });
  const search = element({ value: '' });
  const snapshot = Object.fromEntries([
    'snapshot-checked',
    'snapshot-active',
    'snapshot-removed',
    'snapshot-public',
    'snapshot-affiliate',
  ].map(id => [id, element({ textContent: '' })]));
  const filters = ['all', 'models', 'ides', 'skills', 'mcps'].map(filter =>
    element({ dataset: { filter } }),
  );
  const location = {
    href,
    search: new URL(href).search,
  };
  const historyCalls = [];
  const context = {
    document: {
      getElementById(id) {
        if (id === 'catalog-root') return root;
        if (id === 'search') return search;
        return snapshot[id];
      },
      querySelectorAll() {
        return filters;
      },
    },
    fetch: () => response,
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
  };

  vm.runInNewContext(workshopScript, context, { filename: 'workshop/index.html' });
  await settle();
  return { filters, historyCalls, location, root, search, snapshot };
}


function pressed(harness, filter) {
  return harness.filters.find(button => button.dataset.filter === filter).attributes['aria-pressed'];
}


test('successful load renders every catalog shelf and item', async () => {
  const harness = await makeHarness();
  const itemCount = catalog.collections.reduce((count, collection) => count + collection.items.length, 0);

  assert.equal((harness.root.innerHTML.match(/<article class="card">/g) || []).length, itemCount);
  for (const collection of catalog.collections) {
    assert.match(harness.root.innerHTML, new RegExp(`data-shelf="${collection.id}"`));
  }
  assert.equal(pressed(harness, 'all'), 'true');
  assert.equal(harness.snapshot['snapshot-checked'].textContent, `Checked ${catalog.updated_at}`);
  assert.equal(harness.snapshot['snapshot-active'].textContent, String(catalog.audit.active_skills));
});


test('valid shelf deep link renders only the requested collection', async () => {
  const harness = await makeHarness({ href: 'https://waterfall.sh/workshop/?shelf=skills' });

  assert.match(harness.root.innerHTML, /data-shelf="skills"/);
  assert.doesNotMatch(harness.root.innerHTML, /data-shelf="models"/);
  const expected = catalog.collections.find(collection => collection.id === 'skills').items.length;
  assert.equal((harness.root.innerHTML.match(/<article class="card">/g) || []).length, expected);
  assert.equal(pressed(harness, 'skills'), 'true');
  assert.equal(pressed(harness, 'all'), 'false');
});


test('unknown shelf deep link falls back to the full catalog', async () => {
  const harness = await makeHarness({ href: 'https://waterfall.sh/workshop/?shelf=unknown' });

  assert.match(harness.root.innerHTML, /data-shelf="models"/);
  assert.match(harness.root.innerHTML, /data-shelf="mcps"/);
  assert.equal(pressed(harness, 'all'), 'true');
});


test('filter clicks update rendered cards, pressed state, and URL', async () => {
  const harness = await makeHarness({ href: 'https://waterfall.sh/workshop/?ref=audit' });
  const mcps = harness.filters.find(button => button.dataset.filter === 'mcps');
  const all = harness.filters.find(button => button.dataset.filter === 'all');

  mcps.listeners.click();
  assert.match(harness.root.innerHTML, /data-shelf="mcps"/);
  assert.doesNotMatch(harness.root.innerHTML, /data-shelf="skills"/);
  assert.equal(pressed(harness, 'mcps'), 'true');
  assert.equal(new URL(harness.location.href).searchParams.get('shelf'), 'mcps');
  assert.equal(new URL(harness.location.href).searchParams.get('ref'), 'audit');
  assert.equal(harness.historyCalls.length, 1);

  all.listeners.click();
  assert.match(harness.root.innerHTML, /data-shelf="skills"/);
  assert.equal(pressed(harness, 'all'), 'true');
  assert.equal(new URL(harness.location.href).searchParams.has('shelf'), false);
  assert.equal(new URL(harness.location.href).searchParams.get('ref'), 'audit');
  assert.equal(harness.historyCalls.length, 2);
});


test('search is trimmed and case-insensitive', async () => {
  const harness = await makeHarness();

  harness.search.value = '  NEON  ';
  harness.search.listeners.input();

  assert.match(harness.root.innerHTML, /Neon MCP Server/);
  assert.equal((harness.root.innerHTML.match(/<article class="card">/g) || []).length, 1);
});


test('search covers publisher, role, evidence, negative case, and tags', async () => {
  const harness = await makeHarness();
  const cases = [
    ['moonshot ai', 'Kimi K3 Max'],
    ['generic postgresql access', 'Microsoft Postgres MCP'],
    ['praise-versus-complaint', 'GPT-5.6 Sol xHigh'],
    ['ephemeral branch', 'Neon MCP Server'],
    ['third-opinion', 'Kimi K3 Max'],
  ];

  for (const [query, expected] of cases) {
    harness.search.value = query;
    harness.search.listeners.input();
    assert.match(harness.root.innerHTML, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});


test('search with no matches renders the recoverable empty state', async () => {
  const harness = await makeHarness();

  harness.search.value = 'definitely-not-in-the-workshop';
  harness.search.listeners.input();

  assert.equal(harness.root.innerHTML, '<div class="empty">No entries match that search.</div>');
});


test('interaction before fetch completion is safe and applies after load', async () => {
  const pending = deferred();
  const harness = await makeHarness({ response: pending.promise });
  const models = harness.filters.find(button => button.dataset.filter === 'models');

  models.listeners.click();
  assert.match(harness.root.innerHTML, /Loading the workshop catalog/);
  assert.equal(new URL(harness.location.href).searchParams.get('shelf'), 'models');

  pending.resolve(responseFor());
  await settle();

  assert.match(harness.root.innerHTML, /data-shelf="models"/);
  assert.doesNotMatch(harness.root.innerHTML, /data-shelf="ides"/);
});


test('HTTP failures show direct catalog and README recovery links', async () => {
  const harness = await makeHarness({ response: Promise.resolve(responseFor(catalog, { ok: false, status: 503 })) });

  assert.match(harness.root.innerHTML, /interactive catalog could not load/);
  assert.match(harness.root.innerHTML, /href="\/workshop\/catalog\.json"/);
  assert.match(harness.root.innerHTML, /href="\/workshop\/README\.md"/);
});


test('network and JSON failures use the same recoverable error state', async () => {
  const network = await makeHarness({ response: Promise.reject(new Error('offline')) });
  const invalidJson = await makeHarness({
    response: Promise.resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad json'); } }),
  });

  assert.match(network.root.innerHTML, /interactive catalog could not load/);
  assert.match(invalidJson.root.innerHTML, /interactive catalog could not load/);
});


test('catalog values and tags are escaped before insertion into HTML', async () => {
  const unsafeCatalog = {
    updated_at: catalog.updated_at,
    audit: catalog.audit,
    collections: [{
      id: 'models',
      title: '<Models>',
      summary: 'A & B',
      items: [{
        name: '<img src=x onerror=alert(1)>',
        publisher: '"publisher"',
        role: "owner's role",
        evidence: '<script>alert(1)</script>',
        avoid: 'x & y',
        default_state: 'daily" onclick="alert(1)',
        url: 'https://example.com/?a=1&b=2',
        checked_at: '2026-08-31',
        tags: ['<unsafe>'],
      }],
    }],
  };
  const harness = await makeHarness({ response: Promise.resolve(responseFor(unsafeCatalog)) });

  assert.doesNotMatch(harness.root.innerHTML, /<script>alert/);
  assert.doesNotMatch(harness.root.innerHTML, /<img src=x/);
  assert.match(harness.root.innerHTML, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(harness.root.innerHTML, /&lt;unsafe&gt;/);
  assert.match(harness.root.innerHTML, /a=1&amp;b=2/);
  assert.match(harness.root.innerHTML, /&quot;publisher&quot;/);
  assert.match(harness.root.innerHTML, /owner&#39;s role/);
  assert.doesNotMatch(harness.root.innerHTML, /onclick="alert/);
});


test('missing optional tags and an empty collection render safely', async () => {
  const noTags = structuredClone(catalog);
  delete noTags.collections[0].items[0].tags;
  const taggedHarness = await makeHarness({ response: Promise.resolve(responseFor(noTags)) });
  assert.match(taggedHarness.root.innerHTML, /Agent Arena/);

  const emptyHarness = await makeHarness({
    response: Promise.resolve(responseFor({
      updated_at: catalog.updated_at,
      audit: catalog.audit,
      collections: [{ id: 'models', title: 'Models', summary: '', items: [] }],
    })),
  });
  assert.equal(emptyHarness.root.innerHTML, '<div class="empty">No entries match that search.</div>');
});


test('malformed tags use the recoverable load-failure state', async () => {
  const malformed = structuredClone(catalog);
  malformed.collections[0].items[0].tags = 'agent';
  const harness = await makeHarness({ response: Promise.resolve(responseFor(malformed)) });

  assert.match(harness.root.innerHTML, /interactive catalog could not load/);
});
