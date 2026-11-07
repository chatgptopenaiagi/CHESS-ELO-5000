/* Focused browser-independent checks for presentation boundaries used by the live client. */
const test = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../client/web/app.js');

test('Joomla proxy preserves API path, FEN query and spaces as one encoded value', () => {
  const resource = '/positions?fen=' + encodeURIComponent(ui.START_FEN);
  const config = {proxy:true,apiBase:'/index.php?option=com_chesselo5000&task=api.proxy&format=raw&path='};
  const parsed = new URL(ui.apiURL(config,resource),'http://localhost');
  assert.equal(parsed.searchParams.get('path'),'/api/v1'+resource);
  assert.equal(parsed.searchParams.get('option'),'com_chesselo5000');
  assert.equal(parsed.searchParams.get('task'),'api.proxy');
});

test('standard and promoted FEN pieces are displayed without inferring legality', () => {
  const board=ui.parseFen(ui.START_FEN);
  assert.equal(Object.keys(board).length,32);
  assert.equal(board.a1,'R'); assert.equal(board.e8,'k'); assert.equal(board.h7,'p');
  assert.deepEqual(ui.parseFen('Q6k/8/8/8/8/8/8/7K b - - 0 1'),{a8:'Q',h8:'k',h1:'K'});
});

test('malformed piece encodings never reach the chessboard', () => {
  for(const fen of ['8/8/8/8/8/8/8/7 w - - 0 1','8/8/8/8/8/8/8/9 w - - 0 1','8/8/8/8/8/8/8/< w - - 0 1','8/8/8/8/8/8/8/8 x - - 0 1']) {
    assert.throws(()=>ui.parseFen(fen));
  }
});

test('board rotation retains all 64 unique authoritative square names', () => {
  const white=ui.boardCoordinates(false),black=ui.boardCoordinates(true);
  assert.equal(white.length,64); assert.equal(new Set(white).size,64);
  assert.equal(white[0],'a8'); assert.equal(white[63],'h1');
  assert.deepEqual(white.toReversed(),black);
});

test('untrusted annotations render as text rather than executable HTML', () => {
  assert.equal(ui.escapeHTML('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(ui.escapeHTML("A&B's"),'A&amp;B&#39;s');
});

test('untimed games remain untimed and expired clocks never become negative', () => {
  assert.equal(ui.formatClock(null),'—:—'); assert.equal(ui.formatClock(-200),'00:00');
  assert.equal(ui.formatClock(300001),'05:01'); assert.equal(ui.formatClock(999),'00:01');
});
