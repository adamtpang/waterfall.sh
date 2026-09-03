(() => {
  const body = document.getElementById('leaderboard-body');
  const status = document.getElementById('table-status');
  const boardDate = document.getElementById('board-date');
  const boardSource = document.getElementById('board-source');
  const buttons = [...document.querySelectorAll('[data-sort]')];
  let rows = [];
  let sortKey = 'value';
  let direction = 'desc';

  const money = value => value == null ? 'pending' : `$${Number(value).toFixed(2)}`;
  const number = value => Number(value).toFixed(Number(value) % 1 ? 1 : 0);
  const sourceLabel = source => source === 'harness' ? 'harness' : 'snapshot';

  function cell(text, className = '') {
    const td = document.createElement('td');
    td.textContent = text;
    if (className) td.className = className;
    return td;
  }

  function render() {
    const multiplier = direction === 'asc' ? 1 : -1;
    const sorted = [...rows].sort((a, b) => {
      const av = a[sortKey] == null ? Number.POSITIVE_INFINITY : Number(a[sortKey]);
      const bv = b[sortKey] == null ? Number.POSITIVE_INFINITY : Number(b[sortKey]);
      return (av - bv) * multiplier || Number(a.rank) - Number(b.rank);
    });
    body.replaceChildren();
    sorted.forEach((row, index) => {
      const tr = document.createElement('tr');
      tr.append(cell(String(index + 1)));

      const model = document.createElement('th');
      model.scope = 'row';
      const name = document.createElement('strong');
      name.textContent = row.model;
      const meta = document.createElement('small');
      meta.textContent = `${row.effort} · ${sourceLabel(row.source)}${row.n ? ` · n=${row.n}` : ''}`;
      model.append(name, meta);
      tr.append(model);

      tr.append(cell(number(row.quality)));
      tr.append(cell(`${money(row.price_in)} / ${money(row.price_out)}`));
      tr.append(cell(row.cache_read == null ? 'none' : money(row.cache_read)));
      tr.append(cell(money(row.cost_per_solved)));
      tr.append(cell(money(row.cost_per_attempt)));
      tr.append(cell(`${Math.round(Number(row.solved_pct) * 100)}%`));
      const valueCell = cell('');
      const value = document.createElement('strong');
      value.className = 'value-score';
      value.textContent = Number(row.value).toFixed(1);
      valueCell.append(value);
      tr.append(valueCell);
      tr.append(cell(row.best_for));
      tr.append(cell(row.updated));
      body.append(tr);
    });

    document.querySelectorAll('[data-sort-header]').forEach(header => header.removeAttribute('aria-sort'));
    const active = document.querySelector(`[data-sort-header="${sortKey}"]`);
    if (active) active.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : 'descending');
    status.textContent = `${sortKey.replaceAll('_', ' ')} ${direction === 'asc' ? 'ascending' : 'descending'}, ${rows.length} dated rows.`;
  }

  buttons.forEach(button => button.addEventListener('click', () => {
    const nextKey = button.dataset.sort;
    if (sortKey === nextKey) {
      direction = direction === 'desc' ? 'asc' : 'desc';
    } else {
      sortKey = nextKey;
      direction = nextKey === 'cost_per_solved' ? 'asc' : 'desc';
    }
    render();
  }));

  // ---- coverage: borrowed scores for unmeasured models ------------------
  const coverageBody = document.getElementById('coverage-body');
  const coverageStatus = document.getElementById('coverage-status');
  const coverageToggle = document.getElementById('coverage-toggle');
  const COVERAGE_PREVIEW = 30;
  let coverageRows = [];
  let coverageExpanded = false;

  const sourceName = src => src === 'aa:coding_index' ? 'AA coding'
    : src === 'aa:intelligence_index' ? 'AA intelligence'
    : src === 'design_arena:elo_rescaled' ? 'Arena Elo' : String(src || '');
  const ctx = n => n ? (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n)) : '';

  function renderCoverage() {
    if (!coverageBody) return;
    const shown = coverageExpanded ? coverageRows : coverageRows.slice(0, COVERAGE_PREVIEW);
    coverageBody.replaceChildren();
    shown.forEach((row, index) => {
      const tr = document.createElement('tr');
      tr.append(cell(String(index + 1)));
      const model = document.createElement('th');
      model.scope = 'row';
      const name = document.createElement('strong');
      name.textContent = row.display || row.model;
      const id = document.createElement('small');
      id.textContent = row.model;
      model.append(name, id);
      tr.append(model);
      tr.append(cell(number(row.quality_borrowed), 'borrowed'));
      tr.append(cell(sourceName(row.quality_source)));
      const price = row.free ? 'free' : `${money(row.price_in)} / ${money(row.price_out)}`;
      tr.append(cell(price, row.free ? 'free-tag' : ''));
      tr.append(cell(ctx(row.context)));
      tr.append(cell((row.efforts && row.efforts.length) ? row.efforts.join(', ') : ''));
      coverageBody.append(tr);
    });
    if (coverageStatus) {
      coverageStatus.textContent = coverageRows.length
        ? `${shown.length} of ${coverageRows.length} unmeasured models, sorted by borrowed quality.`
        : 'No catalog coverage in this feed.';
    }
    if (coverageToggle) {
      coverageToggle.hidden = coverageRows.length <= COVERAGE_PREVIEW;
      coverageToggle.textContent = coverageExpanded ? 'Show fewer' : `Show all ${coverageRows.length}`;
      coverageToggle.setAttribute('aria-expanded', String(coverageExpanded));
    }
  }

  if (coverageToggle) coverageToggle.addEventListener('click', () => {
    coverageExpanded = !coverageExpanded;
    renderCoverage();
  });

  fetch('/api/leaderboard.json')
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(board => {
      rows = board.rows;
      boardDate.textContent = board.as_of;
      const harnessCount = rows.filter(row => row.source === 'harness').length;
      boardSource.textContent = `${rows.length - harnessCount} snapshot priors, ${harnessCount} harness rows`;
      render();
      coverageRows = (board.coverage && board.coverage.rows) || [];
      renderCoverage();
    })
    .catch(() => {
      status.textContent = 'Feed unavailable. Showing the committed 2026-09-03 value-sorted snapshot.';
    });
})();
