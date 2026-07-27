/* Lobby client: join -> pick a fighter -> describe how it fights. */
(() => {
'use strict';

const $ = (id) => document.getElementById(id);
const steps = {
  join: $('step-join'), pick: $('step-pick'), brief: $('step-brief'), done: $('step-done'),
};

let state = null;
let step = 'join';
let lastRoundId = null;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

function show(name) {
  step = name;
  for (const [key, node] of Object.entries(steps)) node.classList.toggle('hidden', key !== name);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  return {ok: res.ok, status: res.status, data};
}

/* ------------------------------------------------------------------- poll */
async function refresh() {
  const {ok, data} = await api('/api/state');
  if (!ok) return;
  state = data;

  const llm = $('llm-state');
  llm.textContent = data.llm.available ? 'AI interpreter on' : 'AI interpreter off';
  llm.className = 'chip ' + (data.llm.available ? 'good' : 'warn');
  llm.title = data.llm.reason || '';

  const claimed = data.characters.filter(c => c.takenBy).length;
  $('player-count').textContent = `${claimed} / ${data.maxPlayers} in arena`;

  // A finished match releases every character; bounce everyone back to the grid.
  if (lastRoundId !== null && data.roundId !== lastRoundId) {
    const w = data.lastWinner;
    if (w) flash(`${w.name} won as ${w.characterName}. Characters are free again — pick one.`);
    if (step === 'done' || step === 'brief') show('pick');
  }
  lastRoundId = data.roundId;

  renderGrid();
  renderPlayers();

  // Keep the visible step consistent with what the server thinks.
  if (data.you) {
    if (step === 'join') show(data.you.ready ? 'done' : data.you.character ? 'brief' : 'pick');
    if (step === 'pick' && data.you.character && data.you.ready) show('done');
  }
}

function flash(msg) {
  $('done-msg').textContent = msg;
}

/* ------------------------------------------------------------------- grid */
function renderGrid() {
  if (!state) return;
  const bars = [
    ['Speed', 'speed'], ['Power', 'strength'], ['Health', 'health'],
    ['Reload', 'reload_rate'], ['Weight', 'weight'], ['Reach', 'reach'],
    ['Shield', 'shielding'], ['Jump', 'jump'],
  ];

  $('grid').innerHTML = state.characters.map(c => {
    // Health is an absolute number (80-165), the rest are 1-10 sliders.
    const pct = (key) => key === 'health'
      ? Math.round(((c.health - 60) / 110) * 100)
      : c[key] * 10;
    const value = (key) => key === 'health' ? c.health : c[key];
    const tag = c.mine
      ? '<div class="taken-tag mine">Yours</div>'
      : c.takenBy ? `<div class="taken-tag">${esc(c.takenBy)}</div>` : '';

    return `
      <div class="fighter ${c.takenBy && !c.mine ? 'taken' : ''} ${c.mine ? 'mine' : ''}"
           style="--c:${c.color}" data-id="${c.id}">
        ${tag}
        <div class="f-name">${esc(c.name)}</div>
        <div class="f-title">${esc(c.title)}</div>
        <div class="f-blurb">${esc(c.blurb)}</div>
        <div class="stats">
          ${bars.map(([label, key]) => `
            <div class="stat">
              <span>${label}</span>
              <i><b style="width:${Math.max(4, Math.min(100, pct(key)))}%"></b></i>
              <u>${value(key)}</u>
            </div>`).join('')}
        </div>
      </div>`;
  }).join('');

  for (const node of document.querySelectorAll('.fighter')) {
    node.addEventListener('click', () => pick(node.dataset.id));
  }
}

function renderPlayers() {
  if (!state) return;
  $('players').innerHTML = state.players.map(p => `
    <div class="player-chip ${p.ready ? 'ready' : ''}">
      <i></i>${esc(p.name)}
      <small>${p.character ? esc(charName(p.character)) : 'choosing…'}</small>
    </div>`).join('');
}

const charName = (id) => (state.characters.find(c => c.id === id) || {}).name || id;

/* ------------------------------------------------------------------ steps */
$('join-btn').addEventListener('click', async () => {
  const name = $('name-input').value.trim();
  if (!name) { $('join-err').textContent = 'Pick a name first.'; return; }
  $('join-err').textContent = '';
  const {ok} = await api('/api/join', {name});
  if (!ok) { $('join-err').textContent = 'Could not join. Try again.'; return; }
  await refresh();
  show('pick');
});

$('name-input').addEventListener('keydown', e => { if (e.key === 'Enter') $('join-btn').click(); });

async function pick(id) {
  const c = state.characters.find(x => x.id === id);
  if (!c || (c.takenBy && !c.mine)) return;
  const {ok, data} = await api('/api/select', {character: id});
  if (!ok) { alert(data.message || 'That fighter is taken.'); await refresh(); return; }
  await refresh();
  openBrief(c);
}

function openBrief(c) {
  document.documentElement.style.setProperty('--c', c.color);
  $('chosen').innerHTML = `<b style="--c:${c.color}"></b> ${esc(c.name)} — ${esc(c.title)}`;
  $('chosen').style.setProperty('--c', c.color);
  $('brief-name').textContent = c.name;
  if (state.you && state.you.brief) $('brief').value = state.you.brief;
  updateCount();
  show('brief');
}

$('brief').addEventListener('input', updateCount);
function updateCount() {
  $('char-count').textContent = `${$('brief').value.length} / 1500`;
}

$('back-btn').addEventListener('click', async () => {
  await api('/api/leave', {});
  await refresh();
  show('pick');
});

$('finish-btn').addEventListener('click', async () => {
  const brief = $('brief').value.trim();
  if (brief.length < 8) {
    $('brief-err').textContent = 'Describe how your fighter should act — a sentence or two.';
    return;
  }
  $('brief-err').textContent = '';
  const btn = $('finish-btn');
  btn.disabled = true;
  btn.textContent = 'INTERPRETING…';

  const {ok, data} = await api('/api/behaviour', {brief});
  btn.disabled = false;
  btn.textContent = 'FINISH';

  if (!ok) { $('brief-err').textContent = data.message || 'Something went wrong.'; return; }

  $('done-title').textContent = "You're in";
  $('done-msg').textContent = data.message;
  $('done-note').textContent = `${data.file} · ${data.note}`;
  $('code').textContent = data.source;
  await refresh();
  show('done');
});

$('rewrite-btn').addEventListener('click', () => {
  const c = state.characters.find(x => x.mine);
  if (c) openBrief(c); else show('pick');
});

refresh();
setInterval(refresh, 2500);
})();
