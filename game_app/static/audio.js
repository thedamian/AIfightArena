/* Everything you hear is synthesised in the browser - no audio files to ship.
   Browsers block audio until the page has been interacted with, so the context
   is created lazily and resumed on the first click or keypress. */
const Sound = (() => {
  let ctx = null;
  let master = null;
  let musicGain = null;
  let musicTimer = null;
  let unlocked = false;

  function ensure() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.5;
    master.connect(ctx.destination);
    musicGain = ctx.createGain();
    musicGain.gain.value = 0.0;
    musicGain.connect(master);
    return ctx;
  }

  function unlock() {
    const c = ensure();
    if (c && c.state === 'suspended') c.resume();
    unlocked = true;
  }

  /* A single shaped note. */
  function note(freq, when, dur, {type = 'triangle', gain = 0.22, dest = null, glide = 0} = {}) {
    const c = ensure();
    if (!c) return;
    const t = c.currentTime + when;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (glide) osc.frequency.exponentialRampToValueAtTime(Math.max(20, freq * glide), t + dur);

    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + Math.min(0.03, dur * 0.2));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    osc.connect(g);
    g.connect(dest || master);
    osc.start(t);
    osc.stop(t + dur + 0.05);
  }

  /* Filtered noise burst - impacts, KOs. */
  function noise(when, dur, {gain = 0.3, freq = 900, q = 1.2} = {}) {
    const c = ensure();
    if (!c) return;
    const t = c.currentTime + when;
    const frames = Math.max(1, Math.floor(c.sampleRate * dur));
    const buf = c.createBuffer(1, frames, c.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < frames; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / frames);

    const src = c.createBufferSource();
    src.buffer = buf;
    const filter = c.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = freq;
    filter.Q.value = q;
    const g = c.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);

    src.connect(filter); filter.connect(g); g.connect(master);
    src.start(t);
  }

  const N = {
    C4: 261.63, D4: 293.66, E4: 329.63, F4: 349.23, G4: 392.00, A4: 440.00, B4: 493.88,
    C5: 523.25, D5: 587.33, E5: 659.25, F5: 698.46, G5: 783.99, A5: 880.00, C6: 1046.50,
    G3: 196.00, C3: 130.81, E3: 164.81, F3: 174.61, A3: 220.00,
  };

  /* ------------------------------------------------------------ background */
  function startMusic() {
    if (musicTimer || !ensure()) return;
    musicGain.gain.setTargetAtTime(0.5, ctx.currentTime, 1.2);

    // Brooding two-bar ostinato, kept low so it sits under the action.
    const bass = [N.C3, N.C3, N.G3, N.C3, N.F3, N.F3, N.E3, N.G3];
    const lead = [N.C5, N.E5, N.G5, N.E5, N.F5, N.A5, N.G5, N.E5];
    let step = 0;

    musicTimer = setInterval(() => {
      if (!ctx || ctx.state !== 'running') return;
      const i = step % 8;
      note(bass[i], 0, 0.42, {type: 'sine', gain: 0.16, dest: musicGain});
      if (i % 2 === 0) {
        note(lead[i], 0.02, 0.30, {type: 'triangle', gain: 0.055, dest: musicGain});
      }
      if (i === 0 || i === 4) noise(0, 0.07, {gain: 0.05, freq: 180, q: 0.8});
      step++;
    }, 260);
  }

  function stopMusic(fade = 0.6) {
    if (musicTimer) { clearInterval(musicTimer); musicTimer = null; }
    if (musicGain && ctx) musicGain.gain.setTargetAtTime(0.0001, ctx.currentTime, fade / 3);
  }

  /* ----------------------------------------------------------------- cues */
  const cue = {
    countdown(n) {
      const f = n === 0 ? N.C6 : [N.G4, N.A4, N.C5][Math.min(2, 3 - n)] || N.G4;
      note(f, 0, n === 0 ? 0.5 : 0.18, {type: 'square', gain: 0.24});
      if (n === 0) {
        note(N.E5, 0.02, 0.5, {type: 'square', gain: 0.16});
        note(N.G5, 0.04, 0.55, {type: 'square', gain: 0.13});
      }
    },

    hit() { noise(0, 0.09, {gain: 0.22, freq: 1300, q: 1.6}); },

    heavy() {
      noise(0, 0.17, {gain: 0.34, freq: 420, q: 0.9});
      note(120, 0, 0.16, {type: 'sawtooth', gain: 0.18, glide: 0.35});
    },

    shoot() { note(760, 0, 0.09, {type: 'square', gain: 0.10, glide: 0.4}); },

    ko() {
      noise(0, 0.42, {gain: 0.42, freq: 260, q: 0.6});
      [N.G4, N.E4, N.C4].forEach((f, i) =>
        note(f, i * 0.09, 0.26, {type: 'sawtooth', gain: 0.16, glide: 0.55}));
    },

    out() {
      [N.C5, N.G4, N.E4, N.C4].forEach((f, i) =>
        note(f, i * 0.11, 0.34, {type: 'triangle', gain: 0.2}));
    },

    /* Victory fanfare, then the announcer. */
    victory(name, characterName) {
      stopMusic(0.25);
      const seq = [
        [N.C5, 0.00, 0.16], [N.E5, 0.14, 0.16], [N.G5, 0.28, 0.16],
        [N.C6, 0.42, 0.52], [N.G5, 0.96, 0.16], [N.C6, 1.10, 0.85],
      ];
      seq.forEach(([f, at, d]) => {
        note(f, at, d, {type: 'square', gain: 0.24});
        note(f / 2, at, d, {type: 'triangle', gain: 0.14});
        note(f * 1.5, at, d * 0.8, {type: 'sine', gain: 0.07});
      });
      noise(0.42, 0.5, {gain: 0.2, freq: 3000, q: 0.5});
      noise(1.10, 0.9, {gain: 0.22, freq: 2400, q: 0.4});

      // Celebration loop under the announcement.
      setTimeout(() => {
        if (!ctx) return;
        musicGain.gain.setTargetAtTime(0.4, ctx.currentTime, 0.5);
        const melody = [N.C5, N.E5, N.G5, N.C6, N.G5, N.E5, N.F5, N.A5];
        let i = 0;
        musicTimer = setInterval(() => {
          note(melody[i % melody.length], 0, 0.26, {type: 'triangle', gain: 0.1, dest: musicGain});
          note(melody[i % melody.length] / 4, 0, 0.4, {type: 'sine', gain: 0.13, dest: musicGain});
          i++;
        }, 240);
      }, 2200);

      announce(`${name} wins as ${characterName}!`);
    },

    join() { note(N.G5, 0, 0.10, {type: 'sine', gain: 0.14}); note(N.C6, 0.08, 0.14, {type: 'sine', gain: 0.12}); },
  };

  /* Announcer via the platform speech engine, picking a lower voice if present. */
  function announce(text) {
    if (!('speechSynthesis' in window) || !unlocked) return;
    setTimeout(() => {
      try {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 0.92;
        u.pitch = 0.75;
        u.volume = 1.0;
        const voices = window.speechSynthesis.getVoices();
        const pick = voices.find(v => /daniel|alex|google uk english male|male/i.test(v.name));
        if (pick) u.voice = pick;
        window.speechSynthesis.speak(u);
      } catch (e) { /* announcer is optional */ }
    }, 1900);
  }

  window.addEventListener('pointerdown', unlock, {once: false});
  window.addEventListener('keydown', unlock, {once: false});

  return {cue, startMusic, stopMusic, unlock, isUnlocked: () => unlocked};
})();
