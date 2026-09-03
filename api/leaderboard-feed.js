const board = require('./leaderboard.json');

const fields = [
  'rank', 'model', 'effort', 'quality', 'price_in', 'price_out',
  'cache_read', 'cost_per_solved', 'cost_per_attempt', 'solved_pct',
  'value', 'best_for', 'updated', 'source', 'n', 'harness',
];

function csvCell(value) {
  if (value == null) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv() {
  const rows = board.rows.map(row => fields.map(field => csvCell(row[field])).join(','));
  return [fields.join(','), ...rows].join('\n') + '\n';
}

module.exports = function handler(request, response) {
  response.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
  if (request.query.format === 'csv') {
    response.setHeader('Content-Type', 'text/csv; charset=utf-8');
    response.status(200).send(toCsv());
    return;
  }
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.status(200).send(JSON.stringify(board));
};
