(() => {
  const classGrid = document.getElementById('class-grid');
  const quizRoot = document.getElementById('quiz-root');
  const quizProgress = document.getElementById('quiz-progress');
  const resultTitle = document.getElementById('result-title');
  const resultSigil = document.getElementById('result-sigil');
  const resultRoot = document.getElementById('result-root');
  const promptField = document.getElementById('setup-prompt');
  const copyButton = document.getElementById('copy-prompt');
  const startOverButton = document.getElementById('start-over');
  const status = document.getElementById('pack-status');

  let packs = null;
  let catalogById = new Map();
  let questionIndex = 0;
  let scores = {};
  let selectedId = null;

  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
  const safeHref = (value) => {
    const href = String(value);
    return href.startsWith('https://') || href.startsWith('/workshop/') ? href : null;
  };

  const setStatus = (message, kind = '') => {
    status.textContent = message;
    status.className = `pack-status${kind ? ` ${kind}` : ''}`;
  };

  const validateData = (packData, catalogData) => {
    if (!packData || !Array.isArray(packData.archetypes) || !packData.archetypes.length || !Array.isArray(packData.quiz)) {
      throw new Error('Invalid starter pack data');
    }
    if (!catalogData || !Array.isArray(catalogData.collections)) throw new Error('Invalid catalog data');
    const items = catalogData.collections.flatMap(collection => collection.items || []);
    if (!items.length) throw new Error('Empty catalog');
    if (items.some(item => !safeHref(item.url))) throw new Error('Invalid catalog source URL');
    const itemMap = new Map(items.map(item => [item.id, item]));
    const referencesExist = packData.archetypes.every(archetype =>
      Array.isArray(archetype.catalog_ids) && archetype.catalog_ids.every(id => itemMap.has(id)),
    );
    if (!referencesExist) throw new Error('Unknown starter pack catalog reference');
    return itemMap;
  };

  const renderClasses = () => {
    classGrid.innerHTML = packs.archetypes.map(archetype => `<button class="class-card" type="button" data-class="${escapeHtml(archetype.id)}" aria-pressed="${String(archetype.id === selectedId)}">
      <span class="class-card-top"><span class="class-sigil" aria-hidden="true">${escapeHtml(archetype.sigil)}</span><span class="choose-label">choose class</span></span>
      <h3>${escapeHtml(archetype.name)}</h3>
      <p>${escapeHtml(archetype.tagline)}</p>
    </button>`).join('');
  };

  const renderQuestion = (focusFirst = false) => {
    const question = packs.quiz[questionIndex];
    if (!question) return;
    quizProgress.textContent = `${questionIndex + 1} / ${packs.quiz.length}`;
    quizRoot.innerHTML = `<p class="quiz-question">${escapeHtml(question.question)}</p>
      <div class="quiz-options">${question.options.map(option => `<button class="quiz-option" type="button" data-option="${escapeHtml(option.id)}">${escapeHtml(option.label)}</button>`).join('')}</div>`;
    if (focusFirst && quizRoot.querySelector) quizRoot.querySelector('.quiz-option')?.focus();
  };

  const setupPrompt = (archetype, items) => {
    const stack = items.map(item => `- ${item.name}: ${item.role}\n  Source: ${safeHref(item.url)}`).join('\n');
    const safety = packs.safety.map((rule, index) => `${index + 1}. ${rule}`).join('\n');
    return `Set up the Waterfall ${archetype.name} developer starter pack for this project.\n\nGoal\n${archetype.description}\n\nRecommended stack\n${stack}\n\nPermission posture\n${archetype.permission_posture}\n\nRequired process\n${safety}\n\nFirst inspect the real repository, operating system, installed tools, project instructions, package managers, current MCP configuration, and git status using read-only checks. Compare what already exists with this candidate stack. Use current official documentation and pinned upstream sources.\n\nBefore changing anything, present a concise plan with: what is already installed, what you recommend adding or changing, exact sources, expected cost, permissions, configuration files affected, and the smallest verification check for each item. Ask me to approve the proposed changes. Do not install, authenticate, edit global configuration, enable write access, or spend money until I approve those exact actions.\n\nAfter approval, make only the approved changes. Preserve unrelated configuration and existing user edits. Never print, copy, commit, or publish credentials, private paths, account identifiers, or repository content. Verify every installed item with a harmless check and finish with a complete change log plus manual follow-ups.`;
  };

  const selectClass = (id, updateUrl = true) => {
    const archetype = packs.archetypes.find(candidate => candidate.id === id);
    if (!archetype) return;
    const items = archetype.catalog_ids.map(itemId => catalogById.get(itemId)).filter(Boolean);
    selectedId = id;
    resultTitle.textContent = archetype.name;
    resultSigil.textContent = archetype.sigil;
    resultRoot.innerHTML = `<p><strong>${escapeHtml(archetype.tagline)}</strong></p>
      <p>${escapeHtml(archetype.description)}</p>
      <p><strong>Default posture:</strong> ${escapeHtml(archetype.permission_posture)}</p>
      <ul class="tool-list">${items.map(item => `<li><span><strong>${escapeHtml(item.name)}</strong><br>${escapeHtml(item.role)}</span><a href="${escapeHtml(safeHref(item.url))}" target="_blank" rel="noreferrer">source</a></li>`).join('')}</ul>`;
    promptField.value = setupPrompt(archetype, items);
    copyButton.disabled = false;
    startOverButton.disabled = false;
    renderClasses();
    setStatus(`Starter pack ready. Checked ${packs.updated_at}.`, 'success');
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.set('class', id);
      history.replaceState({}, '', url);
    }
  };

  const finishQuiz = () => {
    const winner = packs.archetypes.reduce((best, archetype) => {
      const score = scores[archetype.id] || 0;
      return score > best.score ? { id: archetype.id, score } : best;
    }, { id: packs.archetypes[0].id, score: scores[packs.archetypes[0].id] || 0 });
    quizProgress.textContent = `${packs.quiz.length} / ${packs.quiz.length}`;
    quizRoot.innerHTML = '<div class="empty">Quiz complete. Your class and setup brief are ready.</div>';
    selectClass(winner.id);
  };

  classGrid.addEventListener('click', (event) => {
    const button = event.target.closest('[data-class]');
    if (button && packs) selectClass(button.dataset.class);
  });

  quizRoot.addEventListener('click', (event) => {
    const button = event.target.closest('[data-option]');
    if (!button || !packs) return;
    const option = packs.quiz[questionIndex].options.find(candidate => candidate.id === button.dataset.option);
    if (!option) return;
    Object.entries(option.scores).forEach(([id, points]) => {
      scores[id] = (scores[id] || 0) + points;
    });
    questionIndex += 1;
    if (questionIndex >= packs.quiz.length) finishQuiz(); else renderQuestion(true);
  });

  copyButton.addEventListener('click', async () => {
    if (!promptField.value) return;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(promptField.value);
      setStatus('Setup prompt copied.', 'success');
    } catch (_error) {
      try {
        promptField.focus();
        promptField.select();
        if (!document.execCommand || !document.execCommand('copy')) throw new Error('Copy failed');
        setStatus('Setup prompt copied with the browser fallback.', 'success');
      } catch (_fallbackError) {
        promptField.focus();
        setStatus('Copy was blocked. Select the prompt and copy it manually.', 'error');
      }
    }
  });

  startOverButton.addEventListener('click', () => {
    selectedId = null;
    questionIndex = 0;
    scores = {};
    promptField.value = '';
    copyButton.disabled = true;
    startOverButton.disabled = true;
    resultTitle.textContent = 'Choose a class to begin.';
    resultSigil.textContent = '?';
    resultRoot.innerHTML = '<p>Your recommended tools, permission posture, and copy-ready setup prompt will appear here.</p>';
    const url = new URL(location.href);
    url.searchParams.delete('class');
    history.replaceState({}, '', url);
    renderClasses();
    renderQuestion();
    setStatus('Choose directly or answer the quiz.');
  });

  Promise.all([
    fetch('/workshop/packs.json').then(response => {
      if (!response.ok) throw new Error(`Packs HTTP ${response.status}`);
      return response.json();
    }),
    fetch('/workshop/catalog.json').then(response => {
      if (!response.ok) throw new Error(`Catalog HTTP ${response.status}`);
      return response.json();
    }),
  ]).then(([packData, catalogData]) => {
    catalogById = validateData(packData, catalogData);
    packs = packData;
    renderClasses();
    renderQuestion();
    const requested = new URLSearchParams(location.search).get('class');
    if (requested && packs.archetypes.some(archetype => archetype.id === requested)) {
      selectClass(requested, false);
    } else {
      setStatus('Choose directly or answer the quiz.');
    }
  }).catch(() => {
    classGrid.innerHTML = '<div class="empty">The class builder could not load. Open <a href="/workshop/packs.json">packs.json</a> directly.</div>';
    quizRoot.innerHTML = '<div class="empty">Quiz unavailable. The raw starter packs remain accessible.</div>';
    setStatus('Starter pack data could not load. Try again or use the JSON links.', 'error');
  });
})();
