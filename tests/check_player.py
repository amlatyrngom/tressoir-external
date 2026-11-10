#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Check a built briefing in headless Chrome, opened from disk.

    uv run tests/check_player.py <built>.html

Plays it at a phone size and at the Claude app's Mac preview size, once on each audio route (audio
element with a data address, audio element with a blob address, Web Audio) and once with no audio
at all, which must fall back to text. Uses the Chrome already installed; downloads no browser.
"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

SIZES = {'phone': (360, 537), 'mac preview': (712, 884)}
# Scripts run before the page's own, to close off the earlier audio routes.
BLOCK_DATA = """const A = window.Audio; window.triedAddresses = []; window.Audio = function () { const el = new A();
  Object.defineProperty(el, 'src', { set(v) { window.triedAddresses.push(String(v).slice(0, 5));
                                              if (String(v).startsWith('data:')) setTimeout(() => el.onerror && el.onerror(), 0); else el.setAttribute('src', v); },
                                     get() { return el.getAttribute('src'); } }); return el; };"""
BLOCK_ELEMENT = "window.Audio = function () { throw new Error('blocked for the test'); };"
BLOCK_ALL = BLOCK_ELEMENT + " window.AudioContext = window.webkitAudioContext = undefined;"
ROUTES = [('audio element, data address', None, 'audio element'), ('audio element, blob address', BLOCK_DATA, 'audio element'),
          ('Web Audio', BLOCK_ELEMENT, 'Web Audio'), ('no audio, text only', BLOCK_ALL, 'none available, text only')]


def check(page, name, expect, decisions, slides, problems):
    def bad(what): problems.append(f'{name}: {what}')
    inside = lambda sel: page.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
        return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth && r.width > 0; }""", sel)
    if page.locator('.pills button').count() != slides: bad('wrong number of progress segments')
    if page.locator('.pills button[data-ask]').count() != decisions: bad('wrong number of decision ticks')
    text_only = expect.startswith('none')
    if text_only:
        page.keyboard.press('Space'); page.wait_for_timeout(600)
        if 'none available' not in page.inner_text('#diag'): bad('did not report the text-only fallback: ' + page.inner_text('#diag'))
        if page.is_hidden('.notes') or page.is_hidden('.note'): bad('text or the no-audio note is not shown')
        if page.is_visible('.play'): bad('play button still shown without audio')
    else:
        page.click('.play'); page.wait_for_timeout(2500)
        said = page.inner_text('#diag')
        if f'Audio: {expect}.' not in said: bad(f'expected route "{expect}", page says: {said}')
        if 'blob address' in name and page.evaluate('window.triedAddresses') != ['data:', 'blob:']: bad('the blob address was not the route used')
        width = page.evaluate("parseFloat(document.querySelector('.pills .cur i').style.width) || 0")
        if width <= 0: bad('playback did not advance')
        page.click('.speed')
        if page.inner_text('.speed') != '1.25×': bad('speed did not change')
        page.wait_for_timeout(700)
        page.click('.next'); page.wait_for_timeout(900)
        if page.inner_text('.count') != f'2 / {slides}': bad('next did not move to slide 2 while playing')
        if page.evaluate("parseFloat(document.querySelector('.pills .cur i').style.width) || 0") <= 0: bad('playback did not continue on slide 2')
        page.click('.play'); page.wait_for_timeout(200)       # pause
        page.click('.textbtn')
        if page.is_hidden('.notes'): bad('Text did not show the narration')
    page.click('.theme')
    if page.evaluate('document.documentElement.dataset.theme') not in ('light', 'dark'): bad('theme button did nothing')
    page.click('.pills button:first-child'); page.wait_for_timeout(100)
    for k in range(slides):
        if page.inner_text('.count') != f'{k + 1} / {slides}': bad(f'arrow keys lost count at slide {k + 1}')
        if not inside('.next') or not inside('.stage'): bad(f'slide or controls outside the viewer on slide {k + 1}')
        if not text_only and not inside('.play'): bad(f'play button outside the viewer on slide {k + 1}')
        if page.evaluate("document.querySelector('.stage .slide').scrollHeight") > 541: bad(f'slide {k + 1} overflows its frame')
        page.keyboard.press('ArrowRight'); page.wait_for_timeout(60)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)'); page.wait_for_timeout(100)
    if not inside('.next'): bad('controls scroll out of view with the text open')


def main():
    built = Path(sys.argv[1]).resolve()
    source = built.read_text(encoding='utf-8')
    slides = json.loads(source.split('SLIDES = ', 1)[1].split(', CUES = ', 1)[0])
    decisions = sum(1 for s in slides if s.get('decision'))
    problems, runs = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', args=['--autoplay-policy=no-user-gesture-required'])
        for size, (w, h) in SIZES.items():
            for route, block, expect in ROUTES:
                context = browser.new_context(viewport={'width': w, 'height': h})
                if block: context.add_init_script(block)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(built.as_uri() + '#debug')
                check(page, f'{size}, {route}', expect, decisions, len(slides), problems)
                problems += [f'{size}, {route}: page error: {e}' for e in errors]
                context.close(); runs += 1
        browser.close()
    for line in problems: print('FAIL', line)
    print(f'{runs} runs ({len(SIZES)} sizes x {len(ROUTES)} audio routes), {len(slides)} slides, {len(problems)} problems')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
