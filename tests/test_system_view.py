#!/usr/bin/env python3
"""Tests for extras/tressoir-system-view/system_view.py. Each case builds its own git repository
in a temporary folder.

    python3 tests/test_system_view.py

Tally, the simple example, is rebuilt as a real repository: the state of the last commit comes
from tests/fixtures/system_view/tally/ (system.json as it was, and which files are new), the rest
from extras/tressoir-system-view/examples/tally/. The page the script builds must then carry the
marks listed in the fixture's expect.json, which were worked out separately.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(KIT, 'extras', 'tressoir-system-view', 'system_view.py')
EXAMPLES = os.path.join(KIT, 'extras', 'tressoir-system-view', 'examples')
FIXTURES = os.path.join(KIT, 'tests', 'fixtures', 'system_view')
PASS, FAIL = [], []


def check(name, ok, detail=''):
    (PASS if ok else FAIL).append(name)
    print(('PASS: ' if ok else 'FAIL: ') + name + ('' if ok or not detail else '\n      ' + str(detail)[:600]), file=sys.stdout if ok else sys.stderr)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)


def git(root, *args):
    subprocess.run(['git'] + list(args), cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run(root, *args):
    p = subprocess.run([sys.executable, SCRIPT] + list(args), cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode('utf-8'), p.stderr.decode('utf-8')


def page_data(root):
    return json.loads(re.search(r'^const S = (.*);$', read(os.path.join(root, 'WORK', 'SYSTEM_VIEW.html')), re.M).group(1))


def repository(tmp, example, commit=True):
    """A project as of its last commit, then the built changes of the example in the working tree."""
    root = os.path.join(tmp, example + ('' if commit else '-plain'))
    ex, fx = os.path.join(EXAMPLES, example), os.path.join(FIXTURES, example)
    words, new = json.loads(read(os.path.join(ex, 'lines.json'))), json.loads(read(os.path.join(fx, 'git.json')))
    entries = json.loads(read(os.path.join(ex, 'changes.json')))
    for p, w in words.items():
        if not p.endswith('/') and p not in new['added']:
            write(root, p, '# ' + w + '\n')
    write(root, 'WORK/SYSTEM_VIEW/system.json', read(os.path.join(fx, 'system.committed.json')))
    write(root, 'WORK/SYSTEM_VIEW/changes.json', '[]\n')
    write(root, 'WORK/SYSTEM_VIEW/lines.json', read(os.path.join(ex, 'lines.json')))
    if commit:
        git(root, 'init', '-q')
        git(root, 'config', 'user.email', 'tests@example.com')
        git(root, 'config', 'user.name', 'Tests')
        git(root, 'add', '-A')
        git(root, 'commit', '-q', '-m', 'the last commit')
    for e in entries:
        if not e.get('plan'):
            for p, n in e['files'].items():
                write(root, p, '# ' + words.get(p, '') + '\n# ' + n + '\n')
    write(root, 'WORK/SYSTEM_VIEW/changes.json', read(os.path.join(ex, 'changes.json')))
    return root


def compare(data, want):
    """Every mark the page data carries against the expected ones. Returns the differences."""
    out = []

    def eq(what, a, b):
        if a != b:
            out.append('%s: got %r, expected %r' % (what, a, b))

    plan = next((t['id'] for t in data['tabs'] if t['id'].startswith('plan')), None)
    cc, pl = data['snap']['cc'], data['snap'][plan]
    plain = lambda boxes: [{k: x for k, x in b.items() if k in ('name', 'folder', 'line', 'shared')} for b in boxes]
    name = lambda sig: re.match(r'[\w.]+', sig).group(0)
    eq('views', len(data['views']), len(want['views']))
    for dv, wv in zip(data['views'], want['views']):
        rows = lambda v: [(r['slot'], r['title'], r['dir'], r['line'], plain(r['boxes'])) for r in v['rows']]
        eq('rows of view %r' % wv['id'], rows(dv), rows(wv))
        eq('links', dv['links'], wv['links'])
        eq('separate', plain(dv.get('sep', [])), plain(wv.get('sep', [])))
        for r in wv['rows']:
            for b in r['boxes']:
                c, p = cc['boxes'].get(b['folder'], ''), pl['boxes'].get(b['folder'], '')
                eq('box, committed to current: ' + b['folder'], None if c is None else c if c in ('add', 'del') else '',
                   None if b.get('plan') == 'add' else b.get('cc', ''))
                eq('box, plan: ' + b['folder'], p if p in ('add', 'del') else '', b.get('plan', ''))
    eq('flows', data['flows'], want['flows'])
    eq('folders', data['dirs'], want['dirs'])
    eq('files', [f[0] for f in data['files']], [f[0] for f in want['files']])
    for (p, w), m in zip(data['files'], want['files']):
        eq('words of ' + p, w, m[1])
        eq('file, committed to current: ' + p, cc['files'].get(p, ''), None if m[3] == 'add' else m[2])
        eq('file, plan: ' + p, pl['files'].get(p, ''), m[3])

    def line(i, sig, s_cc, s_plan, was, default):
        c, p = cc['lines'].get(i, {}), pl['lines'].get(i, {})
        eq('line, committed to current: ' + i, None if c is None else c.get('s', ''), None if s_plan == 'add' else s_cc)
        eq('line, plan: ' + i, p.get('s', ''), s_plan)
        eq('signature in the plan: ' + i, p.get('sig') or default, sig)
        if s_plan == 'chg':
            eq('what it was, plan: ' + i, p.get('was'), was)
        elif s_cc == 'chg':
            eq('what it was: ' + i, c.get('was'), was)

    eq('boxes with functions', sorted(data.get('api', {})), sorted(want['api']))
    for folder, fns in want['api'].items():
        got = data['api'].get(folder, [])
        eq('functions of ' + folder, [name(f[0]) for f in got], [name(f[0]) for f in fns])
        for d, m in zip(got, fns):
            i = folder + '#' + name(m[0])
            line(i, m[0], m[2], m[3], m[4], d[0])
            eq('words of ' + i, pl['lines'].get(i, {}).get('line') or d[1], m[1])
    eq('types', sorted(data.get('types', {})), sorted(want['types']))
    for t, m in want['types'].items():
        d = data['types'].get(t, ['', '', ''])
        line(t, m[0], m[3], m[4], m[5], d[0])
        eq('owner of ' + t, d[2], m[2])
    eq('named changes', [(c['name'], c['line'], c['files']) for c in data['changes']],
       [(c['name'], c['line'], c['files']) for c in want['changes']])
    for k, c in enumerate(want['changes']):
        tab = pl if c.get('plan') else cc
        eq('tab of ' + c['name'], k in tab['changes'], True)
        eq('lines marked by ' + c['name'], sorted(tab['hits'].get(str(k), [])), sorted(want['hits'][c['name']]))
    return out


def tally(tmp):
    root = repository(tmp, 'tally')
    code, out, err = run(root, '--check')
    check('tally: --check finds no error', code == 0 and 'ERROR' not in out, out + err)
    check('tally: --check writes nothing', not os.path.exists(os.path.join(root, 'WORK', 'SYSTEM_VIEW.html'))
          and read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json')) == read(os.path.join(FIXTURES, 'tally', 'system.committed.json')))
    code, out, err = run(root)
    check('tally: the page is built', code == 0 and os.path.exists(os.path.join(root, 'WORK', 'SYSTEM_VIEW.html')), out + err)
    check('tally: the built changes are folded into system.json',
          read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json')) == read(os.path.join(EXAMPLES, 'tally', 'system.json')))
    check('tally: the replaced line is said', 'It was: add(entry: NewEntry) → EntryId  // records one entry.' in out, out)
    data = page_data(root)
    check('tally: tabs are Committed, Current, Committed → Current, Current → Plan',
          [t['label'] for t in data['tabs']] == ['Committed', 'Current', 'Committed → Current', 'Current → Plan'], data['tabs'])
    diffs = compare(data, json.loads(read(os.path.join(FIXTURES, 'tally', 'expect.json'))))
    check('tally: every mark on the page is the expected one', not diffs, '\n      '.join(diffs[:8]))
    cc = data['snap']['cc']['files']
    count = lambda s: sum(1 for v in cc.values() if v == s)
    check('tally: Committed → Current counts +1 ~4 −0', (count('add'), count('chg'), count('del')) == (1, 4, 0), cc)
    before = read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json'))
    code, out, err = run(root)
    check('tally: a second run changes nothing in system.json', code == 0 and 'Folded' not in out
          and read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json')) == before, out + err)
    check('tally: nothing of WORK/ is in the file view', not any(f[0].startswith('WORK/') for f in data['files']))

    # an unreadable file: where, and what is wrong, in plain words
    good = read(os.path.join(root, 'WORK/SYSTEM_VIEW/changes.json'))
    write(root, 'WORK/SYSTEM_VIEW/changes.json', good.replace('"affects": ["main"],', '"affects": ["main"],,', 1))
    code, out, err = run(root)
    check('an unreadable changes.json stops with its line and column',
          code == 2 and re.search(r'WORK/SYSTEM_VIEW/changes\.json cannot be read\. Line \d+, column \d+: ', err), err)
    # a name in affects that no box around the entry's files lists
    write(root, 'WORK/SYSTEM_VIEW/changes.json', good.replace('"affects": ["categorize"]', '"affects": ["categorise"]'))
    code, out, err = run(root, '--check')
    check('a name in affects found nowhere is an error', code == 1 and 'ERROR' in out and 'categorise' in out and 'categorize' in out, out + err)
    write(root, 'WORK/SYSTEM_VIEW/changes.json', good)

    # Seen: hidden while it is the last commit, shown once commits lie between
    code, out, err = run(root, '--seen')
    check('--seen records the last commit', code == 0 and len(read(os.path.join(root, 'WORK/SYSTEM_VIEW/seen')).strip()) == 40, out + err)
    run(root)
    check('Seen has no tab while nothing lies between', 'seen' not in [t['id'] for t in page_data(root)['tabs']])
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'a milestone')
    write(root, 'src/core/budgets/budgets.py', '# limits and what is left\n# rounds to the cent\n')
    code, out, err = run(root)
    data = page_data(root)
    check('Seen has a tab once a commit lies between', [t['label'] for t in data['tabs']][:4] == ['Committed', 'Current', 'Committed → Current', 'Seen → Current'], data['tabs'])
    seen, cc = data['snap'].get('seen', {}), data['snap']['cc']
    check('Seen → Current still shows what the milestone committed',
          seen.get('files', {}).get('src/core/entries/dedupe.py') == 'add' and (seen.get('lines', {}).get('src/core/entries/#add') or {}).get('s') == 'chg'
          and 'Duplicates skipped on import' in [data['changes'][i]['name'] for i in seen.get('changes', [])], seen)
    check('Committed → Current shows only what came after the milestone',
          cc['files'].get('src/core/budgets/budgets.py') == 'chg' and cc['files'].get('src/core/entries/dedupe.py', '') == ''
          and 'src/core/entries/#add' not in cc['lines'], cc)


def no_repository(tmp):
    root = repository(tmp, 'tally', commit=False)
    code, out, err = run(root)
    data = page_data(root) if code == 0 else {'tabs': [], 'built': []}
    check('without a repository only the current state and the plan are shown',
          [t['id'] for t in data['tabs']] == ['current', 'plan:0'] and any('not a git repository' in t for t in data['built']), out + err)


def main():
    tmp = tempfile.mkdtemp(prefix='tressoir-system-view-tests.')
    try:
        tally(tmp)
        no_repository(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\nResult: %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
