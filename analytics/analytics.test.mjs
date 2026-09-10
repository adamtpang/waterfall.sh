import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { startAnalytics } from './analytics.mjs';

function setup(url, token = 'public-test-token') {
  let config;
  let calls = 0;
  const enabled = startAnalytics({ init(_token, options) { calls++; config = options; } }, new URL(url), token);
  return { enabled, calls, config };
}

test('unsupported hosts, private paths, and missing token never initialize', () => {
  for (const url of ['https://localhost/', 'https://preview.vercel.app/', 'https://waterfall.sh.evil.example/', 'https://waterfall.sh/admin', 'https://waterfall.sh/api/leaderboard.json']) {
    assert.deepEqual(setup(url), { enabled: false, calls: 0, config: undefined });
  }
  assert.equal(setup('https://waterfall.sh/', '').calls, 0);
});

test('only a single manual pageview is requested when the SDK loads', () => {
  const { config, calls } = setup('https://waterfall.sh/');
  const captured = [];
  assert.equal(calls, 1);
  assert.equal(config.capture_pageview, false);
  assert.equal(config.capture_pageleave, false);
  assert.equal(config.autocapture, false);
  assert.equal(config.cookieless_mode, 'always');
  assert.equal(config.person_profiles, 'never');
  assert.equal(config.disable_session_recording, true);
  config.loaded({ capture(...args) { captured.push(args); } });
  assert.deepEqual(captured, [['$pageview']]);
  assert.equal(config.before_send(null), null);
  assert.equal(config.before_send({ event: '$autocapture', properties: { input: 'private' } }), null);
});

test('pageviews strip query, fragment, attribution and referrer data while preserving actual host', () => {
  const { config } = setup('https://www.waterfall.sh/about.html?email=private%40example.com#secret');
  const event = config.before_send({ event: '$pageview', properties: {
    $current_url: 'https://www.waterfall.sh/about.html?email=private%40example.com#secret',
    $referrer: 'https://example.com/private', $referring_domain: 'example.com',
    $initial_current_url: 'https://example.com/?private', utm_source: 'private',
    gclid: 'private', fbclid: 'private', msclkid: 'private', $browser: 'Firefox'
  } });
  assert.deepEqual(event.properties, {
    $current_url: 'https://www.waterfall.sh/about', $pathname: '/about',
    $host: 'www.waterfall.sh', hostname: 'www.waterfall.sh', site_id: 'waterfall.sh', $browser: 'Firefox'
  });
});

test('every sitemap page is allowed and includes exactly one tracker', () => {
  const sitemap = readFileSync(new URL('../sitemap.xml', import.meta.url), 'utf8');
  const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => new URL(match[1]));
  assert.ok(urls.length > 0);
  for (const url of urls) {
    assert.equal(setup(url.href).enabled, true, url.pathname);
    const file = url.pathname.endsWith('/') ? `${url.pathname}index.html` : `${url.pathname}.html`;
    const html = readFileSync(new URL(`..${file}`, import.meta.url), 'utf8');
    assert.equal((html.match(/<script src="\/site-analytics\.js" defer><\/script>/g) || []).length, 1, file);
  }
});
