/* Renderer + client for the main game screen. */
(() => {
'use strict';

const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d');

const el = {
  conn: document.getElementById('conn'),
  matchLabel: document.getElementById('match-label'),
  roster: document.getElementById('roster'),
  ticker: document.getElementById('ticker'),
  centerMsg: document.getElementById('center-msg'),
  waiting: document.getElementById('waiting'),
  scriptList: document.getElementById('script-list'),
  victory: document.getElementById('victory'),
  confetti: document.getElementById('confetti'),
  winName: document.getElementById('win-name'),
  winChar: document.getElementById('win-char'),
  winKos: document.getElementById('win-kos'),
  winDmg: document.getElementById('win-dmg'),
  winStocks: document.getElementById('win-stocks'),
  nextBtn: document.getElementById('next-game'),
  resetBtn: document.getElementById('reset-game'),
  joinUrl: document.getElementById('join-url'),
};

let world = {w: 1600, h: 900};
let stage = null;
let state = null;
let prev = {fighters: new Map(), state: null, countdown: -1, winnerId: null};
let lastEventTime = 0;
const particles = [];
const cam = {x: 800, y: 450, zoom: 1, tx: 800, ty: 450, tz: 1, shake: 0};

// Replaced with the real LAN address as soon as the server tells us.
el.joinUrl.textContent = `http://${location.hostname}:8100`;
function setLobbyUrl(url) { if (url) el.joinUrl.textContent = url; }

/* ------------------------------------------------------------------ canvas */
function resize() {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.floor(innerWidth * dpr);
  canvas.height = Math.floor(innerHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
addEventListener('resize', resize);
resize();

/* --------------------------------------------------------------- transport */
let ws = null;
let retry = 0;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    retry = 0;
    el.conn.textContent = 'live';
    el.conn.className = 'pill online';
  };
  ws.onclose = () => {
    el.conn.textContent = 'reconnecting';
    el.conn.className = 'pill offline';
    retry = Math.min(retry + 1, 8);
    setTimeout(connect, 250 * retry);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.init) {
      stage = msg.init.stage;
      world = stage.world;
      setLobbyUrl(msg.init.lobbyUrl);
      return;
    }
    onState(msg);
  };
}

async function loadStatic() {
  try {
    const r = await fetch('/api/static');
    const d = await r.json();
    stage = d.stage;
    world = stage.world;
    setLobbyUrl(d.lobbyUrl);
  } catch (e) { /* the websocket sends it too */ }
}

el.nextBtn.addEventListener('click', () => {
  Sound.unlock();
  Sound.stopMusic(0.3);
  fetch('/api/next-game', {method: 'POST'}).catch(() => {});
});

async function resetMatch() {
  if (el.resetBtn.disabled) return;
  el.resetBtn.disabled = true;
  Sound.unlock();
  Sound.stopMusic(0.3);
  try {
    const response = await fetch('/api/reset', {method: 'POST'});
    if (!response.ok) throw new Error(`reset failed (${response.status})`);
    particles.length = 0;
    prev = {fighters: new Map(), state: null, countdown: -1, winnerId: null};
    lastEventTime = 0;
  } catch (error) {
    console.error('Could not reset the arena:', error);
  } finally {
    window.setTimeout(() => { el.resetBtn.disabled = false; }, 350);
  }
}

el.resetBtn.addEventListener('click', resetMatch);

/* ------------------------------------------------------------ state intake */
function onState(next) {
  state = next;
  el.matchLabel.textContent = `MATCH ${state.match}`;

  reactToSound();
  renderRoster();
  renderTicker();
  renderOverlays();

  prev.fighters = new Map(state.fighters.map(f => [f.id, f]));
  prev.state = state.state;
}

function reactToSound() {
  for (const f of state.fighters) {
    const before = prev.fighters.get(f.id);
    if (!before) continue;
    if (f.attack && f.attack !== before.attack) {
      if (f.attack === 'heavy') Sound.cue.heavy();
      else if (f.attack === 'shoot') Sound.cue.shoot();
      else Sound.cue.hit();
    }
    if (f.hp < before.hp - 0.5) {
      spawnHitBurst(f.x, f.y + f.h / 2, f.accent);
      cam.shake = Math.min(16, cam.shake + (before.hp - f.hp) * 0.35);
    }
    if (before.alive && !f.alive) {
      spawnKO(f.x, f.y + f.h / 2, f.color);
      cam.shake = 18;
      f.eliminated ? Sound.cue.out() : Sound.cue.ko();
    }
  }

  for (const e of state.events || []) {
    if (e.t <= lastEventTime) continue;
    lastEventTime = e.t;
    if (e.kind === 'join') Sound.cue.join();
  }

  if (state.state === 'countdown' && state.countdown !== prev.countdown) {
    prev.countdown = state.countdown;
    Sound.cue.countdown(state.countdown);
    showCenter(state.countdown > 0 ? `${state.countdown}` : 'FIGHT', state.countdown > 0 ? 'count' : 'go');
  }
  if (state.state === 'fighting' && prev.state !== 'fighting') {
    prev.countdown = -1;
    showCenter('FIGHT', 'go');
    Sound.startMusic();
  }
  if (state.state === 'victory' && prev.state !== 'victory') {
    const w = state.winner;
    if (w && w.id !== prev.winnerId) {
      prev.winnerId = w.id;
      Sound.cue.victory(w.name, w.characterName);
    } else if (!w) {
      Sound.stopMusic();
    }
  }
  if (state.state !== 'victory') prev.winnerId = null;
  if (state.state === 'waiting') Sound.stopMusic();
}

function showCenter(text, kind) {
  el.centerMsg.innerHTML = `<div class="${kind}">${text}</div>`;
  setTimeout(() => { el.centerMsg.innerHTML = ''; }, kind === 'go' ? 900 : 950);
}

/* --------------------------------------------------------------- HUD (DOM) */
function renderRoster() {
  const fighters = state.fighters;
  el.roster.innerHTML = fighters.map(f => {
    const hpPct = Math.max(0, f.hp / f.maxHp);
    const tier = hpPct > 0.6 ? 'high' : hpPct > 0.3 ? 'mid' : '';
    const stocks = Array.from({length: state.stocks}, (_, i) =>
      `<span class="stock ${i < f.stocks ? '' : 'spent'}"></span>`).join('');
    const ammo = f.reloading
      ? '<span class="ammo reloading">RELOAD</span>'
      : `<span class="ammo">${'●'.repeat(f.ammo)}${'○'.repeat(Math.max(0, f.maxAmmo - f.ammo))}</span>`;
    return `
      <div class="card ${f.eliminated ? 'dead' : ''} ${f.hit > 0 ? 'hurt' : ''}" style="--card-color:${f.color}">
        <div class="card-top">
          <span class="card-name">${esc(f.name)}</span>
          <span class="card-char">${esc(f.charName)}</span>
        </div>
        <div class="bar hp ${tier}"><i style="width:${hpPct * 100}%"></i></div>
        <div class="bar shield"><i style="width:${(f.shield / f.maxShield) * 100}%"></i></div>
        <div class="card-meta">
          <span class="stocks">${stocks}</span>
          ${ammo}
        </div>
      </div>`;
  }).join('');
}

function renderTicker() {
  el.ticker.innerHTML = (state.events || []).slice(-5).reverse()
    .map(e => `<div class="event ${e.kind}">${esc(e.text)}</div>`).join('');
}

function renderOverlays() {
  const waiting = state.state === 'waiting';
  el.waiting.classList.toggle('hidden', !waiting);
  if (waiting) {
    el.scriptList.innerHTML = (state.scripts || []).map(s =>
      `<div class="script-row ${s.ok ? '' : 'bad'}">${esc(s.file)} ${s.ok ? '✓' : '· ' + esc(s.error || 'error')}</div>`
    ).join('') || '<div class="script-row">no scripts loaded yet</div>';
  }

  const victory = state.state === 'victory';
  el.victory.classList.toggle('hidden', !victory);
  if (victory && state.winner) {
    const w = state.winner;
    el.victory.style.setProperty('--win-color', w.color);
    el.winName.textContent = w.name;
    el.winChar.textContent = `${w.characterName} · ${w.title}`;
    el.winKos.textContent = w.kos;
    el.winDmg.textContent = Math.round(w.damage);
    el.winStocks.textContent = w.stocks;
    if (!el.confetti.childElementCount) buildConfetti(w.color, w.accent);
  } else if (!victory) {
    el.confetti.innerHTML = '';
  }
}

function buildConfetti(a, b) {
  const colors = [a, b, '#ffd35c', '#ffffff'];
  el.confetti.innerHTML = Array.from({length: 70}, () => {
    const left = Math.random() * 100;
    const delay = Math.random() * 3;
    const dur = 2.6 + Math.random() * 2.6;
    const c = colors[(Math.random() * colors.length) | 0];
    return `<i style="left:${left}%;background:${c};animation-duration:${dur}s;animation-delay:${-delay}s"></i>`;
  }).join('');
}

const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

/* --------------------------------------------------------------- particles */
function spawnHitBurst(x, y, color) {
  for (let i = 0; i < 12; i++) {
    const a = Math.random() * Math.PI * 2;
    const s = 2 + Math.random() * 5;
    particles.push({x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 1,
      life: 26 + Math.random() * 14, max: 40, color, size: 2 + Math.random() * 3});
  }
}

function spawnKO(x, y, color) {
  for (let i = 0; i < 46; i++) {
    const a = Math.random() * Math.PI * 2;
    const s = 3 + Math.random() * 12;
    particles.push({x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 2,
      life: 40 + Math.random() * 34, max: 74, color, size: 2 + Math.random() * 5, ring: i < 3});
  }
}

function stepParticles() {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy;
    p.vy += 0.22; p.vx *= 0.975; p.vy *= 0.985;
    if (--p.life <= 0) particles.splice(i, 1);
  }
}

/* ------------------------------------------------------------------ camera */
function updateCamera() {
  const live = state ? state.fighters.filter(f => f.alive && !f.eliminated) : [];
  if (live.length) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const f of live) {
      minX = Math.min(minX, f.x); maxX = Math.max(maxX, f.x);
      minY = Math.min(minY, f.y); maxY = Math.max(maxY, f.y);
    }
    cam.tx = (minX + maxX) / 2;
    cam.ty = (minY + maxY) / 2 + 40;
    const spread = Math.max(maxX - minX + 900, (maxY - minY + 620) * (world.w / world.h));
    cam.tz = clamp(world.w / spread, 0.92, 1.30);
  } else {
    cam.tx = world.w / 2; cam.ty = world.h / 2; cam.tz = 1.0;
  }

  // Keep the stage in frame, but allow headroom so launched fighters stay
  // visible on their way up.
  const halfW = world.w / (2 * cam.tz), halfH = world.h / (2 * cam.tz);
  cam.tx = clamp(cam.tx, halfW - 240, world.w - halfW + 240);
  cam.ty = clamp(cam.ty, halfH - 260, world.h - halfH + 40);

  cam.x += (cam.tx - cam.x) * 0.07;
  cam.y += (cam.ty - cam.y) * 0.07;
  cam.zoom += (cam.tz - cam.zoom) * 0.05;
  cam.shake *= 0.86;
  if (cam.shake < 0.15) cam.shake = 0;
}

// The fighter cards sit along the bottom; keep the stage clear of them.
const HUD_RESERVE = 122;

function applyCamera() {
  // "Contain" fit: at zoom 1 the whole stage is on screen. Zooming past 1
  // crops in on the action, which is the point.
  const viewH = Math.max(240, innerHeight - HUD_RESERVE);
  const base = Math.min(innerWidth / world.w, viewH / world.h);
  const scale = base * cam.zoom;
  const sx = cam.shake ? (Math.random() - 0.5) * cam.shake : 0;
  const sy = cam.shake ? (Math.random() - 0.5) * cam.shake : 0;
  ctx.translate(innerWidth / 2 + sx, viewH / 2 + sy);
  ctx.scale(scale, scale);
  ctx.translate(-cam.x, -cam.y);
  return scale;
}

const clamp = (v, a, b) => v < a ? a : v > b ? b : v;

/* --------------------------------------------------------------- backdrop */
let skyline = null;

function buildSkyline() {
  // Deterministic city silhouettes, generated once.
  let seed = 1337;
  const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
  const layers = [];
  for (let l = 0; l < 3; l++) {
    const buildings = [];
    let x = -600;
    while (x < world.w + 600) {
      const w = 60 + rnd() * 130;
      const h = (90 + rnd() * 300) * (1 - l * 0.18);
      buildings.push({x, w, h, lit: rnd()});
      x += w + 12 + rnd() * 40;
    }
    layers.push(buildings);
  }
  return layers;
}

function drawBackground(t) {
  const g = ctx.createLinearGradient(0, -400, 0, world.h + 200);
  g.addColorStop(0.00, '#0a0f22');
  g.addColorStop(0.34, '#1d1b44');
  g.addColorStop(0.62, '#57306b');
  g.addColorStop(0.82, '#b8546a');
  g.addColorStop(1.00, '#f09055');
  ctx.fillStyle = g;
  ctx.fillRect(-900, -900, world.w + 1800, world.h + 1800);

  // Sun.
  const sunY = world.h - 210;
  const sun = ctx.createRadialGradient(world.w * 0.62, sunY, 20, world.w * 0.62, sunY, 420);
  sun.addColorStop(0, 'rgba(255, 214, 140, 0.95)');
  sun.addColorStop(0.28, 'rgba(255, 150, 90, 0.42)');
  sun.addColorStop(1, 'rgba(255, 120, 80, 0)');
  ctx.fillStyle = sun;
  ctx.fillRect(-900, -900, world.w + 1800, world.h + 1800);

  // Stars fading in near the top.
  ctx.save();
  for (let i = 0; i < 90; i++) {
    const x = ((i * 137.5) % (world.w + 800)) - 400;
    const y = ((i * 91.3) % 420) - 260;
    const tw = 0.35 + 0.65 * Math.abs(Math.sin(t * 0.0009 + i));
    ctx.fillStyle = `rgba(255,255,255,${tw * 0.5})`;
    ctx.fillRect(x, y, 2, 2);
  }
  ctx.restore();

  if (!skyline) skyline = buildSkyline();
  const depths = [
    {k: 0.06, color: 'rgba(24, 20, 52, 0.55)', base: world.h - 120, lit: 'rgba(255,200,140,0.10)'},
    {k: 0.13, color: 'rgba(16, 14, 40, 0.75)', base: world.h - 70, lit: 'rgba(255,190,130,0.14)'},
    {k: 0.22, color: 'rgba(8, 8, 24, 0.92)', base: world.h - 10, lit: 'rgba(255,180,120,0.18)'},
  ];
  depths.forEach((d, li) => {
    const off = (cam.x - world.w / 2) * d.k;
    ctx.save();
    ctx.translate(-off, 0);
    ctx.fillStyle = d.color;
    for (const b of skyline[li]) {
      ctx.fillRect(b.x, d.base - b.h, b.w, b.h + 400);
      if (b.lit > 0.45) {
        ctx.fillStyle = d.lit;
        const rows = Math.floor(b.h / 26);
        for (let r = 1; r < rows; r++) {
          if (((r * 7 + b.x) | 0) % 3) continue;
          ctx.fillRect(b.x + 8, d.base - b.h + r * 26, b.w - 16, 8);
        }
        ctx.fillStyle = d.color;
      }
    }
    ctx.restore();
  });

  // Slow drifting haze.
  ctx.save();
  ctx.globalAlpha = 0.10;
  for (let i = 0; i < 5; i++) {
    const x = ((t * 0.006 * (1 + i * 0.3) + i * 500) % (world.w + 1400)) - 700;
    const y = 120 + i * 95;
    const c = ctx.createRadialGradient(x, y, 10, x, y, 260);
    c.addColorStop(0, 'rgba(255,255,255,0.5)');
    c.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = c;
    ctx.fillRect(x - 280, y - 140, 560, 280);
  }
  ctx.restore();
}

/* ------------------------------------------------------------------- stage */
function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawStage(t) {
  if (!stage) return;
  for (const p of stage.platforms) {
    if (p.soft) {
      ctx.save();
      ctx.shadowColor = 'rgba(120, 190, 255, 0.55)';
      ctx.shadowBlur = 22;
      const g = ctx.createLinearGradient(0, p.y, 0, p.y + p.h);
      g.addColorStop(0, 'rgba(190, 226, 255, 0.95)');
      g.addColorStop(1, 'rgba(90, 140, 220, 0.55)');
      ctx.fillStyle = g;
      roundRect(p.x, p.y, p.w, p.h, p.h / 2);
      ctx.fill();
      ctx.restore();

      ctx.fillStyle = 'rgba(150, 200, 255, 0.14)';
      ctx.fillRect(p.x + 12, p.y + p.h, p.w - 24, 5);
      continue;
    }

    // Main plaza: a slab with a lit deck and a dark underside.
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.55)';
    ctx.shadowBlur = 40;
    ctx.shadowOffsetY = 16;

    const body = ctx.createLinearGradient(0, p.y, 0, p.y + p.h + 150);
    body.addColorStop(0, '#39405f');
    body.addColorStop(0.30, '#232a44');
    body.addColorStop(1, '#0c1020');
    ctx.fillStyle = body;
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x + p.w, p.y);
    ctx.lineTo(p.x + p.w - 52, p.y + p.h + 150);
    ctx.lineTo(p.x + 52, p.y + p.h + 150);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // Deck surface.
    const deck = ctx.createLinearGradient(0, p.y - 2, 0, p.y + 16);
    deck.addColorStop(0, '#8fa4d8');
    deck.addColorStop(1, '#4d5a86');
    ctx.fillStyle = deck;
    ctx.fillRect(p.x, p.y, p.w, 14);

    // Neon lip.
    const pulse = 0.62 + 0.38 * Math.sin(t * 0.0016);
    ctx.save();
    ctx.shadowColor = `rgba(90, 160, 255, ${pulse})`;
    ctx.shadowBlur = 26;
    ctx.fillStyle = `rgba(150, 205, 255, ${0.75 + pulse * 0.25})`;
    ctx.fillRect(p.x, p.y - 3, p.w, 4);
    ctx.restore();

    // Panel seams.
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 2;
    for (let x = p.x + 60; x < p.x + p.w; x += 60) {
      ctx.beginPath();
      ctx.moveTo(x, p.y + 14);
      ctx.lineTo(x - 12, p.y + p.h + 120);
      ctx.stroke();
    }
  }
}

/* ---------------------------------------------------------------- fighters */
function drawFighter(f, t) {
  if (f.eliminated || (!f.alive && !f.respawning)) return;
  const cx = f.x, top = f.y, w = f.w, h = f.h;
  const bottom = top + h;

  // Ground shadow.
  ctx.save();
  ctx.globalAlpha = f.onGround ? 0.38 : 0.16;
  ctx.fillStyle = '#000';
  ctx.beginPath();
  ctx.ellipse(cx, bottom + 4, w * 0.44, 8, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Speed trail.
  const speed = Math.hypot(f.vx, f.vy);
  if (speed > 7) {
    ctx.save();
    ctx.globalAlpha = 0.20;
    ctx.fillStyle = f.color;
    for (let i = 1; i <= 3; i++) {
      roundRect(cx - w / 2 - f.vx * i * 0.9, top - f.vy * i * 0.9, w, h, 13);
      ctx.fill();
    }
    ctx.restore();
  }

  ctx.save();
  if (f.invuln && Math.floor(t / 70) % 2 === 0) ctx.globalAlpha = 0.4;
  if (f.dodging) ctx.globalAlpha = 0.45;

  // Body.
  const g = ctx.createLinearGradient(0, top, 0, bottom);
  g.addColorStop(0, f.accent);
  g.addColorStop(0.35, f.color);
  g.addColorStop(1, shade(f.color, -48));
  ctx.fillStyle = g;
  ctx.shadowColor = f.color;
  ctx.shadowBlur = f.hit > 0 ? 34 : 16;
  roundRect(cx - w / 2, top, w, h, 13);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Hit flash.
  if (f.hit > 0) {
    ctx.globalAlpha = Math.min(0.85, f.hit / 10);
    ctx.fillStyle = '#fff';
    roundRect(cx - w / 2, top, w, h, 13);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // Visor, facing the direction of travel.
  ctx.fillStyle = 'rgba(6, 10, 22, 0.82)';
  roundRect(cx - w / 2 + 8, top + 15, w - 16, 17, 7);
  ctx.fill();
  ctx.fillStyle = f.accent;
  ctx.shadowColor = f.accent;
  ctx.shadowBlur = 12;
  const eyeX = cx + f.facing * 7;
  roundRect(eyeX - 8, top + 20, 16, 7, 3.5);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Shoulder pad on the leading side, and a pair of legs, so the silhouette
  // reads as a fighter rather than a slab.
  ctx.fillStyle = shade(f.color, 34);
  roundRect(cx + f.facing * (w / 2 - 9) - 7, top + 36, 14, 22, 5);
  ctx.fill();
  ctx.fillStyle = shade(f.color, -62);
  roundRect(cx - w / 2 + 7, bottom - 16, 15, 16, 4);
  ctx.fill();
  roundRect(cx + w / 2 - 22, bottom - 16, 15, 16, 4);
  ctx.fill();

  // Chest light doubles as a low-health warning.
  const hpPct = f.hp / f.maxHp;
  ctx.fillStyle = hpPct > 0.35 ? 'rgba(255,255,255,0.30)'
    : `rgba(255,90,110,${0.45 + 0.45 * Math.sin(t * 0.012)})`;
  ctx.beginPath();
  ctx.arc(cx, top + 48, 5.5, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();

  // Shield bubble.
  if (f.shielding) {
    const r = w * 0.95 * (0.85 + 0.15 * (f.shield / f.maxShield));
    ctx.save();
    const sg = ctx.createRadialGradient(cx, top + h / 2, r * 0.4, cx, top + h / 2, r);
    sg.addColorStop(0, 'rgba(120, 210, 255, 0.05)');
    sg.addColorStop(0.75, 'rgba(120, 210, 255, 0.22)');
    sg.addColorStop(1, 'rgba(190, 240, 255, 0.55)');
    ctx.fillStyle = sg;
    ctx.beginPath();
    ctx.arc(cx, top + h / 2, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  if (f.shieldBroken) {
    ctx.save();
    ctx.globalAlpha = 0.6 + 0.4 * Math.sin(t * 0.02);
    ctx.strokeStyle = '#ff6b7f';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, top - 16, 9, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  // Attack arc.
  if (f.phase && f.attack !== 'shoot') {
    const heavy = f.attack === 'heavy';
    const reach = heavy ? 88 : 66;
    const alpha = f.phase === 'active' ? 0.85 : f.phase === 'windup' ? 0.22 : 0.12;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(cx, top + h / 2);
    ctx.scale(f.facing, 1);
    const ag = ctx.createLinearGradient(0, 0, reach + 40, 0);
    ag.addColorStop(0, 'rgba(255,255,255,0)');
    ag.addColorStop(0.55, heavy ? 'rgba(255,190,90,0.9)' : 'rgba(200,235,255,0.85)');
    ag.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = ag;
    ctx.beginPath();
    ctx.arc(0, 0, reach + 40, -0.85, 0.85);
    ctx.arc(0, 0, reach * 0.42, 0.85, -0.85, true);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  // Name tag.
  ctx.save();
  ctx.font = '600 15px Inter, system-ui, sans-serif';
  ctx.textAlign = 'center';
  const label = f.name;
  const tw = ctx.measureText(label).width;
  ctx.fillStyle = 'rgba(6, 9, 20, 0.66)';
  roundRect(cx - tw / 2 - 9, top - 34, tw + 18, 22, 6);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText(label, cx, top - 18);
  ctx.fillStyle = f.color;
  ctx.fillRect(cx - tw / 2 - 9, top - 13, tw + 18, 2);
  ctx.restore();
}

function drawRespawnPad(f) {
  if (!f.respawning) return;
  const [x, y] = [f.x, f.y];
  ctx.save();
  ctx.globalAlpha = 0.5;
  ctx.strokeStyle = f.color;
  ctx.lineWidth = 3;
  ctx.setLineDash([8, 8]);
  ctx.strokeRect(x - 45, y - 10, 90, 100);
  ctx.restore();
}

function drawProjectiles() {
  if (!state) return;
  for (const p of state.projectiles) {
    const ang = Math.atan2(p.vy, p.vx);
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(ang);
    const trail = ctx.createLinearGradient(-32, 0, 12, 0);
    trail.addColorStop(0, 'rgba(255,255,255,0)');
    trail.addColorStop(1, p.c);
    ctx.fillStyle = trail;
    roundRect(-32, -3.5, 44, 7, 3.5);
    ctx.fill();
    ctx.shadowColor = p.c;
    ctx.shadowBlur = 18;
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.arc(6, 0, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

function drawParticles() {
  for (const p of particles) {
    const a = p.life / p.max;
    ctx.save();
    ctx.globalAlpha = a;
    if (p.ring) {
      ctx.strokeStyle = p.color;
      ctx.lineWidth = 3 * a;
      ctx.beginPath();
      ctx.arc(p.x, p.y, (1 - a) * 150, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.fillStyle = p.color;
      ctx.shadowColor = p.color;
      ctx.shadowBlur = 10;
      ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    }
    ctx.restore();
  }
}

function drawBlastEdges() {
  // A soft warning band near the kill boundaries.
  const b = stage && stage.blast;
  if (!b) return;
  const bands = [
    [b.l, -400, 320, world.h + 900, 'left'],
    [b.r - 320, -400, 320, world.h + 900, 'right'],
  ];
  for (const [x, y, w, h, side] of bands) {
    const g = ctx.createLinearGradient(side === 'left' ? x + w : x, 0, side === 'left' ? x : x + w, 0);
    g.addColorStop(0, 'rgba(255, 70, 90, 0)');
    g.addColorStop(1, 'rgba(255, 70, 90, 0.16)');
    ctx.fillStyle = g;
    ctx.fillRect(x, y, w, h);
  }
}

function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const r = clamp((n >> 16) + amt, 0, 255);
  const g = clamp(((n >> 8) & 255) + amt, 0, 255);
  const b = clamp((n & 255) + amt, 0, 255);
  return `rgb(${r},${g},${b})`;
}

/* -------------------------------------------------------------- main loop */
function frame(t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, innerWidth, innerHeight);

  updateCamera();
  stepParticles();

  ctx.save();
  applyCamera();

  drawBackground(t);
  drawBlastEdges();
  drawStage(t);

  if (state) {
    for (const f of state.fighters) drawRespawnPad(f);
    drawProjectiles();
    for (const f of state.fighters) drawFighter(f, t);
  }
  drawParticles();

  ctx.restore();
  requestAnimationFrame(frame);
}

loadStatic();
connect();
requestAnimationFrame(frame);
})();
