const board = require('./leaderboard.json');

function normalize(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function xml(value) {
  return String(value).replace(/[<>&"']/g, character => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;',
  })[character]);
}

function badge(label, value, color = '#1677a5') {
  const leftWidth = Math.max(88, label.length * 7 + 14);
  const rightWidth = Math.max(54, String(value).length * 8 + 16);
  const width = leftWidth + rightWidth;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="20" role="img" aria-label="${xml(label)}: ${xml(value)}"><title>${xml(label)}: ${xml(value)}</title><linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#fff" stop-opacity=".08"/><stop offset="1" stop-opacity=".08"/></linearGradient><clipPath id="r"><rect width="${width}" height="20" rx="4"/></clipPath><g clip-path="url(#r)"><rect width="${leftWidth}" height="20" fill="#27334a"/><rect x="${leftWidth}" width="${rightWidth}" height="20" fill="${color}"/><rect width="${width}" height="20" fill="url(#s)"/></g><g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11"><text x="${leftWidth / 2}" y="15" fill="#010101" fill-opacity=".3">${xml(label)}</text><text x="${leftWidth / 2}" y="14">${xml(label)}</text><text x="${leftWidth + rightWidth / 2}" y="15" fill="#010101" fill-opacity=".3">${xml(value)}</text><text x="${leftWidth + rightWidth / 2}" y="14">${xml(value)}</text></g></svg>`;
}

module.exports = function handler(request, response) {
  const model = normalize(request.query.model);
  const matches = board.rows.filter(row => normalize(row.model) === model);
  const row = matches.sort((a, b) => Number(b.value) - Number(a.value))[0];
  response.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  response.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
  if (!row) {
    response.status(404).send(badge('waterfall value', 'not found', '#8b3342'));
    return;
  }
  response.status(200).send(badge(`${row.model} value`, Number(row.value).toFixed(1)));
};
