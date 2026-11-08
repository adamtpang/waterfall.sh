// /demo page: posts the prompt to /api/demo-route and renders the split and savings.
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $('demo-form');
  const input = $('demo-prompt');
  const run = $('demo-run');
  const status = $('demo-status');
  const result = $('demo-result');

  function usd(n) {
    if (!n) return '$0';
    if (n < 0.01) return '$' + Number(n).toFixed(6).replace(/0+$/, '');
    return '$' + Number(n).toFixed(2);
  }

  function count() { $('demo-count').textContent = input.value.length + ' / 600'; }

  function render(d) {
    result.hidden = false;
    const savings = $('demo-savings');
    if (d.savings) {
      savings.className = 'demo-savings good';
      savings.textContent = '';
      const big = document.createElement('p');
      big.className = 'demo-big';
      big.textContent = 'On Claude ' + usd(d.savings.claude_equivalent_usd) + '  ·  Here ' + usd(d.savings.actual_usd) + '  ·  Saved ' + usd(d.savings.saved_usd);
      const sub = document.createElement('p');
      sub.className = 'demo-sub';
      sub.textContent = '~' + d.savings.tokens_off_claude + ' tokens Claude never read or wrote. ' + usd(d.savings.saved_per_1000_usd) + ' per 1,000 prompts like this, at Sonnet list prices.';
      savings.append(big, sub);
    } else {
      savings.className = 'demo-savings';
      savings.textContent = d.routing === 'claude'
        ? 'All of this needs Claude, so nothing was sent to a cheap model. That is the right call too.'
        : 'No cheap model answered this time. Try again in a moment.';
    }
    $('demo-free-ask').textContent = d.free_prompt || 'Nothing. This one needs Claude.';
    const answer = $('demo-free-answer');
    answer.hidden = !d.free_response;
    answer.textContent = d.free_response || '';
    const tried = (d.attempts || []).filter((a) => a.status === 'failed').map((a) => a.model.split('/').pop() + ' (' + a.reason + ')');
    $('demo-model').textContent = d.model_used
      ? 'Answered by ' + d.model_used + ' in ' + d.seconds + 's' + (tried.length ? '. Skipped: ' + tried.join(', ') : '')
      : '';
    $('demo-claude-ask').textContent = d.claude_prompt || 'Nothing. The cheap model handled all of it.';
    const parts = $('demo-parts');
    parts.textContent = '';
    (d.parts || []).forEach((p) => {
      const li = document.createElement('li');
      const tag = document.createElement('span');
      tag.className = 'demo-tag ' + (p.routing === 'free' ? 'free' : 'claude');
      tag.textContent = (p.routing === 'free' ? 'cheap' : 'Claude') + (p.source === 'jev' ? ' · Jev ' + Math.round(p.confidence * 100) + '%' : ' · safe default');
      const text = document.createElement('span');
      text.textContent = p.text;
      li.append(tag, text);
      parts.append(li);
    });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const prompt = input.value.trim();
    if (!prompt) { status.textContent = 'Type a prompt first.'; return; }
    run.disabled = true;
    status.textContent = 'Asking Jev, then the cheapest model that can do it...';
    try {
      const res = await fetch('/api/demo-route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { status.textContent = data.error || 'Something went wrong. Try again.'; return; }
      status.textContent = '';
      render(data);
    } catch {
      status.textContent = 'Could not reach the demo. Check your connection and try again.';
    } finally {
      run.disabled = false;
    }
  });

  document.querySelectorAll('.demo-chip').forEach((chip) => {
    chip.addEventListener('click', () => { input.value = chip.dataset.prompt; count(); input.focus(); });
  });
  input.addEventListener('input', count);
  input.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') form.requestSubmit(); });
  count();
})();
