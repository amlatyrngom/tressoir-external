// Briefing player. The page that loads this defines four globals first:
//   TITLE  briefing title (string)
//   SLIDES [{ title, html, say, hold?, decision? }]
//   CUES   start time in seconds of each slide inside the audio track
//   TRACK  the whole narration as one base64 audio file (MIME below)
// and contains <div id="deck"></div> and <p id="diag" hidden></p>.
// Add #debug to the address to show the status line (audio route, wake lock, viewer size).

const MIME = 'audio/webm', N = SLIDES.length, SPEEDS = [1, 1.25, 1.5, 1.75];
const trackBytes = () => Uint8Array.from(atob(TRACK), c => c.charCodeAt(0));
const store = (key, value) => {
  try {
    if (value === undefined) return localStorage.getItem('deck.' + key);
    localStorage.setItem('deck.' + key, value);
  } catch (e) { return null; }
};

// Speed without raising the pitch: overlap-add time stretch (WSOLA) on decoded samples.
// Only the Web Audio route needs it; the audio element preserves pitch by itself.
function stretch(x, sr, r) {
  if (r === 1) return x;
  const W = Math.round(sr * 0.032) & ~1, Hs = W >> 1, S = Math.round(sr * 0.012), n = x.length;
  const win = new Float32Array(W);
  for (let k = 0; k < W; k++) win[k] = 0.5 - 0.5 * Math.cos(2 * Math.PI * k / W);
  const frames = Math.max(1, Math.floor((n - W - S) / (Hs * r))), y = new Float32Array(frames * Hs + W);
  let prev = 0;
  for (let f = 0; f < frames; f++) {
    let pos = Math.round(f * Hs * r);
    const nat = prev + Hs;
    if (f > 0 && nat + W < n) {
      let best = -Infinity, shift = 0;
      const lo = Math.max(-S, -pos), hi = Math.min(S, n - W - pos - 1);
      for (let d = lo; d <= hi; d += 2) {
        let c = 0;
        const a = pos + d;
        for (let k = 0; k < W; k += 4) c += x[a + k] * x[nat + k];
        if (c > best) { best = c; shift = d; }
      }
      pos += shift;
    }
    const o = f * Hs;
    for (let k = 0; k < W; k++) y[o + k] += x[pos + k] * win[k];
    prev = pos;
  }
  return y;
}

// Routes 1 and 2: one <audio> element playing one continuous track. Nothing depends on page
// timers, so it keeps going when a phone locks; the slide catches up when the page is visible.
class ElementTrack {
  constructor(kind) { this.kind = kind; this.el = new Audio(); this.el.preload = 'auto'; }
  open() {
    const el = this.el;
    return new Promise((ok, fail) => {
      const t = setTimeout(() => fail(new Error('timeout')), 6000);
      el.onloadedmetadata = () => { clearTimeout(t); ok(); };
      el.onerror = () => { clearTimeout(t); fail(new Error('media error')); };
      el.src = this.kind === 'data'
        ? 'data:' + MIME + ';base64,' + TRACK
        : URL.createObjectURL(new Blob([trackBytes()], { type: MIME }));
    });
  }
  play() { return this.el.play(); }
  pause() { this.el.pause(); }
  seek(k) { this.el.currentTime = CUES[k]; }
  setRate(r) {
    this.el.playbackRate = r;
    this.el.preservesPitch = this.el.webkitPreservesPitch = this.el.mozPreservesPitch = true;
  }
  pos() {
    const t = this.el.currentTime, total = this.el.duration || CUES[N - 1] + 1;
    let k = N - 1;
    while (k > 0 && t < CUES[k]) k--;
    const end = k + 1 < N ? CUES[k + 1] : total;
    return { slide: k, frac: Math.min(1, (t - CUES[k]) / (end - CUES[k])), ended: this.el.ended };
  }
}

// Route 3: Web Audio, for viewers that block the audio element (the Claude app's inline preview
// is one). Plays slide by slide from the decoded track. The system suspends it on a locked phone.
class WebAudioTrack {
  async open() {
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume();
    this.raw = await this.ctx.decodeAudioData(trackBytes().buffer);
    this.made = {}; this.k = 0; this.rate = 1; this.frac = 0; this.done = false;
  }
  segment(k, rate) {
    const key = k + '@' + rate;
    if (this.made[key]) return this.made[key];
    const sr = this.raw.sampleRate;
    const from = Math.floor(CUES[k] * sr), to = k + 1 < N ? Math.floor(CUES[k + 1] * sr) : this.raw.length;
    const y = stretch(this.raw.getChannelData(0).subarray(from, to), sr, rate);
    const buf = this.ctx.createBuffer(1, y.length, sr);
    buf.getChannelData(0).set(y);
    return this.made[key] = buf;
  }
  start(k, frac) {
    this.halt();
    const s = this.ctx.createBufferSource();
    s.buffer = this.segment(k, this.rate);
    s.connect(this.ctx.destination);
    this.node = s; this.k = k; this.done = false; this.dur = s.buffer.duration;
    const at = Math.min(frac || 0, 0.999) * this.dur;
    this.t0 = this.ctx.currentTime - at;
    s.onended = () => {
      if (this.node !== s) return;
      if (k < N - 1) this.start(k + 1, 0);
      else { this.node = null; this.done = true; this.frac = 1; }
    };
    s.start(0, at);
    // prepare the next slide ahead of time so there is no gap at the boundary
    if (k + 1 < N) setTimeout(() => { if (this.node === s) this.segment(k + 1, this.rate); }, 1200);
  }
  halt() { const n = this.node; this.node = null; if (n) { try { n.stop(); } catch (e) {} } }
  async play() {
    await this.ctx.resume();
    if (!this.node) this.start(this.done ? 0 : this.k, this.done ? 0 : this.frac);
  }
  pause() { this.ctx.suspend(); }
  seek(k) {
    const live = !!this.node && this.ctx.state === 'running';
    this.halt(); this.k = k; this.frac = 0; this.done = false;
    if (live) this.start(k, 0);
  }
  setRate(r) {
    const p = this.pos(), live = !!this.node;
    this.rate = r;
    if (live) this.start(p.slide, p.frac);
  }
  pos() {
    if (this.node) this.frac = Math.min(1, (this.ctx.currentTime - this.t0) / this.dur);
    return { slide: this.k, frac: this.frac, ended: this.done };
  }
}

const ROUTES = [
  ['audio element', () => new ElementTrack('data')],
  ['audio element', () => new ElementTrack('blob')],
  ['Web Audio', () => new WebAudioTrack()],
];
async function openEngine() {
  for (const [name, make] of ROUTES) {
    try { const e = make(); await e.open(); e.label = name; return e; } catch (err) {}
  }
  return null;
}

const svg = d => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
const ICON = {
  prev: svg('M6 5h2.4v14H6zM20 5v14L9.5 12z'),
  next: svg('M15.6 5H18v14h-2.4zM4 5v14l10.5-7z'),
  play: svg('M7 4v16l13-8z'),
  pause: svg('M6 4h4.2v16H6zM13.8 4H18v16h-4.2z'),
  sun: svg('M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM11 1.5h2v3.2h-2zM11 19.3h2v3.2h-2zM1.5 11h3.2v2H1.5zM19.3 11h3.2v2h-3.2zM4.1 5.5l1.4-1.4 2.3 2.3-1.4 1.4zM16.2 17.6l1.4-1.4 2.3 2.3-1.4 1.4zM4.1 18.5l2.3-2.3 1.4 1.4-2.3 2.3zM16.2 6.4l2.3-2.3 1.4 1.4-2.3 2.3z'),
  moon: svg('M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7z'),
};

(function Deck(root) {
  let i = 0, playing = false, engine = null, opening = false, noAudio = false, awake = null, wakeState = 'not requested';
  let rate = SPEEDS.includes(+store('rate')) ? +store('rate') : 1, text = store('text') === '1';

  root.innerHTML = `<div class="top"><div class="stage"><div class="slide"></div></div>
    <div class="pills"></div>
    <div class="bar">
      <div class="nav"><button class="prev" aria-label="Previous slide">${ICON.prev}</button><button class="play" aria-label="Play or pause"></button><button class="next" aria-label="Next slide">${ICON.next}</button></div>
      <span class="count"></span>
      <button class="speed" aria-label="Playback speed"></button>
      <button class="textbtn">Text</button>
      <button class="theme" aria-label="Switch between light and dark"></button>
    </div></div>
    <div class="notes" hidden><p></p></div>
    <div class="note" hidden>Audio could not play in this viewer. Use the text and the arrows.</div>`;

  const $ = q => root.querySelector(q);
  const stage = $('.stage'), slide = $('.slide'), pills = $('.pills'), notes = $('.notes'), diagEl = document.getElementById('diag');
  if (diagEl) diagEl.hidden = location.hash !== '#debug';

  SLIDES.forEach((it, k) => {
    const b = document.createElement('button');
    b.title = it.title;
    b.setAttribute('aria-label', 'Slide ' + (k + 1) + ': ' + it.title);
    b.innerHTML = '<span><i></i></span>';
    if (it.decision) b.dataset.ask = '1';        // drawn as a small tick on the progress bar
    b.onclick = () => go(k);
    pills.appendChild(b);
  });

  // One layout everywhere: slide, progress and controls pinned on top; text below at natural length.
  const scale = () => { slide.style.transform = `scale(${stage.clientWidth / 960})`; };
  const layout = () => { if (root.clientWidth) { root.classList.toggle('narrow', root.clientWidth < 560); scale(); } };
  new ResizeObserver(layout).observe(root);
  new ResizeObserver(scale).observe(stage);
  window.addEventListener('resize', layout);

  const diag = () => {
    if (!diagEl) return;
    const audio = noAudio ? 'none available, text only' : engine ? engine.label : 'not started';
    diagEl.textContent = `Audio: ${audio}. Screen kept awake while playing: ${wakeState}. Viewer: ${window.innerWidth}×${window.innerHeight}.`;
  };

  function render() {
    const it = SLIDES[i];
    slide.innerHTML = it.html;
    notes.hidden = !text;
    notes.querySelector('p').textContent = it.say;
    root.classList.toggle('text-on', text);
    layout();
    [...pills.children].forEach((b, k) => {
      b.className = k < i ? 'done' : k === i ? 'cur' : '';
      if (k !== i) b.querySelector('i').style.width = '';
    });
    $('.play').innerHTML = playing ? ICON.pause : ICON.play;
    $('.play').style.display = noAudio ? 'none' : '';
    $('.speed').style.visibility = noAudio ? 'hidden' : '';
    $('.speed').textContent = rate + '×';
    $('.prev').disabled = i === 0;
    $('.next').disabled = i === N - 1;
    $('.textbtn').setAttribute('aria-pressed', text);
    $('.count').textContent = (i + 1) + ' / ' + N;
    $('.note').hidden = !noAudio;
    diag();
    if (playing && 'mediaSession' in navigator) {
      try { navigator.mediaSession.metadata = new MediaMetadata({ title: it.title, artist: TITLE, album: 'Briefing' }); } catch (e) {}
    }
  }

  // While playing, the audio position is the source of truth for which slide is shown.
  function tick() {
    if (!engine) return;
    const p = engine.pos();
    if (p.slide !== i) { i = p.slide; render(); }
    pills.children[i].querySelector('i').style.width = (p.frac * 100).toFixed(1) + '%';
    if (p.ended && playing) { playing = false; sleep(); render(); }
    if (playing) requestAnimationFrame(tick);
  }

  async function wake() {
    try { awake = await navigator.wakeLock.request('screen'); wakeState = 'yes'; }
    catch (e) { wakeState = 'not allowed here'; }
    diag();
  }
  function sleep() { if (awake) { awake.release().catch(() => {}); awake = null; } }

  async function play() {
    if (noAudio || opening) return;
    if (!engine) {
      opening = true; engine = await openEngine(); opening = false;
      if (!engine) { noAudio = true; text = true; render(); return; }   // fall back to reading
      engine.setRate(rate); engine.seek(i);
    } else if (engine.pos().ended) engine.seek(0);
    try { await engine.play(); } catch (e) { diag(); return; }
    playing = true; wake(); render(); tick();
  }
  function pause() { if (!playing) return; playing = false; engine.pause(); sleep(); render(); }
  function go(k) {
    i = Math.max(0, Math.min(N - 1, k));
    if (engine) engine.seek(i);
    render();
    if (engine) tick();
  }

  $('.play').onclick = () => playing ? pause() : play();
  $('.prev').onclick = () => go(i - 1);
  $('.next').onclick = () => go(i + 1);
  $('.speed').onclick = () => {
    rate = SPEEDS[(SPEEDS.indexOf(rate) + 1) % SPEEDS.length];
    store('rate', rate);
    if (engine) engine.setRate(rate);
    render();
  };
  $('.textbtn').onclick = () => { text = !text; store('text', text ? '1' : '0'); render(); };

  document.addEventListener('keydown', e => {
    if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.code === 'Space') { e.preventDefault(); playing ? pause() : play(); }
    else if (e.key === 'ArrowRight') go(i + 1);
    else if (e.key === 'ArrowLeft') go(i - 1);
  });
  // A mouse click must not leave a focus ring behind; keyboard focus still shows one.
  root.addEventListener('click', e => { const b = e.target.closest('button'); if (b && e.detail > 0) b.blur(); });

  // Light or dark: follows the system until the viewer picks one; the choice is remembered.
  const docEl = document.documentElement, systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const isDark = () => docEl.dataset.theme ? docEl.dataset.theme === 'dark' : systemDark.matches;
  const paintTheme = () => {
    const t = $('.theme');
    t.innerHTML = isDark() ? ICON.sun : ICON.moon;
    t.title = isDark() ? 'Switch to light' : 'Switch to dark';
  };
  if (['light', 'dark'].includes(store('theme'))) docEl.dataset.theme = store('theme');
  $('.theme').onclick = () => { const next = isDark() ? 'light' : 'dark'; docEl.dataset.theme = next; store('theme', next); paintTheme(); };
  systemDark.addEventListener('change', paintTheme);
  paintTheme();

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && playing) { wake(); tick(); }
  });
  if ('mediaSession' in navigator) {
    try {
      const ms = navigator.mediaSession;
      ms.setActionHandler('play', play);
      ms.setActionHandler('pause', pause);
      ms.setActionHandler('previoustrack', () => go(i - 1));
      ms.setActionHandler('nexttrack', () => go(i + 1));
    } catch (e) {}
  }
  render();
})(document.getElementById('deck'));
