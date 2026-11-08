// Public /demo backend: the same routing idea as the local app, sized for strangers.
// 1. Split the prompt into clauses (same joiners as router/classifier/classifier.py).
// 2. Ask Jev on OpenRouter whether each clause is cheap work or Claude work.
// 3. Send only the cheap clauses through a short cascade of cheap OpenRouter models.
// 4. Report what the routed part would have cost on Claude and what it cost here.
// Abuse limits: prompt length cap, clause cap, per-visitor and per-instance rate
// limits, cheap models only, a short answer cap, and a dedicated OpenRouter key
// (WATERFALL_DEMO_OPENROUTER_KEY) that should carry a hard credit limit set in
// OpenRouter. With no key the endpoint answers 503 and spends nothing.

const OPENROUTER = 'https://openrouter.ai/api';
const JEV_MODEL = '~typesafe/jev-latest';
const MAX_PROMPT_CHARS = 600;
const MAX_CLAUSES = 4;
const MAX_ANSWER_TOKENS = 500;
const JEV_THRESHOLD = 0.5;
const CONTEXT_CUTOFF = 0.5;
const DEFAULT_MODELS = ['z-ai/glm-5.3-flash', 'deepseek/deepseek-v4-flash', 'google/gemini-3.8-flash'];
// Sonnet list prices, the same display estimate as router/tracker.py.
const CLAUDE_IN_PER_TOKEN = 3e-6;
const CLAUDE_OUT_PER_TOKEN = 15e-6;
const LIMITS = { perMinute: 5, perDay: 30, instancePerDay: 400 };

const CLAUSE_JOINER = /\s*(?:[,;]\s*(?:and\s+)?then\s+|(?<![A-Za-z])and\s+then\s+|;\s+)/;

const JEV_QUESTIONS = {
  route: {
    type: 'choice',
    instructions: 'A developer is about to send this request to an expensive frontier coding model. Who should handle it?',
    criteria: {
      free: 'Small, self-contained, mechanical. A cheap model can do all of it from the text alone.',
      claude: 'Needs deep reasoning, broad codebase context, or careful judgment.',
    },
  },
  needs_context: {
    type: 'noul',
    instructions: 'Does answering this require seeing the repository, prior conversation, or files that are not included in the text itself?',
  },
};

function splitClauses(prompt) {
  const sentences = String(prompt).trim().split(/(?<=[.!?])\s+/);
  const out = [];
  for (const sentence of sentences) {
    for (const clause of sentence.split(CLAUSE_JOINER)) {
      const text = clause.trim();
      if (text) out.push(text);
    }
  }
  return out;
}

function tokens(text) {
  return text ? Math.max(1, Math.floor(text.length / 4)) : 0;
}

function estimateSavings(freePrompt, freeResponse, actualUsd) {
  const tokensIn = tokens(freePrompt);
  const tokensOut = tokens(freeResponse);
  const claudeUsd = tokensIn * CLAUDE_IN_PER_TOKEN + tokensOut * CLAUDE_OUT_PER_TOKEN;
  const saved = Math.max(0, claudeUsd - (actualUsd || 0));
  const round = (n, d) => Number(n.toFixed(d));
  return {
    claude_equivalent_usd: round(claudeUsd, 6),
    actual_usd: round(actualUsd || 0, 6),
    saved_usd: round(saved, 6),
    saved_per_1000_usd: round(saved * 1000, 2),
    tokens_off_claude: tokensIn + tokensOut,
  };
}

function decide(answer) {
  // Same rule as router/jev.py: a "free" verdict on text that needs outside
  // context goes to Claude; an unsure verdict stays with Claude (the safe side).
  if (!answer) return { routing: 'claude', confidence: 0, source: 'fallback' };
  let routing = answer.route?.choice === 'free' ? 'free' : 'claude';
  const probs = answer.route?.probabilities || {};
  let confidence = Math.max(0, ...Object.values(probs).map(Number).filter(Number.isFinite));
  const needsContext = Number(answer.needs_context?.noul ?? 0);
  if (routing === 'free' && needsContext >= CONTEXT_CUTOFF) {
    routing = 'claude';
    confidence = needsContext;
  }
  if (routing === 'free' && confidence < JEV_THRESHOLD) return { routing: 'claude', confidence, source: 'jev-unsure' };
  return { routing, confidence: Number(confidence.toFixed(2)), source: 'jev' };
}

function createRateLimiter(limits = LIMITS, now = () => Date.now()) {
  const visitors = new Map();
  let day = Math.floor(now() / 86_400_000);
  let instanceCount = 0;
  return function allow(visitor) {
    const t = now();
    const today = Math.floor(t / 86_400_000);
    if (today !== day) { day = today; instanceCount = 0; visitors.clear(); }
    if (instanceCount >= limits.instancePerDay) return { ok: false, reason: 'The demo hit its daily limit. Try again tomorrow.' };
    const v = visitors.get(visitor) || { minute: [], dayCount: 0 };
    v.minute = v.minute.filter(ts => t - ts < 60_000);
    if (v.dayCount >= limits.perDay) return { ok: false, reason: 'You hit the daily demo limit. Try again tomorrow.' };
    if (v.minute.length >= limits.perMinute) return { ok: false, reason: 'Slow down a little: a few tries per minute.' };
    v.minute.push(t);
    v.dayCount += 1;
    instanceCount += 1;
    visitors.set(visitor, v);
    if (visitors.size > 5000) visitors.delete(visitors.keys().next().value);
    return { ok: true };
  };
}

async function askJev(clause, key, fetchImpl) {
  try {
    const res = await fetchImpl(`${OPENROUTER}/alpha/decisions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: JEV_MODEL, state: clause, questions: JEV_QUESTIONS }),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return { answer: null, cost: 0 };
    const data = await res.json();
    return { answer: data.answers || null, cost: Number(data.usage?.cost || 0) };
  } catch {
    return { answer: null, cost: 0 };
  }
}

async function cheapAnswer(task, key, models, fetchImpl) {
  const attempts = [];
  for (const model of models) {
    const started = Date.now();
    try {
      const res = await fetchImpl(`${OPENROUTER}/v1/chat/completions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          max_tokens: MAX_ANSWER_TOKENS,
          reasoning: { effort: 'low' },
          usage: { include: true },
          messages: [
            { role: 'system', content: 'You handle the routine part of a coding task. Be direct and short. Code first, at most two sentences of explanation.' },
            { role: 'user', content: task },
          ],
        }),
        signal: AbortSignal.timeout(20000),
      });
      const seconds = Number(((Date.now() - started) / 1000).toFixed(2));
      if (!res.ok) { attempts.push({ model, status: 'failed', reason: `HTTP ${res.status}`, seconds }); continue; }
      const data = await res.json();
      const text = String(data.choices?.[0]?.message?.content || '').trim();
      if (!text) { attempts.push({ model, status: 'failed', reason: 'empty answer', seconds }); continue; }
      attempts.push({ model, status: 'ok', seconds });
      return {
        text, model, attempts,
        cost: Number(data.usage?.cost || 0),
        tokensIn: Number(data.usage?.prompt_tokens || 0),
        tokensOut: Number(data.usage?.completion_tokens || 0),
        seconds,
      };
    } catch (error) {
      attempts.push({ model, status: 'failed', reason: error?.name === 'TimeoutError' ? 'timed out' : 'network error', seconds: Number(((Date.now() - started) / 1000).toFixed(2)) });
    }
  }
  return { text: '', model: '', attempts, cost: 0, tokensIn: 0, tokensOut: 0, seconds: 0 };
}

async function route(prompt, { key, models = DEFAULT_MODELS, fetchImpl = fetch } = {}) {
  const clauses = splitClauses(prompt).slice(0, MAX_CLAUSES);
  const verdicts = await Promise.all(clauses.map(clause => askJev(clause, key, fetchImpl)));
  const parts = clauses.map((text, i) => ({ text, ...decide(verdicts[i].answer) }));
  const jevCost = verdicts.reduce((sum, v) => sum + v.cost, 0);
  const free = parts.filter(p => p.routing === 'free').map(p => p.text);
  const hard = parts.filter(p => p.routing === 'claude').map(p => p.text);
  const routing = free.length && hard.length ? 'split' : free.length ? 'free' : 'claude';
  const freePrompt = free.join('\n\n');
  const answer = freePrompt ? await cheapAnswer(freePrompt, key, models, fetchImpl) : null;
  const routed = Boolean(answer && answer.text);
  const actual = (answer ? answer.cost : 0) + jevCost;
  return {
    routing,
    parts,
    free_prompt: freePrompt,
    claude_prompt: hard.join('\n\n'),
    free_response: routed ? answer.text : '',
    model_used: routed ? answer.model : '',
    attempts: answer ? answer.attempts : [],
    seconds: answer ? answer.seconds : 0,
    jev_cost_usd: Number(jevCost.toFixed(6)),
    cost_usd: Number(actual.toFixed(6)),
    routed,
    savings: routed ? estimateSavings(freePrompt, answer.text, actual) : null,
  };
}

const allow = createRateLimiter();

async function handler(request, response) {
  response.setHeader('Cache-Control', 'no-store');
  if (request.method !== 'POST') { response.status(405).json({ error: 'Use POST.' }); return; }
  const key = process.env.WATERFALL_DEMO_OPENROUTER_KEY;
  if (!key) { response.status(503).json({ error: 'The live demo is not switched on yet.' }); return; }
  let body = request.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = {}; } }
  const prompt = String(body?.prompt || '').trim();
  if (!prompt) { response.status(400).json({ error: 'Type a prompt first.' }); return; }
  if (prompt.length > MAX_PROMPT_CHARS) { response.status(400).json({ error: `Keep it under ${MAX_PROMPT_CHARS} characters.` }); return; }
  const visitor = String(request.headers['x-real-ip'] || request.headers['x-forwarded-for'] || 'anon').split(',')[0].trim();
  const gate = allow(visitor);
  if (!gate.ok) { response.status(429).json({ error: gate.reason }); return; }
  try {
    response.status(200).json(await route(prompt, { key }));
  } catch {
    response.status(502).json({ error: 'The model cascade failed. Try again in a moment.' });
  }
}

module.exports = handler;
module.exports.helpers = { splitClauses, estimateSavings, decide, createRateLimiter, route, MAX_PROMPT_CHARS, LIMITS };
