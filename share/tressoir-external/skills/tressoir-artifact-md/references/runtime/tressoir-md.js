/* tressoir-md.js — USER_ARTIFACT_MD core runtime (classic IIFE, eval-free).
 *
 * Projects a `.tressoir.md` source into the LOCKED user-artifact DOM (artifact.css) and wires
 * the runtime behaviors. Loaded as a classic <script src> alongside the vendored UMD libs;
 * consumed by the bridge webview (which calls TressoirMd.project() then morphs) and by the
 * standalone SHIM (TressoirMd.render()).
 *
 * v2 authoring surface (minimal): YAML front-matter (title/description/links) + depth-styled
 * markdown headings + THREE container directives — `::::card{title oneliner state}` (4 colons,
 * explicit close, groups items), `:::item{oneliner}` (3 colons, reveal row), `:::input{key}`
 * (3 colons, a decision: question + markdown options + a bound text box) — plus plain markdown,
 * fenced code (```lang / ```diff), and raw HTML/SVG passthrough. The only nesting is
 * ::::card(4) ⊃ :::item(3). The locked artifact.css is OUTPUT-side, so the projector still
 * emits the same locked DOM classes (.milestone / .ctx-item / .m-decision / ...) from this
 * simpler input.
 *
 * Dependencies (window globals, all eval-free UMD): TressoirRemark (unified/remark/rehype
 * bundle), jsyaml, Prism, CodeMirror. No `eval`/`new Function`; projection is a mdast->HTML
 * string transform + classic DOM wiring.
 */
(function (global) {
  'use strict';

  // ----------------------------------------------------------------- helpers
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escAttr(s) {
    return esc(s).replace(/"/g, '&quot;');
  }
  function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
  function textOf(node) {
    if (!node) return '';
    if (node.type === 'text' || node.type === 'inlineCode') return node.value || '';
    if (node.children) return node.children.map(textOf).join('');
    return '';
  }

  // ----------------------------------------------------------- projection
  function getRemark() {
    var R = global.TressoirRemark;
    if (!R) throw new Error('TressoirRemark (remark UMD bundle) is not loaded.');
    return R;
  }

  // mdast (array of nodes) -> HTML string, converting fenced code blocks to the locked
  // pre.code / pre.diff form the runtime highlighter expects (data-lang). Raw HTML/SVG/scripts
  // pass through via rehype-raw. Markdown headings (### / ####) pass through to <h3>/<h4>,
  // styled by the appended depth rules in artifact.css.
  function renderCodeBlock(node) {
    var lang = String(node.lang || '').toLowerCase();
    if (lang === 'diff') {
      return '<pre class="diff" data-lang="">' + esc(node.value) + '</pre>';
    }
    return '<pre class="code" data-lang="' + escAttr(lang) + '">' + esc(node.value) + '</pre>';
  }
  function transformCodeDeep(node) {
    if (!node || typeof node !== 'object') return node;
    if (node.type === 'code') {
      return { type: 'html', value: renderCodeBlock(node) };
    }
    if (node.children) {
      node.children = node.children.map(transformCodeDeep);
    }
    return node;
  }
  function mdastToHtml(nodes) {
    var R = getRemark();
    var proc = R.unified()
      .use(R.remarkGfm)
      .use(R.remarkRehype, { allowDangerousHtml: true })
      .use(R.rehypeRaw)
      .use(R.rehypeStringify, { allowDangerousHtml: true });
    var root = { type: 'root', children: nodes.map(transformCodeDeep) };
    var hast = proc.runSync(root);
    return proc.stringify(hast);
  }

  // ---- ::::card{title oneliner state} -> .milestone reveal card (groups items).
  // title / oneliner / state are injected RAW so an author can put an inline badge or other
  // inline HTML in them (e.g. state="<span class='badge ok'>Done</span>"). `open` (or
  // `selected`) starts the card expanded.
  function renderCard(node) {
    var a = node.attributes || {};
    var open = ('open' in a) || ('selected' in a);
    var title = a.title || '';
    var oneliner = a.oneliner || '';
    var state = a.state || '';
    var body = renderBlocks(node.children || []);
    return '<section class="milestone' + (open ? ' selected' : '') + '" data-morph-keep-class="selected">' +
      '<div class="m-head" role="button" tabindex="0" aria-expanded="' + (open ? 'true' : 'false') + '">' +
      '<div><div class="m-title">' + title + '</div>' +
      (oneliner ? '<div class="m-intent">' + oneliner + '</div>' : '') + '</div>' +
      (state ? '<span class="m-state">' + state + '</span>' : '') + '</div>' +
      '<div class="m-detail">' + body + '</div></section>';
  }

  // ---- :::item{oneliner} -> .ctx-item disclosure row. oneliner injected RAW (inline HTML ok).
  function renderItem(node) {
    var a = node.attributes || {};
    var open = ('open' in a);
    var oneliner = a.oneliner || a.title || '';
    var body = renderBlocks(node.children || []);
    return '<div class="ctx-item' + (open ? ' open' : '') + '" data-morph-keep-class="open">' +
      '<button class="ctx-item-head" type="button" aria-expanded="' + (open ? 'true' : 'false') + '">' +
      '<span class="dot"></span>' + oneliner + '</button>' +
      '<div class="ctx-item-body">' + body + '</div></div>';
  }

  // ---- :::input{key} -> .ctx-item.m-decision.m-input decision row. The head is the question
  // (the `oneliner`/`question` attr, else the first paragraph). The body holds the options
  // (plain markdown) + a bound text box; typing answers it (read back from interactions.json).
  function renderInput(node) {
    var a = node.attributes || {};
    var key = a.key || ('input.' + Math.random().toString(36).slice(2, 8));
    var children = (node.children || []).slice();
    var question = a.oneliner || a.question || '';
    if (!question && children.length && children[0].type === 'paragraph') {
      question = textOf(children[0]);
      children = children.slice(1);
    }
    if (!question) question = 'Decision';
    var body = renderBlocks(children);
    var ph = 'Type a pick, a tweak, or a question for the next pass...';
    return '<div class="ctx-item m-decision m-input" data-key="' + escAttr(key) + '" data-morph-key="tressoir-input:' + escAttr(key) + '" data-morph-keep-class="open">' +
      '<button class="ctx-item-head" type="button" aria-expanded="false">' +
      '<span class="dec-check" aria-hidden="true"></span>' +
      '<span class="dec-name">' + esc(question) + '</span></button>' +
      '<div class="ctx-item-body">' + body +
      '<div class="other-box show" data-morph-skip>' +
      '<textarea data-input-key="' + escAttr(key) + '" placeholder="' + escAttr(ph) + '"></textarea></div>' +
      '</div></div>';
  }

  // ---- generic block renderer (recursive). Groups consecutive cards into .milestones and
  // consecutive item/input rows into a .ctx-list; everything else is plain markdown.
  function isCardDir(n) { return n.type === 'containerDirective' && n.name === 'card'; }
  function isRowDir(n) { return n.type === 'containerDirective' && (n.name === 'item' || n.name === 'input'); }

  function renderBlocks(nodes) {
    var out = '', i = 0, prose = [];
    function flushProse() { if (prose.length) { out += mdastToHtml(prose); prose = []; } }
    while (i < nodes.length) {
      var n = nodes[i];
      if (isCardDir(n)) {
        flushProse();
        var cards = [];
        while (i < nodes.length && isCardDir(nodes[i])) { cards.push(nodes[i]); i += 1; }
        out += '<div class="milestones">' + cards.map(renderCard).join('') + '</div>';
        continue;
      }
      if (isRowDir(n)) {
        flushProse();
        var rows = [];
        while (i < nodes.length && isRowDir(nodes[i])) { rows.push(nodes[i]); i += 1; }
        out += '<div class="ctx-list">' + rows.map(function (it) {
          return it.name === 'input' ? renderInput(it) : renderItem(it);
        }).join('') + '</div>';
        continue;
      }
      prose.push(n); i += 1;
    }
    flushProse();
    return out;
  }

  function renderHeader(fm) {
    var title = esc(fm.title || 'Untitled');
    var type = fm.tressoir;
    var badge = (type != null && type !== '') ? '<span class="badge type">' + esc(cap(String(type))) + '</span>' : '';
    var desc = fm.description ? '<p class="dek">' + esc(fm.description) + '</p>' : '';
    var ph = 'Type any questions, constraints, or edits for the next pass. Markdown; fenced code blocks highlight.';
    var ff = '<div class="head-feedback" data-morph-skip>' +
      '<textarea id="ff-editor" placeholder="' + escAttr(ph) + '"></textarea></div>';
    return '<header class="plan-head"><div class="title-row"><h1>' + title + '</h1>' + badge + '</div>' +
      desc + ff + '</header>';
  }

  function project(markdown) {
    var R = getRemark();
    var parseProc = R.unified().use(R.remarkParse).use(R.remarkGfm).use(R.remarkFrontmatter, ['yaml']).use(R.remarkDirective);
    var tree = parseProc.parse(markdown);
    var fm = {};
    var fmNode = null;
    tree.children.forEach(function (n) { if (n.type === 'yaml' && !fmNode) fmNode = n; });
    if (fmNode) { try { fm = global.jsyaml.load(fmNode.value) || {}; } catch (e) { fm = {}; } }
    var content = tree.children.filter(function (n) { return n.type !== 'yaml'; });
    var preamble = [], sections = [], cur = null;
    content.forEach(function (n) {
      if (n.type === 'heading' && n.depth === 2) { cur = { title: textOf(n), blocks: [] }; sections.push(cur); }
      else if (cur) { cur.blocks.push(n); }
      else { preamble.push(n); }
    });
    var body = renderBlocks(preamble);
    sections.forEach(function (s) {
      body += '<section class="ua-section"><h2 class="section">' + esc(s.title) + '</h2>' +
        renderBlocks(s.blocks) + '</section>';
    });
    var footer = '<footer class="gen"><span id="gen-marker">Generated by Tressoir. Consult the user-artifact-md skill before editing.</span></footer>';
    return '<div class="wrap">' + renderHeader(fm) + body + footer + '</div>';
  }

  // ------------------------------------------------------------- behaviors
  var qsa = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  function adaptTheme() {
    function isDarkBg() {
      try {
        var probe = document.createElement('div');
        probe.style.cssText = 'background:var(--vscode-editor-background, transparent);position:absolute;left:-9999px;';
        document.body.appendChild(probe);
        var c = getComputedStyle(probe).backgroundColor;
        document.body.removeChild(probe);
        var m = c && c.match(/[\d.]+/g);
        if (!m || m.length < 3) return null;
        if (m.length >= 4 && parseFloat(m[3]) === 0) return null;
        var lum = 0.2126 * (+m[0]) + 0.7152 * (+m[1]) + 0.0722 * (+m[2]);
        return lum < 128;
      } catch (_) { return null; }
    }
    var cls = (document.body && document.body.className) || '';
    var dark;
    if (/vscode-dark|vscode-high-contrast(?!-light)/.test(cls)) dark = true;
    else if (/vscode-light|vscode-high-contrast-light/.test(cls)) dark = false;
    else dark = isDarkBg();
    if (dark === null || dark === undefined) return;
    document.documentElement.setAttribute('data-vscode-theme-kind', dark ? 'vscode-dark' : 'vscode-light');
  }

  function readInteraction(key) {
    if (global.tressoirNotebook && typeof global.tressoirNotebook.getInteraction === 'function') {
      try { return global.tressoirNotebook.getInteraction(key); } catch (_) {}
    }
    return undefined;
  }
  function noteInteraction(key, value) {
    if (global.tressoirNotebook && typeof global.tressoirNotebook.storeInteraction === 'function') {
      try { global.tressoirNotebook.storeInteraction(key, value); } catch (_) {}
    }
  }

  function highlightCode() {
    function escTxt(t) { return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
    var LANG_ALIASES = { py: 'python', rs: 'rust', ts: 'typescript', tsx: 'tsx', jsx: 'jsx', js: 'javascript',
      sh: 'bash', shell: 'bash', zsh: 'bash', yml: 'yaml', md: 'markdown', 'c++': 'cpp', 'c#': 'csharp', cs: 'csharp', rb: 'ruby', kt: 'kotlin' };
    function grammarFor(lang) {
      if (!global.Prism || !global.Prism.languages || !lang) return null;
      var key = LANG_ALIASES[lang] || lang;
      return global.Prism.languages[key] || null;
    }
    function hl(code, lang) {
      var g = grammarFor(lang);
      if (g && global.Prism) { try { return global.Prism.highlight(code, g, lang); } catch (_) {} }
      return escTxt(code);
    }
    qsa('pre.code').forEach(function (pre) {
      var lang = pre.getAttribute('data-lang') || '';
      pre.innerHTML = hl(pre.textContent.replace(/^\n/, '').replace(/\s+$/, ''), lang);
    });
    qsa('pre.diff').forEach(function (pre) {
      // Idempotent: the diff highlighter joins per-line <span> with '' (dropping the
      // source newlines), so a second pass would collapse everything onto one line.
      // After a real bridge morph the <pre> is reset to raw text (no .dl), so this
      // guard only short-circuits a redundant re-apply on the SAME DOM.
      if (pre.querySelector('.dl')) return;
      var lang = pre.getAttribute('data-lang') || '';
      var lines = pre.textContent.replace(/^\n/, '').replace(/\n$/, '').split('\n');
      pre.innerHTML = lines.map(function (line) {
        if (line.slice(0, 2) === '@@') return '<span class="dl dl-hunk">' + escTxt(line) + '</span>';
        var c = line.charAt(0), cls, marker, bodyTxt;
        if (c === '+') { cls = 'dl-add'; marker = '+'; bodyTxt = line.slice(1); }
        else if (c === '-') { cls = 'dl-del'; marker = '-'; bodyTxt = line.slice(1); }
        else { cls = 'dl-ctx'; marker = ' '; bodyTxt = (c === ' ' ? line.slice(1) : line); }
        return '<span class="dl ' + cls + '"><span class="dm">' + marker + '</span>' + hl(bodyTxt, lang) + '</span>';
      }).join('');
    });
  }

  function applyRuntimeUI() {
    var marker = document.getElementById('gen-marker');
    if (marker) marker.textContent = 'Generated by Tressoir \u2014 ' + new Date().toLocaleString() + '. Consult the user-artifact-md skill before editing.';
    highlightCode();
    // Restore :::input answers: the value is a raw string stored under data-input-key (like
    // free_form_feedback); a non-empty value marks the decision .resolved (green check).
    qsa('textarea[data-input-key]').forEach(function (ta) {
      var key = ta.getAttribute('data-input-key');
      if (!key) return;
      var stored = readInteraction(key);
      var val = stored && (typeof stored === 'object' ? (stored.text != null ? stored.text : stored.value) : stored);
      if (typeof val === 'string') {
        if (ta.value !== val) ta.value = val;
        var dec = ta.closest('.m-decision');
        if (dec && val.length) dec.classList.add('resolved');
      }
    });
    initFreeForm();
  }

  // CodeMirror's markdown fenced-code highlighting resolves the inner mode via
  // `findModeByName(lang)`, which matches mode NAME/ALIASES only — NOT file extensions.
  // So a fence like ```py (an extension, not an alias) fails to resolve and renders
  // unhighlighted, even though the python mode is loaded. Patch findModeByName to fall
  // back to findModeByExtension so ```py / ```rs / ```ts / ```sh resolve. Idempotent.
  function patchModeResolution() {
    var CM = global.CodeMirror;
    if (!CM || CM.__tressoirModePatched || typeof CM.findModeByName !== 'function') return;
    var origByName = CM.findModeByName;
    CM.findModeByName = function (name) {
      var hit = origByName.call(this, name);
      if (!hit && typeof CM.findModeByExtension === 'function' && name) {
        hit = CM.findModeByExtension(String(name).toLowerCase());
      }
      return hit;
    };
    CM.__tressoirModePatched = true;
  }

  function initFreeForm() {
    if (typeof global.CodeMirror === 'undefined') return;
    patchModeResolution();
    var ta = document.getElementById('ff-editor');
    if (!ta || ta.__cmMounted) return;
    ta.__cmMounted = true;
    // Namespace the feedback key by source basename (provider.ts emits data-source-name, e.g.
    // `PLAN`) so sibling artifacts sharing one folder's interactions.json don't collide. The SHIM
    // / preview harness sets no such attr -> falls back to the plain legacy key.
    var bodyData = (document.body && document.body.dataset) || {};
    var srcName = bodyData.sourceName || '';
    // New providers supply the complete, injective, bounded key. `sourceName` keeps the previous
    // namespaced runtime compatible; a plain fallback remains only for the standalone SHIM.
    var FF_KEY = bodyData.feedbackKey || ((srcName ? srcName + '-' : '') + 'free_form_feedback');
    var prior = readInteraction(FF_KEY);
    if (typeof prior === 'string') ta.value = prior;
    else if (prior && typeof prior.value === 'string') ta.value = prior.value;
    var cm = global.CodeMirror.fromTextArea(ta, {
      mode: { name: 'markdown', fencedCodeBlockHighlighting: true },
      lineWrapping: true, lineNumbers: false,
      placeholder: ta.getAttribute('placeholder') || ''
    });
    var saveTimer = null;
    function flush() { if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; } noteInteraction(FF_KEY, cm.getValue()); }
    cm.on('change', function () { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(flush, 500); });
    cm.on('blur', flush);
    document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(); });
    global.addEventListener('pagehide', flush);
    global.__ffcm = cm;
  }

  // Event delegation (morph-safe; bound to document ONCE).
  var _delegated = false;
  var _inputTimers = {};
  function initDelegation() {
    if (_delegated) return; _delegated = true;
    document.addEventListener('click', function (e) {
      var t = e.target; if (!t || !t.closest) return;
      var openFileEl = t.closest('[data-open-file]');
      if (openFileEl) {
        e.preventDefault();
        var rel = openFileEl.getAttribute('data-open-file');
        if (rel && global.tressoirNotebook && typeof global.tressoirNotebook.openFile === 'function') global.tressoirNotebook.openFile(rel);
        return;
      }
      var ctxHead = t.closest('.ctx-item-head');
      if (ctxHead) {
        var item = ctxHead.closest('.ctx-item');
        if (item) { var on = item.classList.toggle('open'); ctxHead.setAttribute('aria-expanded', on ? 'true' : 'false'); }
        return;
      }
      var mHead = t.closest('.m-head');
      if (mHead) {
        var msx = mHead.closest('.milestone');
        if (msx) { var onm = msx.classList.toggle('selected'); mHead.setAttribute('aria-expanded', onm ? 'true' : 'false'); }
        return;
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var t = e.target; if (!t || !t.closest) return;
      // ctx-item-head / openFile are real <button>s (native Enter/Space) — only the div-based
      // .m-head needs explicit keyboard activation.
      var mHead = t.closest('.m-head');
      if (mHead) { e.preventDefault(); var ms = mHead.closest('.milestone'); if (ms) { var onm = ms.classList.toggle('selected'); mHead.setAttribute('aria-expanded', onm ? 'true' : 'false'); } return; }
    });
    // :::input text box -> mark .resolved live + persist the raw string (debounced).
    document.addEventListener('input', function (e) {
      var t = e.target;
      if (!t || t.tagName !== 'TEXTAREA' || typeof t.getAttribute !== 'function') return;
      var key = t.getAttribute('data-input-key');
      if (!key) return;
      var dec = t.closest && t.closest('.m-decision');
      if (dec) dec.classList.toggle('resolved', !!String(t.value).trim());
      if (_inputTimers[key]) clearTimeout(_inputTimers[key]);
      var val = t.value;
      _inputTimers[key] = setTimeout(function () { noteInteraction(key, val); }, 500);
    });
    // Flush on blur (capture phase — blur does not bubble).
    document.addEventListener('blur', function (e) {
      var t = e.target;
      if (!t || t.tagName !== 'TEXTAREA' || typeof t.getAttribute !== 'function') return;
      var key = t.getAttribute('data-input-key');
      if (!key) return;
      if (_inputTimers[key]) { clearTimeout(_inputTimers[key]); _inputTimers[key] = null; }
      noteInteraction(key, t.value);
    }, true);
  }

  var _themeObserver = false;
  function applyBehaviors() {
    adaptTheme();
    if (!_themeObserver) {
      _themeObserver = true;
      try {
        var mo = new MutationObserver(adaptTheme);
        if (document.body) mo.observe(document.body, { attributes: true, attributeFilter: ['class'] });
      } catch (_) {}
    }
    initDelegation();
    applyRuntimeUI();
  }

  // Re-apply on every bridge render (full + morph): the projected DOM carries no init script.
  document.addEventListener('tressoir:render', function () { applyBehaviors(); });

  // ----------------------------------------------------------------- render (SHIM/standalone)
  function recreateScripts(container) {
    var scripts = Array.prototype.slice.call(container.querySelectorAll('script'))
      .filter(function (s) { return !s.hasAttribute('data-tressoir-script-ran'); });
    scripts.forEach(function (old) {
      var fresh = document.createElement('script');
      Array.prototype.slice.call(old.attributes).forEach(function (a) { fresh.setAttribute(a.name, a.value); });
      fresh.setAttribute('data-tressoir-script-ran', '1');
      fresh.textContent = old.textContent;
      old.replaceWith(fresh);
    });
  }
  function render(markdown, hostEl, bridge) {
    var host = hostEl || document.getElementById('app');
    if (bridge && !global.tressoirNotebook) { try { global.tressoirNotebook = bridge; } catch (_) {} }
    host.innerHTML = project(markdown);
    recreateScripts(host);
    applyBehaviors();
    try { document.dispatchEvent(new CustomEvent('tressoir:render', { detail: { phase: 'full' } })); } catch (_) {}
    return host;
  }

  // ----------------------------------------------------------------- lint
  // Pure static checker (NO DOM). Reuses the SAME remark + js-yaml parse as project() so its
  // verdict cannot diverge from what the editor actually renders. Returns an array of
  // { level: 'error'|'warn'|'info', line: <1-based>, msg: <string> }, flagging the silent
  // failure modes the renderer would otherwise swallow. Consumed by the Node
  // flows/scripts/check_md.js frontend so an agent can self-check a `.tressoir.md` before render.
  function lint(markdown) {
    var findings = [];
    function add(level, line, msg) { findings.push({ level: level, line: line || 0, msg: msg }); }
    function lineOf(n) { return (n && n.position && n.position.start && n.position.start.line) || 0; }

    // Flat text of an AST subtree (text + inline code), for length/heading checks.
    function plainText(n) {
      if (!n || typeof n !== 'object') return '';
      if (n.type === 'text' || n.type === 'inlineCode') return n.value || '';
      if (n.children) return n.children.map(plainText).join('');
      return '';
    }
    // The visible lifecycle label inside a card `state=` badge (HTML tags stripped).
    function stateLabel(a) {
      var s = (a && a.state != null) ? String(a.state) : '';
      return s.replace(/<[^>]*>/g, '').trim().toLowerCase();
    }
    // Lower-cased set of heading texts anywhere inside a card subtree.
    function headingTextsIn(node) {
      var found = {};
      (function rec(n) {
        if (!n || typeof n !== 'object') return;
        if (n.type === 'heading') found[plainText(n).trim().toLowerCase()] = true;
        if (n.children) n.children.forEach(rec);
      })(node);
      return found;
    }
    // Track explicit :::input keys to flag duplicates (warning, per accepted D2).
    var seenInputKeys = {};

    // Card lifecycle vs required sections (all warnings; exit status unchanged).
    function lintCard(node) {
      var line = lineOf(node), a = node.attributes || {};
      if (a.title != null && String(a.title).length > 200) {
        add('warn', line, '::::card title exceeds 200 characters — keep the visible title skimmable and put depth in the body');
      }
      if (a.title == null || String(a.title) === '') {
        add('warn', line, '::::card has no `title=` (the card head will be blank)');
      }
      var label = stateLabel(a);
      if (label === '') return;
      var headings = headingTextsIn(node);
      var hasPlanned = !!headings['planned changes'];
      var hasReport = !!headings['completion report'];
      if (label === 'planning' || label === 'implementing') {
        if (!hasPlanned) add('warn', line, '::::card is `' + label + '` but has no `#### Planned Changes` — show every planned edit as a named diff before handoff');
      } else if (label === 'review' || label === 'completed') {
        if (!hasReport && !hasPlanned) add('warn', line, '::::card is `' + label + '` but has no `#### Completion Report` or `#### Planned Changes`');
      } else if (label === 'tbd') {
        if (hasPlanned) add('warn', line, '::::card is `TBD` but already has `#### Planned Changes` — a TBD milestone should carry only a one-line overview');
      }
    }

    var R = getRemark();
    var tree;
    try {
      tree = R.unified().use(R.remarkParse).use(R.remarkGfm)
        .use(R.remarkFrontmatter, ['yaml']).use(R.remarkDirective).parse(markdown);
    } catch (e) {
      add('error', 0, 'markdown failed to parse: ' + (e && e.message || e));
      return findings;
    }

    // ---- front-matter: optional, but if present must be a valid YAML mapping.
    var fmNode = null;
    tree.children.forEach(function (n) { if (n.type === 'yaml' && !fmNode) fmNode = n; });
    if (!fmNode) {
      add('warn', 1, 'no YAML front-matter (a `title:` becomes the H1, `description:` the dek)');
    } else {
      var fmLine = lineOf(fmNode) || 1;
      var fm, fmOk = true;
      try { fm = global.jsyaml.load(fmNode.value); }
      catch (e) { fmOk = false; add('error', fmLine, 'front-matter YAML is invalid: ' + (e && e.message || e)); }
      if (fmOk) {
        if (fm == null) {
          add('warn', fmLine, 'front-matter is empty');
        } else if (typeof fm !== 'object' || Array.isArray(fm)) {
          add('error', fmLine, 'front-matter is not a YAML mapping');
        } else {
          var ttype = fm.tressoir;
          var allowed = ['plan', 'research', 'interactive'];
          if (ttype != null && ttype !== '' && allowed.indexOf(String(ttype)) < 0) {
            add('warn', fmLine, 'front-matter `tressoir: ' + ttype + '` is not one of plan | research | interactive (type is optional)');
          }
          if (fm.title == null || String(fm.title) === '') {
            add('warn', fmLine, 'front-matter missing `title:` (header will show "Untitled")');
          }
        }
      }
    }

    // ---- :::input — needs a `key=` (read-back) and a question (head text).
    function lintInput(node) {
      var line = lineOf(node), a = node.attributes || {};
      if (a.key == null || String(a.key) === '') {
        add('error', line, ':::input has no `key=` — the human answer cannot be read back from interactions.json');
      } else {
        var inputKey = String(a.key);
        if (inputKey === 'free_form_feedback' || /-free_form_feedback$/.test(inputKey)) {
          add('error', line, ':::input uses a reserved free-form feedback key — choose a different unique `key=`');
        } else if (seenInputKeys[inputKey]) {
          add('warn', line, ':::input key `' + inputKey + '` is used by more than one input — reuse binds both boxes to the same value; give each decision a unique `key=`');
        } else {
          seenInputKeys[inputKey] = true;
        }
      }
      var hasQ = (a.oneliner != null && a.oneliner !== '') || (a.question != null && a.question !== '');
      var qText = '';
      if (a.oneliner != null && a.oneliner !== '') qText = String(a.oneliner);
      else if (a.question != null && a.question !== '') qText = String(a.question);
      if (!hasQ) {
        var kids = node.children || [];
        var leadPara = kids.length && kids[0].type === 'paragraph';
        if (!leadPara) add('warn', line, ':::input has no question — add a leading paragraph or an `oneliner=` attribute (otherwise the head reads "Decision")');
        else qText = plainText(kids[0]);
      }
      if (qText.length > 200) {
        add('warn', line, ':::input question first paragraph exceeds 200 characters — keep the visible question short and put depth in the options/body');
      }
    }

    // ---- directive names + prose-in-plain-fence heuristic (one walk).
    var KNOWN = { card: 1, item: 1, input: 1 };
    var CODE_HINT = /[{};=]|=>|\bfunction\b|\bdef\b|\bclass\b|\breturn\b|\bimport\b|\bconst\b|\bvar\b|\blet\b|^\s*[-+*]\s|\/\//;
    function looksLikeProse(v) {
      var t = String(v == null ? '' : v).trim();
      if (t.length < 20) return false;
      if (CODE_HINT.test(t)) return false;
      var first = t.split(/\n/)[0].trim();
      if (first.split(/\s+/).length < 4) return false;
      return /[.?:]\s|[.?:]$/.test(first) || /\.\s/.test(t);
    }
    function walk(node, inItem) {
      if (!node || typeof node !== 'object') return;
      if (node.type === 'code') {
        if (String(node.lang || '') === '' && looksLikeProse(node.value)) {
          add('warn', lineOf(node), 'looks like prose inside a plain ``` code fence — renders as a set-apart gray monospace box, not a paragraph (drop the fence, or move it to `description:`/lead text)');
        }
        if (!inItem) {
          add('warn', lineOf(node), 'fenced code/diff outside an :::item — tie every snippet to an item that names its file and symbol (orphan snippet)');
        }
      }
      var childInItem = inItem;
      if (node.type === 'containerDirective' || node.type === 'leafDirective' || node.type === 'textDirective') {
        var name = node.name || '';
        if (!KNOWN[name]) {
          add('warn', lineOf(node), 'unknown directive `:' + name + '` (known: card, item, input)');
        } else if (name === 'input') {
          lintInput(node);
        } else if (name === 'item') {
          var ia = node.attributes || {};
          if (ia.oneliner != null && String(ia.oneliner).length > 200) {
            add('warn', lineOf(node), ':::item oneliner exceeds 200 characters — keep the skimmable claim short and put depth inside the reveal body');
          }
          childInItem = true;
        } else if (name === 'card') {
          lintCard(node);
        }
      }
      if (node.children) node.children.forEach(function (c) { walk(c, childInItem); });
    }
    tree.children.forEach(function (n) { walk(n, false); });

    // ---- a directive marker that survived as PLAIN TEXT did not parse; the usual cause is
    // colon-nesting (a card that wraps items must use MORE colons than the items it wraps).
    var LEAK = /(^|\s):{2,}\s*(card|item|input)\b/;
    function scanLeak(node) {
      if (!node || typeof node !== 'object') return;
      if (node.type === 'text' && LEAK.test(node.value || '')) {
        add('warn', lineOf(node), 'a directive marker survived as plain text (it did not parse) — usual cause: colon-nesting (a card that wraps items must use MORE colons, e.g. ::::card around :::item)');
      }
      if (node.children) node.children.forEach(scanLeak);
    }
    tree.children.forEach(scanLeak);

    function rk(l) { return l === 'error' ? 0 : l === 'warn' ? 1 : l === 'info' ? 2 : 9; }
    findings.sort(function (a, b) {
      if (a.line !== b.line) return a.line - b.line;
      return rk(a.level) - rk(b.level);
    });
    return findings;
  }

  global.TressoirMd = { project: project, render: render, applyBehaviors: applyBehaviors, lint: lint };
})(typeof window !== 'undefined' ? window : this);
