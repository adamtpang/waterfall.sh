(() => {
  const root = document.getElementById('catalog-root');
  const search = document.getElementById('search');
  const filters = [...document.querySelectorAll('[data-filter]')];
  let catalog = null;
  let active = new URLSearchParams(location.search).get('shelf') || 'all';

  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
  const safeHref = (value) => {
    const href = String(value);
    return href.startsWith('https://') || href.startsWith('/workshop/') ? href : '#';
  };

  const card = (item) => {
    const text = [item.name, item.publisher, item.role, item.evidence, item.avoid, ...(item.tags || [])].join(' ').toLowerCase();
    const query = search.value.trim().toLowerCase();
    if (query && !text.includes(query)) return '';
    const tags = (item.tags || []).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('');
    const rank = item.ranking_eligible && Number.isInteger(item.rank)
      ? `<span class="rank" title="Waterfall fit rank" aria-label="Waterfall fit rank ${escapeHtml(item.rank)}">#${escapeHtml(item.rank)}</span>`
      : '';
    return `<article class="card">
      <div class="card-top">
        <div class="card-labels">${rank}<span class="state ${escapeHtml(item.default_state)}">${escapeHtml(item.default_state)}</span></div>
        <span class="publisher">${escapeHtml(item.publisher)}</span>
      </div>
      <h3>${escapeHtml(item.name)}</h3>
      <p class="role">${escapeHtml(item.role)}</p>
      <p class="evidence"><b>why</b>${escapeHtml(item.evidence)}</p>
      <p class="avoid"><b>leave off</b>${escapeHtml(item.avoid)}</p>
      <div class="card-foot">
        <div class="tags">${tags}</div>
        <a class="source-link" href="${escapeHtml(safeHref(item.url))}" target="_blank" rel="noreferrer">
          <span>open link</span><span class="checked">checked ${escapeHtml(item.checked_at)}</span>
        </a>
      </div>
    </article>`;
  };

  const render = () => {
    if (!catalog) return;
    filters.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === active)));
    const shelves = catalog.collections
      .filter(collection => active === 'all' || collection.id === active)
      .map(collection => {
        const orderedItems = [...collection.items].sort((a, b) => {
          if (a.ranking_eligible !== b.ranking_eligible) return a.ranking_eligible ? -1 : 1;
          if (a.ranking_eligible) return a.rank - b.rank;
          return a.name.localeCompare(b.name);
        });
        const cards = orderedItems.map(card).filter(Boolean);
        if (!cards.length) return '';
        return `<section class="shelf" data-shelf="${escapeHtml(collection.id)}">
          <div class="shelf-head">
            <div class="shelf-title"><h2>${escapeHtml(collection.title)}</h2><span class="count">${cards.length}</span></div>
            <p class="shelf-summary">${escapeHtml(collection.summary)}</p>
          </div>
          <div class="cards">${cards.join('')}</div>
        </section>`;
      }).filter(Boolean);
    root.innerHTML = shelves.length ? shelves.join('') : '<div class="empty">No entries match that search.</div>';
  };

  const renderSnapshot = () => {
    const values = {
      'snapshot-checked': `Checked ${catalog.updated_at}`,
      'snapshot-active': catalog.audit.active_skills,
      'snapshot-removed': catalog.audit.unused_skills_removed,
      'snapshot-public': catalog.audit.public_starter_skills,
      'snapshot-affiliate': catalog.audit.affiliate_links,
    };
    Object.entries(values).forEach(([id, value]) => {
      document.getElementById(id).textContent = String(value);
    });
  };

  filters.forEach(button => button.addEventListener('click', () => {
    active = button.dataset.filter;
    const url = new URL(location.href);
    if (active === 'all') url.searchParams.delete('shelf'); else url.searchParams.set('shelf', active);
    history.replaceState({}, '', url);
    render();
  }));
  search.addEventListener('input', render);

  fetch('/workshop/catalog.json')
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(data => {
      catalog = data;
      if (!catalog.collections.some(collection => collection.id === active)) active = 'all';
      renderSnapshot();
      render();
    })
    .catch(() => {
      root.innerHTML = '<div class="empty">The interactive catalog could not load. Open <a href="/workshop/catalog.json">catalog.json</a> or <a href="/workshop/README.md">README.md</a> directly.</div>';
    });
})();
