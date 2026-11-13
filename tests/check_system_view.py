#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Check built system view pages in headless Chrome, opened from disk.

    uv run tests/check_system_view.py                  # builds the Tally, Marlin and Pocket examples, then checks them
    uv run tests/check_system_view.py <page>.html ...  # checks pages that are already built

At 375, 705, 900 and 1440 pixels wide it goes through every tab, every view, every box (closed and
with every line opened) and every flow step, and expects: no console error; no text of the figure
on a box or on other text; no name larger than its box; no two regions picked by the same name; at 375 pixels, nothing wider than
the screen. It then draws the page
inside a hidden frame, shows the frame, and expects the same figure as in a frame that was never
hidden. Uses the Chrome already installed; downloads no browser.
"""
import shutil, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_system_view as kit

WIDTHS = [375, 705, 900, 1440]

# Walks the page with its own functions and returns what is wrong. Runs in the page.
SWEEP = """(narrow) => { const bad = [], strip = document.getElementById('strip'); let states = 0;
  const R = e => e.getBoundingClientRect(), hit = (a, b) => a.left < b.right - .5 && a.right > b.left + .5 && a.top < b.bottom - .5 && a.bottom > b.top + .5;
  const overlaps = where => document.querySelectorAll('.stage').forEach(st => {
    const boxes = [...st.querySelectorAll('.nd')].map(e => [e.textContent, R(e)]);
    const texts = [...st.querySelectorAll('.ed text')].filter(e => e.style.display !== 'none').map(e => [e.textContent, R(e)])
      .concat([...st.querySelectorAll('.rg b')].map(e => [e.textContent, R(e)]));
    st.querySelectorAll('.nd').forEach(e => { const s = e.querySelector('span'); if (!s) return; const a = R(s), b = R(e);
      if (a.left < b.left - 1 || a.right > b.right + 1 || a.top < b.top - 1 || a.bottom > b.bottom + 1) bad.push(where + ': the name "' + e.textContent + '" does not fit in its box'); });
    const picks = [...st.querySelectorAll('.rg')].map(e => e.dataset.pick);
    if (new Set(picks).size !== picks.length) bad.push(where + ': two regions are picked by the same name (' + picks.join(', ') + ')');
    texts.forEach(([t, r]) => boxes.forEach(([n, b]) => { if (hit(r, b)) bad.push(where + ': "' + t + '" is on the box ' + n); }));
    texts.forEach(([t, r], i) => texts.slice(i + 1).forEach(([u, q]) => { if (hit(r, q)) bad.push(where + ': "' + t + '" is on "' + u + '"'); })); });
  const wide = where => { states++; if (narrow && document.documentElement.scrollWidth > innerWidth + 1) bad.push(where + ': the page is ' + document.documentElement.scrollWidth + ' pixels wide'); };
  let where = '';
  try {
    for (const t of TABS) { mode = t.id;
      for (const v of S.views) { go(v.id); where = t.label + ', ' + (v.name || v.id); overlaps(where);
        for (const p of [null, ...own(v).map(b => 'node:' + b.folder)]) { pin = p; openT = []; show(); wide(where + ', ' + p);
          openT = [...strip.querySelectorAll('[data-fold]')].map(e => e.dataset.fold); show(); wide(where + ', ' + p + ', opened'); }
        for (const r of regionsOf(v)) { pin = 'region:' + r.id; openT = []; show(); wide(where + ', region ' + r.id); } }
      for (let f = 0; f < S.flows.length; f++) { goFlow(f); where = t.label + ', flow ' + S.flows[f].name; pin = null; show(); wide(where);
        for (let k = 0; k < S.flows[f].steps.length; k++) { pin = 'step:' + k; show(); wide(where + ', step ' + (k + 1)); } }
      go(''); only = !only; render(); wide(t.label + ', the other setting of Changes only'); only = !only; render(); }
  } catch (e) { bad.push(where + ': ' + e); }
  return { bad, states }; }"""

# Where everything of the figure sits, to compare two drawings.
SHAPE = """() => [...document.querySelectorAll('.stage')].map(st => { const o = st.getBoundingClientRect();
  return [...st.querySelectorAll('.nd, .lab, .rg b, .ed text')].filter(e => e.style.display !== 'none').map(e => { const r = e.getBoundingClientRect();
    return [e.textContent, Math.round(r.left - o.left), Math.round(r.top - o.top), Math.round(r.width), Math.round(r.height)].join('|'); }); })"""


def build(tmp):
    pages = []
    for example in ('tally', 'marlin'):
        root = kit.repository(tmp, example)
        code, out, err = kit.run(root)
        if code != 0:
            sys.exit('could not build the %s example:\n%s%s' % (example, out, err))
        page = Path(tmp) / (example + '.html')
        shutil.copy(Path(root) / 'WORK' / 'SYSTEM_VIEW.html', page)
        pages.append(page)
    root, _first = kit.pocket_repository(tmp)
    code, out, err = kit.run(root)
    if code != 0:
        sys.exit('could not build the pocket example:\n%s%s' % (out, err))
    shutil.copy(Path(root) / 'WORK' / 'SYSTEM_VIEW.html', Path(tmp) / 'pocket.html')
    return pages + [Path(tmp) / 'pocket.html']


def main():
    tmp = tempfile.mkdtemp(prefix='tressoir-system-view-pages.')
    pages = [Path(a).resolve() for a in sys.argv[1:]] or build(tmp)
    problems, states = [], 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome')
            for built in pages:
                for width in WIDTHS:
                    page = browser.new_page(viewport={'width': width, 'height': 900})
                    said = []
                    page.on('console', lambda m: said.append(m.text) if m.type == 'error' else None)
                    page.on('pageerror', lambda e: said.append(str(e)))
                    page.goto(built.as_uri())
                    page.wait_for_timeout(150)
                    result = page.evaluate(SWEEP, width == 375)
                    states += result['states']
                    for what in result['bad'][:12] + said[:6]:
                        problems.append('%s at %d: %s' % (built.name, width, what))
                    page.close()
                # drawn while hidden, then shown: the same figure as one that was never hidden
                frames = Path(tmp) / (built.stem + '.frames.html')
                frames.write_text('<!doctype html><body style="margin:0"><iframe id="a" src="%s" style="width:900px;height:900px;border:0"></iframe>'
                                  '<iframe id="b" src="%s" style="width:900px;height:900px;border:0;display:none"></iframe>' % (built.as_uri(), built.as_uri()),
                                  encoding='utf-8')
                page = browser.new_page(viewport={'width': 900, 'height': 1900})
                page.goto(frames.as_uri())
                page.wait_for_timeout(400)
                page.evaluate("document.getElementById('b').style.display = ''")
                page.wait_for_timeout(900)
                seen, hidden = [f.evaluate(SHAPE) for f in page.frames[1:3]]
                if (not seen or not seen[0]) and not page.frames[1].evaluate('!!S.none'):
                    problems.append('%s: the figure could not be read inside a frame' % built.name)
                elif seen != hidden and seen and seen[0]:
                    problems.append('%s: a figure drawn while hidden differs once shown (%d of %d pieces differ)' % (
                        built.name, sum(1 for a, b in zip(seen[0], (hidden or [[]])[0]) if a != b) + abs(len(seen[0]) - len((hidden or [[]])[0])), len(seen[0])))
                page.close()
            browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for line in problems:
        print('FAIL: ' + line, file=sys.stderr)
    print('%d pages, %d widths, %d states checked: %s' % (len(pages), len(WIDTHS), states, 'all good' if not problems else '%d problems' % len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
