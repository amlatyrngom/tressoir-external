#!/usr/bin/env python3
"""Tests for extras/tressoir-system-view/system_view.py. Each case builds its own git repository
in a temporary folder.

    python3 tests/test_system_view.py

Tally, the simple example, and Marlin, the one with views inside boxes, are rebuilt as real
repositories: the state of the last commit comes from tests/fixtures/system_view/<example>/
(system.json as it was, and which files are new, changed or not there yet), the rest from
extras/tressoir-system-view/examples/<example>/. The page the script builds must then carry the
marks listed in the fixture's expect.json, which were worked out separately.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

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
        if not p.endswith('/') and p not in new['added'] and p not in new.get('later', []):
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
    touched = new.get('changed') or [p for e in entries if not e.get('plan') for p in e['files']]
    for p in list(new['added']) + list(touched):
        write(root, p, '# ' + words.get(p, '') + '\n# changed\n')
    for p in new.get('removed') or []:
        os.remove(os.path.join(root, p))
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


def compare_marks(data, want):
    """The same comparison for a fixture that lists marks by id: files, boxes, lines, and the lines each change marks."""
    out = []

    def eq(what, a, b):
        if a != b:
            out.append('%s: got %r, expected %r' % (what, a, b))

    plan = next((t['id'] for t in data['tabs'] if t['id'].startswith('plan')), None)
    cc, pl = data['snap']['cc'], data['snap'][plan]
    files = [f for f in want['files'] if not f[0].endswith('/')]
    eq('files', sorted(f[0] for f in data['files']), sorted(f[0] for f in files))
    for p, c, q in files:
        eq('file, committed to current: ' + p, cc['files'].get(p, ''), None if q == 'add' else c)
        eq('file, plan: ' + p, pl['files'].get(p, ''), q)
    boxes = [b['folder'] for v in data['views']
             for b in [x for r in v['rows'] for x in r['boxes']] + (v.get('band') or {}).get('boxes', []) + v.get('sep', [])]
    eq('boxes', sorted(boxes), sorted(b[0] for b in want['boxes']))
    for f, c, q in want['boxes']:
        x, y = cc['boxes'].get(f, ''), pl['boxes'].get(f, '')
        eq('box, committed to current: ' + f, None if x is None else x if x in ('add', 'del') else '', None if q == 'add' else c)
        eq('box, plan: ' + f, y if y in ('add', 'del') else '', q)
    default = {}
    for folder, fns in data['api'].items():
        for sig, _words in fns:
            default[folder + '#' + re.match(r'[\w.]+', sig).group(0)] = sig
    for t, v in data['types'].items():
        default[t] = v[0]
    eq('lines', sorted(default), sorted(a['id'] for a in want['api'] + want['types']))
    for a in want['api'] + want['types']:
        i = a['id']
        c, p = cc['lines'].get(i, {}), pl['lines'].get(i, {})
        eq('line, committed to current: ' + i, None if c is None else c.get('s', ''), None if a['plan'] == 'add' else a['cc'])
        eq('line, plan: ' + i, None if p is None else p.get('s', ''), a['plan'])
        eq('signature in the plan: ' + i, (p or {}).get('sig') or default.get(i), a['sig'])
        if a['plan'] == 'chg':
            eq('what it was, plan: ' + i, p.get('was'), a['was'])
        elif a['cc'] == 'chg':
            eq('what it was: ' + i, c.get('was'), a['was'])
    names = [c['name'] for c in data['changes']]
    eq('named changes', names, list(want['plans']))
    for name, ids in want['hits'].items():
        if name not in names:
            continue
        k = names.index(name)
        tab = pl if want['plans'][name] else cc
        eq('tab of ' + name, k in tab['changes'], True)
        eq('lines marked by ' + name, sorted(tab['hits'].get(str(k), [])), sorted(ids))
    return out


def unordered(v):
    """system.json with the order of boxes in a row and of lines in a box left out: a folded box or line is added last."""
    if isinstance(v, list):
        return [unordered(x) for x in v]
    if not isinstance(v, dict):
        return v
    out = {k: unordered(x) for k, x in v.items()}
    if isinstance(out.get('interface'), list):
        out['interface'] = sorted(out['interface'])
    if isinstance(out.get('boxes'), list):
        out['boxes'] = sorted(out['boxes'], key=lambda b: b.get('folder', '') if isinstance(b, dict) else str(b))
    return out


def marlin(tmp):
    root = repository(tmp, 'marlin')
    code, out, err = run(root)
    check('marlin: the page is built with no error', code == 0 and 'ERROR' not in out, out + err)
    got = json.loads(read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json')))
    want = json.loads(read(os.path.join(EXAMPLES, 'marlin', 'system.json')))
    check('marlin: the built changes are folded into system.json', unordered(got) == unordered(want))
    check('marlin: a box that came with a change is added last in its row',
          [b['folder'] for b in got['regions']['external']['boxes']][-1] == 'src/connectors/object-store/', got['regions']['external'])
    data = page_data(root)
    check('marlin: one view per box that has boxes inside, after the overview',
          [v['id'] for v in data['views']] == ['', 'src/core/optimizer/', 'src/core/execution/', 'src/core/transactions/', 'src/core/storage/'],
          [v['id'] for v in data['views']])
    check('marlin: tabs are Committed, Current, Committed → Current, Current → Plan',
          [t['label'] for t in data['tabs']] == ['Committed', 'Current', 'Committed → Current', 'Current → Plan'], data['tabs'])
    diffs = compare_marks(data, json.loads(read(os.path.join(FIXTURES, 'marlin', 'expect.json'))))
    check('marlin: every mark on the page is the expected one', not diffs, '\n      '.join(diffs[:8]))
    cc = data['snap']['cc']['files']
    count = lambda s: sum(1 for v in cc.values() if v == s)
    check('marlin: Committed → Current counts +6 ~15 −0', (count('add'), count('chg'), count('del')) == (6, 15, 0), (count('add'), count('chg'), count('del')))
    check('marlin: flows are carried as written', [f['name'] for f in data['flows']] == [f['name'] for f in want.get('flows', [])] and data['flows'])
    before = read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json'))
    code, out, err = run(root)
    check('marlin: a second run changes nothing in system.json', code == 0 and 'Folded' not in out
          and read(os.path.join(root, 'WORK/SYSTEM_VIEW/system.json')) == before, out + err)


# ---------------------------------------------------------------- a small project with real code, for the checks

MINI = {
    'name': 'Mini',
    'regions': {
        'entry': {'folder': 'src/entry/', 'line': 'how it is used', 'boxes': [
            {'name': 'Command line', 'folder': 'src/entry/cli/', 'line': 'the commands',
             'interface': ['main(argv: [Text])  // runs one command']}]},
        'core': {'folder': 'src/core/', 'line': 'what it does', 'boxes': [
            {'name': 'Entries', 'folder': 'src/core/entries/', 'line': 'records entries',
             'interface': ['add(entry: NewEntry) → EntryId  // records one entry', 'listing() → [Entry]  // every entry',
                           'NewEntry = { text: Text }  // an entry not yet recorded']},
            {'name': 'Reports', 'folder': 'src/core/reports/', 'line': 'totals',
             'interface': ['monthly(month: Month) → Report  // one month']}]}},
    'links': [{'from': 'src/entry/', 'to': 'src/core/', 'label': 'commands', 'says': 'The command line calls the core.'}],
    'flows': [{'name': 'Adding an entry', 'line': 'from the command to the record', 'steps': [
        {'at': 'src/entry/cli/', 'does': 'reads the command', 'calls': 'main'},
        {'at': 'src/core/entries/', 'gets': 'the entry', 'does': 'records it', 'calls': 'add'}]}]}
MINI_FILES = {
    'src/entry/cli/main.py': 'def main(argv):\n    return add(argv)\n',
    'src/core/entries/entries.py': 'class NewEntry:\n    pass\n\n\ndef add(entry):\n    return _store(entry)\n\n\n'
                                   'def _store(entry):\n    return _key(entry)\n\n\ndef _key(entry):\n    return 1\n\n\n'
                                   'def listing():\n    return []\n',
    'src/core/reports/monthly.py': 'def monthly(month):\n    return total(month)\n\n\ndef total(month):\n    return 0\n',
    'docs/readme.md': 'How to use it.\n',
}
ENTRIES_PY, MONTHLY_PY = 'src/core/entries/entries.py', 'src/core/reports/monthly.py'
SV = 'WORK/SYSTEM_VIEW/'


def mini(tmp, name='mini'):
    root = os.path.join(tmp, name)
    for path, text in MINI_FILES.items():
        write(root, path, text)
    write(root, SV + 'system.json', json.dumps(MINI, ensure_ascii=False))
    write(root, SV + 'changes.json', '[]\n')
    write(root, SV + 'lines.json', '{}\n')
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'tests@example.com')
    git(root, 'config', 'user.name', 'Tests')
    run(root)                                   # the script gives system.json its format
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'the base')
    git(root, 'tag', 'base')
    return root


def back(root):
    git(root, 'reset', '-q', '--hard', 'base')
    git(root, 'clean', '-q', '-fd')


def entries(root, *es):
    write(root, SV + 'changes.json', json.dumps(list(es), ensure_ascii=False))


def edit(root, path, old, new):
    text = read(os.path.join(root, path))
    assert old in text, (path, old)
    write(root, path, text.replace(old, new))


def system(root):
    return json.loads(read(os.path.join(root, SV + 'system.json')))


def lines_of(root, folder):
    for region in system(root)['regions'].values():
        for b in (region or {}).get('boxes', []):
            if b['folder'] == folder:
                return b.get('interface', [])
    return None


def checks(tmp):
    root = mini(tmp)
    code, out, err = run(root)
    check('mini: a clean project has no error and no note', code == 0 and 'ERROR' not in out and 'note' not in out, out + err)
    ent, rep = 'src/core/entries/', 'src/core/reports/'
    keys = {'name': 'Keys are stable', 'line': 'a key no longer depends on the clock',
            'files': {ENTRIES_PY: 'the key is the same on every run'}, 'affects': ['add']}

    # ---- errors
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, 'docs/readme.md', 'use it', 'use it well')
    code, out, err = run(root)
    check('a changed file under the figure that no entry explains is an error',
          code == 1 and 'ERROR  1 changed file under the figure is in no entry: ' + ENTRIES_PY in out, out + err)
    check('an entry is prepared for it, with every unexplained file and what the code shows',
          'Prepared for the changed files no entry explains' in out and '"docs/readme.md": "?"' in out
          and ENTRIES_PY + ': changed in _key. Its box src/core/entries/ lists add, listing.' in out, out)
    check('the prepared entry proposes the nearest listed function, found through the callers', '"affects": ["add"]' in out, out)
    entries(root, dict(keys, files=dict(keys['files'], **{'docs/readme.md': 'says so'})))
    code, out, err = run(root)
    check('with an entry for them the error is gone', code == 0 and 'ERROR' not in out, out + err)
    entries(root, dict(keys, files=dict(keys['files'], **{'docs/readme.md': 'says so'}), affects=[]))
    code, out, err = run(root)
    check('affects that differs from what the code shows is only said',
          code == 0 and 'Keys are stable: "affects" has nothing. Following its changed lines to the nearest listed functions gives add.' in out, out + err)

    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 1')
    count = dict(keys, interface={ent: ['count() → Int  // how many entries']})
    years = {'name': 'Totals by year', 'line': 'a year at a time', 'files': {MONTHLY_PY: 'adds up the months'}, 'affects': ['yearly']}
    entries(root, count, years)
    code, out, err = run(root)
    check('an entry that fails a check is not folded, and says which', code == 1 and 'Totals by year: "affects" names yearly' in out
          and 'Nothing was folded from: Totals by year.' in out, out + err)
    check('the entries that pass are folded all the same', 'count() → Int  // how many entries' in lines_of(root, ent), lines_of(root, ent))
    check('the page is still written, and lists both changes',
          [c['name'] for c in page_data(root)['changes']] == ['Keys are stable', 'Totals by year'])
    check('a flow that passes a box an entry changes is said',
          'note   The flow "Adding an entry" passes src/core/entries/, which "Keys are stable" changes.' in out, out)
    check('a listed name found nowhere in its box is said', 'note   Listed in src/core/entries/ and found nowhere in its files: count.' in out, out)

    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 1')
    both = {'name': 'Exports', 'line': 'both can export', 'files': {ENTRIES_PY: 'exports', MONTHLY_PY: 'exports'},
            'interface': {ent: ['export() → Text  // every entry as text'], rep: ['export() → Text  // the totals as text']}}
    entries(root, dict(both, affects=['export']))
    code, out, err = run(root, '--check')
    check('a name in affects that two boxes list is an error that asks for the box', code == 1 and 'Write it as "<box folder>: export"' in out, out + err)
    entries(root, dict(both, affects=['src/core/reports/: export']))
    code, out, err = run(root, '--check')
    check('written with its box, the name is found', code == 0 and 'ERROR' not in out, out + err)

    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    entries(root, dict(keys, files={ENTRIES_PY: 'the key is the same on every run', MONTHLY_PY: 'uses the key'}))
    code, out, err = run(root, '--check')
    check('a file of a built entry that does not differ while the others do is an error',
          code == 1 and 'Keys are stable: %s does not differ from the last commit' % MONTHLY_PY in out, out + err)
    entries(root, dict(keys, files={ENTRIES_PY: 'the key is the same on every run', 'src/core/entries/keys.py': '+ makes keys'}))
    code, out, err = run(root, '--check')
    check('a built entry with a "+ " file that does not exist is an error',
          code == 1 and 'src/core/entries/keys.py is written as a new file ("+ ") and does not exist' in out, out + err)

    back(root)
    entries(root, {'name': 'Totals by year', 'line': 'a year at a time', 'plan': 'Years', 'files': {'src/core/reports/yearly.py': 'adds up the months'}})
    code, out, err = run(root, '--check')
    check('a planned path that does not exist and has no "+ " is an error that names its neighbours',
          code == 1 and 'src/core/reports/yearly.py does not exist and its note has no "+ ". Nearest: ' + MONTHLY_PY in out, out + err)

    back(root)
    good = system(root)
    for what, change, said in [
            ('a name twice in a box', lambda b: b[1]['interface'].append('add(entry: NewEntry)  // again'), 'add is written twice: in src/core/entries/'),
            ('a path in two boxes', lambda b: b[2].update(also=['src/core/entries/']), 'The path src/core/entries/ is given to two boxes'),
            ('a bare name with no function inside', lambda b: b[1]['interface'].append('ghost'), 'ghost in src/core/entries/ is a bare name')]:
        bad = json.loads(json.dumps(good))
        change(bad['regions']['entry']['boxes'] + bad['regions']['core']['boxes'])
        write(root, SV + 'system.json', json.dumps(bad, ensure_ascii=False))
        code, out, err = run(root, '--check')
        check('%s is an error' % what, code == 1 and 'ERROR  ' + said in out, out + err)
    bad = json.loads(json.dumps(good))
    del bad['regions']['core']['boxes'][0]['folder']
    write(root, SV + 'system.json', json.dumps(bad, ensure_ascii=False))
    code, out, err = run(root)
    check('a box with no folder stops the script', code == 2 and 'a box in the region "core" has no "folder" (Entries)' in err, out + err)

    # ---- notes
    bad = json.loads(json.dumps(good))
    bad['links'].append({'from': 'src/entry/', 'to': 'src/nowhere/', 'says': 'nothing'})
    bad['flows'][0]['steps'] += [{'at': 'src/core/nowhere/', 'does': 'nothing'}, {'at': rep, 'does': 'totals a year', 'calls': 'yearly'}]
    bad['regions']['core']['boxes'][1]['uses'] = {'boxes': ['src/gone/'], 'says': 'nothing'}
    write(root, SV + 'system.json', json.dumps(bad, ensure_ascii=False))
    write(root, 'src/core/loose.py', 'x = 1\n')
    code, out, err = run(root)
    check('a link, a neighbour or a flow step that points at nothing is said, and the page is built',
          'A link of the overview points at src/nowhere/' in out and 'step 3, is at src/core/nowhere/, which is not a box' in out
          and 'step 4, calls yearly, which src/core/reports/ does not list. The page draws the step without its call.' in out
          and 'src/core/reports/: "uses" names src/gone/' in out and os.path.exists(os.path.join(root, 'WORK/SYSTEM_VIEW.html')), out + err)
    check('a file under a region that belongs to no box is said', 'note   1 file under src/core/ belongs to no box: src/core/loose.py.' in out, out)

    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    force = 'add(entry: NewEntry, force: Bool) → EntryId?  // records one entry'
    entries(root, dict(keys, interface={ent: ['add(entry: NewEntry) → EntryId?  // records one entry']}, affects=[]),
            {'name': 'Forced adds', 'line': 'an entry can be recorded twice on purpose', 'plan': 'Force',
             'files': {MONTHLY_PY: '+ counts the forced ones'}, 'interface': {ent: [force]}})
    code, out, err = run(root)
    check('a planned entry whose "+ " file exists is said to look built', code == 0 and 'Forced adds, of the plan Force, looks built: ' + MONTHLY_PY in out, out + err)
    check('an open plan that restates a line changed since the last commit is said',
          'Forced adds, of the plan Force, restates add, which has changed since the last commit.' in out, out)
    plan = page_data(root)['snap']['plan:0']['lines']['src/core/entries/#add']
    check('the plan tab starts from the line as it is now', plan.get('s') == 'chg' and plan.get('was') == 'add(entry: NewEntry) → EntryId?', plan)

    # ---- a line stated by two built entries
    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 1')
    first = dict(keys, affects=[], interface={ent: ['add(entry: NewEntry) → EntryId?  // records one entry', 'count() → Int  // how many']})
    second = {'name': 'Forced adds', 'line': 'on purpose', 'files': {MONTHLY_PY: 'counts the forced ones'}, 'interface': {ent: [force]}}
    entries(root, first, second)
    code, out, err = run(root)
    now = json.loads(read(os.path.join(root, SV + 'changes.json')))
    check('when two built entries state a line the later one stands, and it is said',
          code == 0 and '"Keys are stable" and "Forced adds" both state add in src/core/entries/' in out and force in lines_of(root, ent), out + err)
    check('the line leaves the earlier entry, and its name goes under affects',
          now[0].get('interface') == {ent: ['count() → Int  // how many']} and now[0].get('affects') == ['add'] and now[1]['interface'] == {ent: [force]}, now)

    # ---- dropping
    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    write(root, 'src/core/entries/dedupe.py', 'def same(a, b):\n    return a == b\n')
    entries(root, dict(keys, files={ENTRIES_PY: 'the key is the same on every run', 'src/core/entries/dedupe.py': 'recognises an entry already recorded'},
                       interface={ent: ['add(entry: NewEntry) → EntryId?  // records one entry']}))
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'committed without running the script')
    code, out, err = run(root)
    data = page_data(root)
    check('an entry stays while a line it states is not in system.json at the last commit',
          code == 0 and 'Took' not in out and [c['name'] for c in data['changes']] == ['Keys are stable']
          and (data['snap']['cc']['lines'].get('src/core/entries/#add') or {}).get('s') == 'chg', out + err)
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', 'the fold')
    code, out, err = run(root)
    data = page_data(root)
    check('a built entry is taken out once the last commit holds it', code == 0 and 'Took 1 built entry out of WORK/SYSTEM_VIEW/changes.json' in out
          and json.loads(read(os.path.join(root, SV + 'changes.json'))) == [] and data['snap']['cc']['changes'] == [], out + err)
    check('the note of its new file becomes the file\'s line',
          json.loads(read(os.path.join(root, SV + 'lines.json'))).get('src/core/entries/dedupe.py') == 'recognises an entry already recorded'
          and ['src/core/entries/dedupe.py', 'recognises an entry already recorded'] in data['files'])
    code, out, err = run(root, '--from', 'base')
    data = page_data(root)
    tab = data['snap'].get('from', {})
    check('a delta from an earlier commit still names the change, from changes.json as it was',
          code == 0 and 'Keys are stable' in [data['changes'][i]['name'] for i in tab.get('changes', [])]
          and tab.get('files', {}).get('src/core/entries/dedupe.py') == 'add' and (tab['lines'].get('src/core/entries/#add') or {}).get('s') == 'chg', out + err)

    # ---- a renamed file is one line
    for how in ('with git', 'without telling git'):
        back(root)
        if how == 'with git':
            git(root, 'mv', MONTHLY_PY, 'src/core/reports/month.py')
        else:
            os.rename(os.path.join(root, MONTHLY_PY), os.path.join(root, 'src/core/reports/month.py'))
        entries(root, {'name': 'A shorter name', 'line': 'month.py', 'files': {'src/core/reports/month.py': 'renamed'}})
        code, out, err = run(root)
        cc = page_data(root)['snap']['cc']
        check('a file renamed %s is one changed line that keeps its old name' % how, code == 0 and cc.get('moved') == {'src/core/reports/month.py': MONTHLY_PY}
              and cc['files'].get('src/core/reports/month.py') == 'chg' and cc['files'].get(MONTHLY_PY, '') is None, out + err + str(cc.get('files')))


def empty(tmp):
    for name, text in (('nothing', '{}\n'), ('seed', read(os.path.join(KIT, 'extras', 'tressoir-system-view', 'seeds', 'system.json')))):
        root = os.path.join(tmp, 'empty-' + name)
        write(root, 'src/app.py', 'x = 1\n')
        write(root, SV + 'system.json', text)
        write(root, SV + 'changes.json', '[]\n')
        git(root, 'init', '-q')
        code, out, err = run(root)
        data = page_data(root) if code == 0 else {'files': []}
        check('an empty system.json (%s) is not an error: the page says where to add boxes' % name,
              code == 0 and 'ERROR' not in out and 'No boxes yet' in data.get('none', '') and data['files'] == [['src/app.py', '']]
              and read(os.path.join(root, SV + 'system.json')) == text, out + err)


def commit(root, message):
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '-m', message)


def changes(root):
    return json.loads(read(os.path.join(root, SV + 'changes.json')))


def review(tmp):
    """What an independent review of the script found (2026-11-13), one case each."""
    count = [0]

    def new():
        count[0] += 1
        return mini(tmp, 'review-%d' % count[0])

    ent, rep = 'src/core/entries/', 'src/core/reports/'

    # ---- an entry the last commit holds, and the next task
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    a = {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'key 2', MONTHLY_PY: 'total 5'}, 'affects': ['add', 'monthly']}
    entries(root, a)
    run(root)
    commit(root, 'task A, code and SYSTEM_VIEW together')
    edit(root, ENTRIES_PY, 'return 2', 'return 3')
    b = {'name': 'B', 'line': 'b', 'files': {ENTRIES_PY: 'key 3'}, 'affects': ['add']}
    entries(root, a, b)
    code, out, err = run(root)
    data = page_data(root)
    check('a committed entry is taken out when the next task touches one of its files, with no error',
          code == 0 and 'ERROR' not in out and 'Took 1 built entry out' in out and [e['name'] for e in changes(root)] == ['B']
          and [data['changes'][i]['name'] for i in data['snap']['cc']['changes']] == ['B'], out + err)
    check('the note of a file that was only changed does not become its line', json.loads(read(os.path.join(root, SV + 'lines.json'))) == {})

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    a = {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'interface': {ent: ['add(entry: NewEntry, at: Date) → EntryId']}}
    entries(root, a)
    run(root)
    commit(root, 'task A')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    b = {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'y'}, 'affects': ['monthly'],
         'interface': {ent: ['add(entry: NewEntry, at: Date, by: Text) → EntryId']}}
    entries(root, a, b)
    code, out, err = run(root)
    data = page_data(root)
    check('a committed entry is taken out, not rewritten, when the next task restates a line it stated',
          code == 0 and 'both state' not in out and changes(root) == [b]
          and [data['changes'][i]['name'] for i in data['snap']['cc']['changes']] == ['B'], out + err)

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'the key is 2 now'}, 'affects': ['add']})
    run(root)
    commit(root, 'A')
    code, out, err = run(root)
    check('the note of a changed file does not become its line when its entry goes',
          code == 0 and 'Took 1 built entry' in out and json.loads(read(os.path.join(root, SV + 'lines.json'))) == {}, out + err)

    root = new()
    git(root, 'mv', MONTHLY_PY, rep + 'month.py')
    entries(root, {'name': 'A shorter name', 'line': 'month.py', 'files': {rep + 'month.py': 'renamed'}})
    run(root)
    commit(root, 'renamed')
    code, out, err = run(root)
    check('the note of a renamed file does not become its line',
          code == 0 and 'Took 1 built entry' in out and json.loads(read(os.path.join(root, SV + 'lines.json'))) == {}, out + err)

    # ---- a line stated by two built entries
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2\n\n\ndef count():\n    return 0')
    edit(root, MONTHLY_PY, 'return 0', 'return count()')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'count'}, 'interface': {ent: ['count() → Int  // how many']}},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'uses count'}, 'affects': ['monthly'], 'interface': {ent: ['count(month: Month) → Int']}})
    code, out, err = run(root)
    now = changes(root)
    check('two new entries may state a line system.json does not have yet: both are folded',
          code == 0 and 'ERROR' not in out and 'count(month: Month) → Int  // how many' in lines_of(root, ent)
          and now[0].get('affects') == ['count'] and 'interface' not in now[0], out + err + str(now))
    code, out, err = run(root)
    check('and a second run says and changes the same', code == 0 and 'ERROR' not in out and changes(root) == now, out + err)

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2\n\n\ndef count():\n    return 0')
    edit(root, MONTHLY_PY, 'return 0', 'return count()')
    pair = [{'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'count'}, 'interface': {ent: ['count() → Int  // how many']}},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'uses count'}, 'affects': ['yearly'], 'interface': {ent: ['count(month: Month) → Int']}}]
    entries(root, *pair)
    code, out, err = run(root)
    check('when the later of two entries fails a check, the earlier one keeps its line and is folded',
          code == 1 and 'Nothing was folded from: B.' in out and changes(root) == pair and 'count() → Int  // how many' in lines_of(root, ent), out + err)
    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2\n\n\ndef count():\n    return 0')
    edit(root, MONTHLY_PY, 'return 0', 'return count()')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'count'}, 'affects': ['count']},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'uses count'}, 'affects': ['monthly'], 'interface': {ent: ['count() → Int  // how many']}})
    code, out, err = run(root)
    check('a name under affects may be of a line a later entry brings', code == 0 and 'ERROR' not in out, out + err)

    root = new()
    write(root, 'src/core/tags/tags.py', 'def tag(x):\n    return x\n\n\ndef untag(x):\n    return x\n')
    edit(root, MONTHLY_PY, 'return 0', 'return 7')
    entries(root, {'name': 'A', 'line': 'a', 'files': {'src/core/tags/tags.py': 'tags'}, 'boxes': [
                {'name': 'Tags', 'folder': 'src/core/tags/', 'line': 'tags', 'interface': ['tag(x: Text) → Tag  // tags one', 'untag(x: Text)  // removes']}]},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'uses tag'}, 'affects': ['monthly'], 'interface': {'src/core/tags/': ['tag(x: Text, y: Text) → Tag']}})
    code, out, err = run(root)
    now = changes(root)
    check('an entry brings a box and a later one restates a line of it: the box is folded with the later line',
          code == 0 and 'ERROR' not in out and lines_of(root, 'src/core/tags/') == ['tag(x: Text, y: Text) → Tag  // tags one', 'untag(x: Text)  // removes']
          and now[0]['boxes'][0]['interface'] == ['untag(x: Text)  // removes'] and now[0].get('affects') == ['tag'], out + err + str(now))
    code, out, err = run(root)
    check('and a second run says and changes the same (a box brought by an entry)', code == 0 and 'ERROR' not in out and changes(root) == now, out + err)

    root = new()
    both = system(root)
    both['regions']['core']['boxes'][0]['interface'].append('export() → Text  // dumps entries')
    both['regions']['core']['boxes'][1]['interface'].append('export() → Text  // dumps reports')
    write(root, SV + 'system.json', json.dumps(both, ensure_ascii=False))
    run(root)
    commit(root, 'two boxes list export')
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    edit(root, 'src/entry/cli/main.py', 'add(argv)', 'add(argv[0])')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x', MONTHLY_PY: 'y'}, 'affects': ['add', 'monthly'], 'interface': {ent: ['export(fmt: Text) → Text']}},
            {'name': 'B', 'line': 'b', 'files': {'src/entry/cli/main.py': 'z'}, 'affects': ['main'], 'interface': {ent: ['export(fmt: Text, to: Path) → Text']}})
    code, out, err = run(root)
    check('a name the script puts under affects is written with its box when two boxes list it',
          code == 0 and 'ERROR' not in out and changes(root)[0].get('affects') == ['add', 'monthly', 'src/core/entries/: export'], out + err)

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    entries(root, {'name': 'A', 'line': 'a', 'files': {MONTHLY_PY: 'y'}, 'affects': ['monthly'], 'interface': {ent: ['count() → Int  // how many']}},
            {'name': 'B', 'line': 'b', 'files': {ENTRIES_PY: 'x'}, 'affects': ['add'], 'interface': {ent: ['count(month: Month) → Int']}})
    code, out, err = run(root)
    now = changes(root)
    code2, out2, err2 = run(root)
    check('and with its box when the earlier entry has no file in that box',
          code == 0 and code2 == 0 and 'ERROR' not in out + out2 and now[0].get('affects') == ['monthly', 'src/core/entries/: count'], out + err + out2)

    for runs in (1, 2):
        root = new()
        edit(root, ENTRIES_PY, 'return 1', 'return 2')
        edit(root, MONTHLY_PY, 'return 0', 'return 5')
        a = {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'interface': {ent: ['add(a: Int) → EntryId  // records it, with better words']}}
        b = {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'y'}, 'affects': ['monthly'], 'interface': {ent: ['add(a: Int, b: Int) → EntryId']}}
        if runs == 2:
            entries(root, a)
            run(root)
        entries(root, a, b)
        run(root)
        check('words the earlier entry gives are kept when the later one leaves them out (the script run %s)' % ('once for both' if runs == 1 else 'after each'),
              lines_of(root, ent)[0] == 'add(a: Int, b: Int) → EntryId  // records it, with better words', lines_of(root, ent)[0])

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'interface': {ent: ['add(a: Int) → EntryId', 'add(a: Int, b: Int) → EntryId']}},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'y'}, 'affects': ['monthly'], 'interface': {ent: ['add(a: Int, b: Int, c: Int) → EntryId']}})
    code, out, err = run(root)
    now = changes(root)
    run(root)
    check('an entry that states a name twice, restated by a later one, is settled in one run, and it is said',
          now == changes(root) and 'interface' not in now[0] and now[0].get('affects') == ['add'] and '"A" states add twice' in out, str(now) + out)

    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    edit(root, MONTHLY_PY, 'return 0', 'return 5')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'affects': ['add'], 'interface': {ent: ['NewEntry = { text: Text, at: Date }']}},
            {'name': 'B', 'line': 'b', 'files': {MONTHLY_PY: 'y'}, 'affects': ['monthly'], 'interface': {ent: ['- NewEntry']}})
    code, out, err = run(root)
    now = changes(root)
    check('a later "- Name" takes the earlier line of a type out too, and leaves no name under affects',
          code == 0 and 'interface' not in now[0] and now[0]['affects'] == ['add'] and not any(l.startswith('NewEntry') for l in lines_of(root, ent)), out + err + str(now))

    # ---- removing a type
    root = new()
    edit(root, ENTRIES_PY, 'class NewEntry:\n    pass\n\n\n', '')
    gone = {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'gone'}, 'interface': {ent: ['- NewEntry']}}
    entries(root, gone)
    code, out, err = run(root)
    cc = page_data(root)['snap']['cc']
    check('an entry that removes a type marks the type', code == 0 and cc['lines'].get('NewEntry') == {'s': 'del'} and cc['hits']['0'] == ['NewEntry'], cc['hits'])
    git(root, 'checkout', 'HEAD', '--', SV + 'system.json')
    commit(root, 'committed with system.json not folded')
    code, out, err = run(root)
    check('and stays while system.json at the last commit still has the type', code == 0 and 'Took' not in out and changes(root) == [gone], out + err)

    # ---- a plan that names a file in two entries
    p1 = {'name': 'P1', 'line': 'a', 'plan': 'X', 'files': {rep + 'yearly.py': '+ yearly totals'}, 'interface': {rep: ['yearly(y: Int) → Report  // one year']}}
    p2 = {'name': 'P2', 'line': 'b', 'plan': 'X', 'files': {rep + 'yearly.py': 'caches the totals'}, 'affects': ['yearly']}
    for order in ([p1, p2], [p2, p1]):
        root = new()
        entries(root, *order)
        code, out, err = run(root)
        data = page_data(root)
        check('a planned file one entry adds and another changes is shown as added (%s first)' % order[0]['name'],
              code == 0 and data['snap']['plan:0']['files'].get(rep + 'yearly.py') == 'add' and rep + 'yearly.py' in [f[0] for f in data['files']], out + err)

    # ---- hand-written files in a shape the script cannot read: a sentence, never a traceback, and nothing folded
    root = new()
    changed_entries = MINI_FILES[ENTRIES_PY].replace('return 1', 'return 2')
    core = lambda s: s['regions']['core']
    box = lambda s: core(s)['boxes'][0]

    def at(get, k, v):
        def f(s):
            get(s)[k] = v
        return f

    def entry(**kw):
        return dict({'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}}, **kw)

    def stops(sysmod=None, es=None, raw=None):
        back(root)
        if sysmod:
            bad = json.loads(json.dumps(MINI))
            sysmod(bad)
            write(root, SV + 'system.json', json.dumps(bad, ensure_ascii=False))
        if es is not None:
            write(root, ENTRIES_PY, changed_entries)
            entries(root, *es)
        if raw:
            with open(os.path.join(root, SV + raw[0]), 'wb') as f:
                f.write(raw[1])
        before = read(os.path.join(root, SV + 'system.json'))
        code, out, err = run(root)
        ok = (code == 2 and 'Traceback' not in err and err.startswith('system_view.py: WORK/SYSTEM_VIEW/') and len(err.strip().split('\n')) == 1
              and read(os.path.join(root, SV + 'system.json')) == before)
        return '' if ok else 'exit %d: %s' % (code, (err or out).strip().split('\n')[-1][:160])

    top = lambda s: s
    shapes = {
        'regions null': at(top, 'regions', None), 'name a number': at(top, 'name', 5), 'region folder a number': at(core, 'folder', 5),
        'region boxes null': at(core, 'boxes', None), 'region boxes an object': at(core, 'boxes', {}), 'also a number': at(box, 'also', 5),
        'also holds null': at(box, 'also', [None]), 'also a text': at(box, 'also', 'src/util.py'), 'inside a number': at(box, 'inside', 5),
        'links of a box hold text': at(box, 'links', ['x']), 'from a list': at(box, 'from', [rep]),
        'links an object': at(top, 'links', {'from': 'src/entry/', 'to': 'src/core/'}), 'links hold text': at(top, 'links', ['a']),
        'flows an object': at(top, 'flows', {'name': 'x', 'steps': []}), 'steps hold text': at(top, 'flows', [{'name': 'x', 'steps': [ent]}]),
        'a step at a list': at(top, 'flows', [{'name': 'x', 'steps': [{'at': [ent]}]}]), 'a line a number': at(box, 'interface', [5]),
        'a region folder "."': at(core, 'folder', '.')}
    wrong = ['%s (%s)' % (k, r) for k, r in ((k, stops(sysmod=f)) for k, f in shapes.items()) if r]
    check('a system.json in a wrong shape stops with one sentence: %d shapes' % len(shapes), not wrong, '; '.join(wrong))
    shapes = {
        'box folder a number': [entry(boxes=[{'folder': 5, 'name': 'x'}])], 'box interface holds a number': [entry(boxes=[{'folder': ent, 'interface': [5]}])],
        'box interface null': [entry(boxes=[{'folder': ent, 'interface': None}])], 'box also null': [entry(boxes=[{'folder': ent, 'also': None}])],
        'box also a number': [entry(boxes=[{'folder': ent, 'also': 5}])], 'box also a text': [entry(boxes=[{'folder': ent, 'also': 'src/core/x.py'}])],
        'new box inside holds text': [entry(boxes=[{'folder': 'src/core/n/', 'inside': ['x']}])],
        'inner box without folder': [entry(boxes=[{'folder': 'src/core/n/', 'inside': [{'folder': 'src/core/n/r/', 'boxes': [{'name': 'z'}]}]}])],
        'plan a list': [entry(plan=['p'])], 'plan true': [entry(plan=True), entry(name='B', plan='x')], 'files a list': [entry(files=[ENTRIES_PY])],
        'affects a text': [entry(affects='add')], 'an entry that is text': ['A']}
    wrong = ['%s (%s)' % (k, r) for k, r in ((k, stops(es=v)) for k, v in shapes.items()) if r]
    check('a changes.json in a wrong shape stops with one sentence, and nothing of it is folded: %d shapes' % len(shapes), not wrong, '; '.join(wrong))
    wrong = [k for k, raw in (('changes.json as Latin-1', ('changes.json', '[{"name":"Café","line":"é","files":{}}]'.encode('latin-1'))),
                              ('lines.json as UTF-16', ('lines.json', '{}'.encode('utf-16'))),
                              ('lines.json holds a list', ('lines.json', b'{"a.py": ["x"]}'))) if stops(raw=raw)]
    check('a file not saved as UTF-8, or a lines.json that is not paths and words, stops with one sentence', not wrong, wrong)
    back(root)
    with open(os.path.join(root, SV + 'seen'), 'wb') as f:
        f.write(b'\x00\x01')
    code, out, err = run(root)
    check('a seen file that holds no commit is said, and the page is built', code == 0 and 'Traceback' not in err and 'which is not a commit here' in out, out + err)
    os.remove(os.path.join(root, SV + 'seen'))
    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    entries(root, {'name': 'Fix', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'affects': ['add']}, {'name': 'Fix', 'line': 'b', 'files': {ENTRIES_PY: 'y'}})
    code, out, err = run(root)
    check('two entries with the same name stop the script, which says to rename one',
          code == 2 and 'two entries are named "Fix"' in err and 'rename one' in err, out + err)

    # ---- an entry that cannot be read, in an earlier commit
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    write(root, SV + 'changes.json', '[{"name":"A","line":"a","files":["src/core/entries/entries.py"]}]')
    commit(root, 'committed without running the script')
    entries(root)
    commit(root, 'the entry taken out')
    code, out, err = run(root, '--from', 'base')
    check('an entry that cannot be read in an earlier commit is left out of a delta, and said',
          code == 0 and 'Traceback' not in err and 'has an entry that cannot be read; it is left out' in out
          and 'from' in [t['id'] for t in page_data(root)['tabs']], out + err)
    write(root, SV + 'seen', subprocess.check_output(['git', 'rev-parse', 'base'], cwd=root).decode())
    code, out, err = run(root)
    check('and of Seen → Current', code == 0 and 'Traceback' not in err and 'seen' in [t['id'] for t in page_data(root)['tabs']], out + err)

    # ---- flat projects
    def flat(folder, at_top):
        count[0] += 1
        root = os.path.join(tmp, 'flat-%d' % count[0])
        pre = '' if at_top else folder
        write(root, SV + 'system.json', json.dumps({'name': 'Flat', 'regions': {
            'entry': {'folder': folder, 'line': 'in', 'boxes': [{'name': 'CLI', 'folder': pre + 'cli.py', 'line': 'commands', 'interface': ['main(argv: [Text])  // runs']}]},
            'core': {'folder': folder, 'line': 'does', 'boxes': [{'name': 'Store', 'folder': pre + 'store.py', 'line': 'keeps', 'interface': ['save(x: Text)  // saves']}]}}}))
        for path, text in {'cli.py': 'def main(argv):\n    return save(argv)\n', 'store.py': 'def save(x):\n    return x\n', 'util.py': 'def norm(x):\n    return x\n'}.items():
            write(root, pre + path, text)
        write(root, SV + 'changes.json', '[]\n')
        git(root, 'init', '-q')
        git(root, 'config', 'user.email', 'tests@example.com')
        git(root, 'config', 'user.name', 'Tests')
        run(root)
        commit(root, 'the base')
        return root

    root = flat('./', True)
    edit(root, 'util.py', 'return x', 'return x.strip()')
    write(root, 'newmod.py', 'def helper():\n    return 2\n')
    code, out, err = run(root, '--check')
    check('regions at the top of the repository are written "./": a changed file in no entry is an error there too',
          code == 1 and 'ERROR  2 changed files under the figure are in no entry: newmod.py, util.py' in out
          and 'note   2 files under ./ belong to no box: newmod.py, util.py.' in out, out + err)
    edit(root, 'cli.py', 'save(argv)', 'save(argv[0])')
    entries(root, {'name': 'B', 'line': 'b', 'files': {'cli.py': 'the first word', 'util.py': 'strips', 'newmod.py': 'helper'}, 'affects': ['main']})
    code, out, err = run(root)
    check('and an entry there is folded and drawn', code == 0 and 'ERROR' not in out and page_data(root)['views'][0]['rows'][0]['dir'] == './', out + err)
    root = flat('', True)
    code, out, err = run(root, '--check')
    check('a figure whose regions give no folder is said, with how the top of the repository is written',
          code == 0 and 'note   No region gives its folder' in out and '"./"' in out, out + err)
    root = flat('.', True)
    code, out, err = run(root, '--check')
    check('"." as a region\'s folder stops the script, which says to write "./"', code == 2 and 'The top of the repository is written "./"' in err, out + err)
    for folder in ('./', 'src/'):
        root = flat(folder, folder == './')
        pre = '' if folder == './' else folder
        write(root, pre + 'rates.py', 'def rate():\n    return 1\n')
        before = read(os.path.join(root, SV + 'system.json'))
        entries(root, {'name': 'Rates', 'line': 'r', 'files': {pre + 'rates.py': '+ exchange rates'},
                       'boxes': [{'name': 'Exchange rates', 'folder': pre + 'rates.py', 'line': 'daily rates'}]})
        code, out, err = run(root)
        check('a new box where regions share the folder %s is not placed by the script: an error that names the regions' % folder,
              code == 1 and 'Rates: the new box %srates.py could go in more than one region (entry, core): they share the folder %s' % (pre, folder) in out
              and read(os.path.join(root, SV + 'system.json')) == before, out + err)

    # ---- boxes that come and go
    root = new()
    shutil.rmtree(os.path.join(root, ent))
    entries(root, {'name': 'No entries', 'line': 'gone', 'files': {ENTRIES_PY: 'removed'}, 'interface': {ent: ['- add', '- listing', '- NewEntry']}})
    code, out, err = run(root)
    code2, out2, err2 = run(root)
    flow_error = 'ERROR  The flow "Adding an entry", step 2, is at src/core/entries/, which is not a box.'
    check('an entry that removes the lines of a box whose files are gone gives the same result on a second run',
          code == code2 and 'The box src/core/entries/ is removed' in out and out.count('ERROR') == 1 and out2.count('ERROR') == 1, out + err + out2 + err2)
    check('a flow step left at a box that is gone is an error, on every run', code == 1 and flow_error in out and flow_error in out2, out + out2)
    cc = page_data(root)['snap']['cc']
    check('and its lines are marked as the entry\'s', cc['boxes'].get(ent) == 'del' and 'src/core/entries/#add' in cc['hits']['0'] and 'NewEntry' in cc['hits']['0'], cc['hits'])

    root = new()
    write(root, ent + 'index/index.py', 'def find(x):\n    return x\n')
    inner = {'name': 'Index', 'folder': ent + 'index/', 'line': 'finds entries', 'interface': ['find(x: Text) → Entry?  // finds one']}
    entries(root, {'name': 'Index', 'line': 'i', 'files': {ent + 'index/index.py': '+ finds'}, 'boxes': [inner]})
    code, out, err = run(root)
    check('a new box inside the folder of a box is an error, and is not folded',
          code == 1 and 'Index: the new box src/core/entries/index/ is inside the box src/core/entries/' in out
          and [b['folder'] for b in system(root)['regions']['core']['boxes']] == [ent, rep], out + err)
    back(root)
    write(root, 'src/core/a/b/b.py', 'x = 1\n')
    entries(root, {'name': 'Deep', 'line': 'd', 'files': {'src/core/a/b/b.py': '+ b'}, 'boxes': [{'name': 'B', 'folder': 'src/core/a/b/', 'line': 'b'}]})
    code, out, err = run(root, '--check')
    check('a new box deeper than directly in a region is an error', code == 1 and 'Deep: the new box src/core/a/b/ is not directly in src/core/' in out, out + err)
    entries(root, {'name': 'Deep', 'line': 'd', 'files': {'src/core/a/b/b.py': '+ b'}, 'boxes': [{'name': 'A', 'folder': 'src/core/a/', 'line': 'a'}]})
    code, out, err = run(root, '--check')
    check('directly in a region it is folded as before', code == 0 and 'ERROR' not in out, out + err)

    root = new()
    odd = system(root)
    odd['regions']['core']['boxes'].append({'name': 'Ghost', 'folder': 'src/core/ghost/', 'line': 'nothing there'})
    write(root, SV + 'system.json', json.dumps(odd, ensure_ascii=False))
    code, out, err = run(root, '--check')
    check('a box with no file is said', code == 0 and 'note   No file is in the box src/core/ghost/.' in out, out + err)

    # ---- smaller things
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    write(root, 'WORK/notes.md', 'new\n')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x', 'WORK/notes.md': 'notes', 'WORK/more.md': '+ more'}, 'affects': ['add']})
    code, out, err = run(root, '--check')
    check('a file of the work folder in an entry is not said to be unchanged; a "+ " one is still looked for',
          code == 1 and 'WORK/notes.md does not differ' not in out and 'WORK/more.md is written as a new file ("+ ") and does not exist' in out, out + err)
    back(root)
    code, out, err = run(root, '--check', '--seen')
    check('--check with --seen writes nothing', code == 0 and 'Nothing is written' in out and not os.path.exists(os.path.join(root, SV + 'seen')), out + err)
    write(root, ENTRIES_PY, MINI_FILES[ENTRIES_PY] + '# pad pad pad\n' * 45000)
    code, out, err = run(root, '--check')
    check('a name is still found in a file too large to read as code', 'found nowhere' not in out, out + err)
    back(root)
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    entries(root, {'name': 'A', 'line': 'a', 'files': {ENTRIES_PY: 'x'}, 'interface': {ent: ['add(entry: NewEntry, at: Date) → EntryId']}})
    os.remove(os.path.join(root, 'WORK/SYSTEM_VIEW.html'))
    p = subprocess.run([sys.executable, SCRIPT], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=dict(os.environ, LC_ALL='C', LANG='C', PYTHONIOENCODING='latin-1', PYTHONUTF8='0'))
    check('on a terminal that is not UTF-8 the script still ends and writes the page',
          p.returncode == 0 and b'Traceback' not in p.stderr and os.path.exists(os.path.join(root, 'WORK/SYSTEM_VIEW.html')), p.stderr.decode('latin-1')[-300:])
    back(root)
    routes = system(root)
    routes['regions']['entry']['boxes'][0]['interface'] = ['GET /users  // lists users', 'GET /orders  // lists orders']
    write(root, SV + 'system.json', json.dumps(routes, ensure_ascii=False))
    code, out, err = run(root, '--check')
    check('two routes that start with the same word are an error that says how to name them',
          code == 1 and 'GET is written twice: in src/entry/cli/. The name of a line is its first word.' in out and 'get_users' in out, out + err)

    # ---- the proposal of affects on a large box: each function is read once
    root = new()
    files, fns = 150, 40
    for i in range(files):
        write(root, ent + 'mod%d.py' % i, ''.join('def f%d_%d(x):\n    return f%d_%d(x) + helper_%d(x)\n\n' % (i, j, i, j + 1, j) for j in range(fns)))
    commit(root, 'a large box')

    def timed(n):
        git(root, 'checkout', '-q', '--', '.')
        for i in range(n):
            edit(root, ent + 'mod%d.py' % i, 'def f%d_%d(x):\n    return f%d_%d(x)' % (i, fns - 1, i, fns), 'def f%d_%d(x):\n    return 1 + f%d_%d(x)' % (i, fns - 1, i, fns))
        start = time.time()
        code, out, err = run(root, '--check')
        return time.time() - start, code, out + err

    few, code, _said = timed(3)
    many, code, _said = timed(30)
    check('proposing affects for 30 changed files of a large box costs little more than for 3', code == 1 and many < few * 3 + 2,
          '%.1f s for 3 files, %.1f s for 30' % (few, many))


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


def flat_app(tmp, name, links=None):
    """A project whose code is one folder, app/: its regions share it and its boxes are files."""
    root = os.path.join(tmp, name)
    box = lambda n, f, line: {'name': n, 'folder': f, 'line': 'does ' + n, 'interface': [line]}
    write(root, SV + 'system.json', json.dumps({'name': 'Flat app', 'regions': {
        'entry': {'folder': 'app/', 'line': 'in', 'boxes': [box('CLI', 'app/cli.py', 'main(argv: [Text])  // runs')]},
        'core': {'folder': 'app/', 'line': 'does', 'boxes': [box('Store', 'app/store.py', 'save(x: Text)  // saves')]},
        'platform': {'folder': 'app/', 'line': 'one system only', 'boxes': [box('Blocker', 'app/block.py', 'block(seconds: Int)  // blocks')]}},
        'links': links or [],
        'flows': [{'name': 'Blocking', 'line': 'from the command to the block', 'steps': [
            {'at': 'app/cli.py', 'does': 'reads the command', 'calls': 'main'},
            {'at': 'app/block.py', 'gets': 'seconds', 'does': 'blocks', 'calls': 'block'}]}]}))
    for path, text in {'app/__init__.py': '', 'app/cli.py': 'def main(argv):\n    return block(save(argv))\n',
                       'app/store.py': 'def save(x):\n    return x\n', 'app/block.py': 'def block(seconds):\n    return seconds\n'}.items():
        write(root, path, text)
    write(root, SV + 'changes.json', '[]\n')
    write(root, SV + 'lines.json', json.dumps({'app/block.py': 'keeps the apps closed', 'app/cli.py': 'the commands'}))
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'tests@example.com')
    git(root, 'config', 'user.name', 'Tests')
    return root


def trial(tmp):
    """What the first trial by an agent that had never seen the system view found (2026-11-13), one case each."""
    count = [0]

    def new():
        count[0] += 1
        return mini(tmp, 'trial-%d' % count[0])

    ent, rep, summ = 'src/core/entries/', 'src/core/reports/', 'src/core/summaries/'
    box_at = lambda root, folder: next((b for r in system(root)['regions'].values() for b in (r or {}).get('boxes', []) if b['folder'] == folder), None)

    # ---- a box that moves, in a project with one folder per box
    def renamed():
        root = new()
        s = system(root)
        s['flows'].append({'name': 'A monthly report', 'line': 'totals', 'steps': [{'at': rep, 'does': 'totals the month', 'calls': 'monthly'}]})
        write(root, SV + 'system.json', json.dumps(s, ensure_ascii=False))
        write(root, SV + 'lines.json', json.dumps({rep: 'the reports', MONTHLY_PY: 'the monthly total'}))
        run(root)
        commit(root, 'a flow and a few words')
        git(root, 'mv', 'src/core/reports', 'src/core/summaries')
        return root

    root = renamed()
    entries(root, {'name': 'Reports become summaries', 'line': 'r', 'files': {summ + 'monthly.py': 'moved from reports/'}})
    before = read(os.path.join(root, SV + 'system.json'))
    code, out, err = run(root)
    check('a box whose files were all renamed is not removed: an error that says how to state the move',
          code == 1 and 'ERROR  The box src/core/reports/ has no file left, and its code is not gone' in out
          and '"moves": { "src/core/reports/": "src/core/summaries/" }' in out and 'is removed' not in out
          and read(os.path.join(root, SV + 'system.json')) == before, out + err)

    root = renamed()
    entries(root, {'name': 'Reports become summaries', 'line': 'r', 'files': {summ + 'monthly.py': 'moved from reports/'}, 'moves': {rep: summ}})
    code, out, err = run(root)
    moved, s = box_at(root, summ), system(root)
    check('"moves" carries the box to its new path, with its name, line and interface',
          code == 0 and 'ERROR' not in out and box_at(root, rep) is None and moved is not None and moved['name'] == 'Reports'
          and moved['interface'] == ['monthly(month: Month) → Report  // one month'], out + err)
    check('the flow step that was at the box follows it', s['flows'][1]['steps'][0]['at'] == summ, s['flows'])
    words = json.loads(read(os.path.join(root, SV + 'lines.json')))
    check('the few words of the folder and of its renamed file follow too',
          words == {summ: 'the reports', summ + 'monthly.py': 'the monthly total'}, words)
    cc = page_data(root)['snap']['cc']
    check('the page shows the old box removed and the new one added, both marked as the change\'s',
          cc['boxes'].get(rep) == 'del' and cc['boxes'].get(summ) == 'add'
          and summ + '#monthly' in cc['hits']['0'] and rep + '#monthly' in cc['hits']['0'], cc['hits'])
    commit(root, 'the move')
    code, out, err = run(root)
    code2, out2, err2 = run(root)
    check('once committed, an entry with "moves" leaves the list like any other',
          code == 0 and 'Took 1 built entry out' in out and changes(root) == [] and code2 == 0 and 'ERROR' not in out + out2
          and box_at(root, summ) is not None, out + err + out2 + err2)

    # ---- what "moves" refuses: anything more than the same box at another path
    for what, target, said in (
            ('to another region', 'src/entry/reports/', 'which is not in src/core/, the folder of its region'),
            ('onto another box', ent, 'which is already a box'),
            ('into another box', ent + 'reports/', 'which overlaps the box src/core/entries/')):
        root = new()
        before = read(os.path.join(root, SV + 'system.json'))
        entries(root, {'name': 'Move', 'line': 'm', 'files': {}, 'moves': {rep: target}})
        code, out, err = run(root, '--check')
        check('"moves" does not carry a box %s: that is architecture' % what,
              code == 1 and said in out and 'tell the owner' in out and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    root = new()
    entries(root, {'name': 'Move', 'line': 'm', 'files': {}, 'moves': {'src/core/nothing/': summ}})
    code, out, err = run(root, '--check')
    check('"moves" that names no box is an error', code == 1 and 'Move: "moves" names src/core/nothing/, which is not a box.' in out, out + err)
    root = new()
    entries(root, {'name': 'Move', 'line': 'm', 'files': {}, 'moves': [rep, summ]})
    code, out, err = run(root, '--check')
    check('"moves" in a wrong shape stops the script with one sentence', code == 2 and '"moves" an object' in err, out + err)

    # ---- the same in a project whose code is one folder: a file that becomes a package
    def packaged(name):
        root = flat_app(tmp, name)
        run(root)
        commit(root, 'the base')
        os.makedirs(os.path.join(root, 'app/blocking'))
        git(root, 'mv', 'app/block.py', 'app/blocking/block.py')
        write(root, 'app/blocking/__init__.py', '')
        return root

    root = packaged('trial-flat-1')
    files = {'app/blocking/block.py': 'moved here', 'app/blocking/__init__.py': 'the package'}
    entries(root, {'name': 'Blocker in its own package', 'line': 'b', 'files': files})
    code, out, err = run(root)
    check('a one-file box whose file moved into a new folder: the error proposes that folder',
          code == 1 and '"moves": { "app/block.py": "app/blocking/" }' in out and box_at(root, 'app/block.py') is not None, out + err)
    entries(root, {'name': 'Blocker in its own package', 'line': 'b', 'files': files, 'moves': {'app/block.py': 'app/blocking/'}})
    code, out, err = run(root)
    s = system(root)
    check('with "moves" the box stays in its region although the regions share the folder',
          code == 0 and 'ERROR' not in out and [b['folder'] for b in s['regions']['platform']['boxes']] == ['app/blocking/']
          and s['flows'][0]['steps'][1]['at'] == 'app/blocking/', out + err)
    check('an empty file, such as a package marker, is not said to belong to no box', 'belong' not in out, out)
    check('the renamed file keeps its few words', json.loads(read(os.path.join(root, SV + 'lines.json'))).get('app/blocking/block.py') == 'keeps the apps closed')

    # ---- regions that share a folder are told apart by their key
    root = flat_app(tmp, 'trial-flat-2', links=[{'from': 'entry', 'to': 'core', 'label': 'saves', 'says': 'The commands save through the store.'}])
    code, out, err = run(root)
    over = page_data(root)['views'][0]
    check('a link between regions is written with their keys, and drawn where they share a folder',
          code == 0 and 'note' not in out and [(l['from'], l['to']) for l in over['links']] == [('entry', 'core')]
          and [r['id'] for r in over['rows']] == ['entry', 'core'] and over['band']['id'] == 'platform', out + err + str(over['links']))
    page = read(os.path.join(root, 'WORK', 'SYSTEM_VIEW.html'))
    check('the page picks a region by its key, not by its folder', 'data-pick="region:${g.r.id}"' in page and 'region:${g.r.dir}' not in page)
    root = flat_app(tmp, 'trial-flat-3', links=[{'from': 'app/', 'to': 'core', 'says': 's'}])
    code, out, err = run(root)
    check('a link that names a folder several regions share is said, with what to write',
          code == 0 and 'points at app/, which is the folder of entry and core and platform. Name the region by its key' in out
          and page_data(root)['views'][0]['links'] == [], out + err)

    # ---- a flow step at nothing
    root = new()
    s = system(root)
    s['flows'][0]['steps'][1]['at'] = 'src/core/nothing/'
    write(root, SV + 'system.json', json.dumps(s, ensure_ascii=False))
    code, out, err = run(root, '--check')
    check('a flow step at a path that is not a box is an error', code == 1 and 'step 2, is at src/core/nothing/, which is not a box' in out, out + err)

    # ---- a renamed file keeps its words; what the script says of itself
    root = new()
    write(root, SV + 'lines.json', json.dumps({ENTRIES_PY: 'add and list'}))
    commit(root, 'words')
    git(root, 'mv', ENTRIES_PY, ent + 'records.py')
    entries(root, {'name': 'Renamed', 'line': 'r', 'files': {ent + 'records.py': 'renamed'}})
    code, out, err = run(root)
    check('a renamed file keeps its few words in lines.json',
          code == 0 and json.loads(read(os.path.join(root, SV + 'lines.json'))) == {ent + 'records.py': 'add and list'}, out + err)
    root = new()
    write(root, SV + 'system.json', json.dumps(system(root), ensure_ascii=False))
    code, out, err = run(root)
    check('a system.json that is only set in the script\'s layout is not said to be folded',
          code == 0 and 'Folded' not in out and 'nothing in it changed' in out, out + err)
    root = os.path.join(tmp, 'trial-seed')
    write(root, 'src/app.py', 'x = 1\n')
    write(root, SV + 'system.json', read(os.path.join(KIT, 'extras', 'tressoir-system-view', 'seeds', 'system.json')))
    write(root, SV + 'changes.json', '[]\n')
    git(root, 'init', '-q')
    code, out, err = run(root, '--check')
    check('with no box written yet, the script says where to start', code == 0 and 'note   No box is written yet' in out and 'Starting in a project' in out, out + err)
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    code, out, err = run(root, '--check')
    check('the prepared entry says where a changed signature goes', code == 1 and '"affects": ["add"]' in out and 'goes under "interface" instead' in out, out + err)


def pocket_repository(tmp):
    """The third example, a project whose code is one folder, rebuilt as a repository: the last commit has the notifier
    as one file and no word list; the working tree has the example's two built changes. Returns the folder and what the
    script said on the last commit's state."""
    ex = os.path.join(EXAMPLES, 'pocket')
    want, words = json.loads(read(os.path.join(ex, 'system.json'))), json.loads(read(os.path.join(ex, 'lines.json')))
    root = os.path.join(tmp, 'pocket')
    was = json.loads(json.dumps(want))
    for b in was['regions']['platform']['boxes']:
        b['folder'] = 'pocket/notify.py'
    for b in was['regions']['core']['boxes']:
        b.pop('also', None)
    for step in was['flows'][0]['steps']:
        if step['at'] == 'pocket/notify/':
            step['at'] = 'pocket/notify.py'
    code_of = {'pocket/search.py': 'def find(words):\n    return []\n', 'pocket/notify.py': 'def notify(title):\n    return title\n'}
    for path, w in words.items():
        if not path.endswith('/') and not path.startswith('pocket/notify/') and path != 'pocket/stopwords.txt':
            write(root, path, code_of.get(path, '# ' + w + '\n'))
    write(root, 'pocket/notify.py', code_of['pocket/notify.py'])
    write(root, SV + 'system.json', json.dumps(was, ensure_ascii=False))
    write(root, SV + 'changes.json', '[]\n')
    before = {p: w for p, w in words.items() if not p.startswith('pocket/notify/') and p != 'pocket/stopwords.txt'}
    write(root, SV + 'lines.json', json.dumps(dict(before, **{'pocket/notify.py': words['pocket/notify/macos.py']})))
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'tests@example.com')
    git(root, 'config', 'user.name', 'Tests')
    first = run(root)
    commit(root, 'the last commit')
    os.makedirs(os.path.join(root, 'pocket/notify'))
    git(root, 'mv', 'pocket/notify.py', 'pocket/notify/macos.py')
    write(root, 'pocket/notify/__init__.py', 'from .macos import notify\n')
    write(root, 'pocket/notify/linux.py', 'def notify(title):\n    return title\n')
    write(root, 'pocket/stopwords.txt', 'the\na\n')
    write(root, 'pocket/search.py', 'def find(words):\n    return [w for w in words if w]\n')
    write(root, SV + 'changes.json', read(os.path.join(ex, 'changes.json')))
    return root, first


def pocket(tmp):
    ex = os.path.join(EXAMPLES, 'pocket')
    want, words = json.loads(read(os.path.join(ex, 'system.json'))), json.loads(read(os.path.join(ex, 'lines.json')))
    root, (code, out, err) = pocket_repository(tmp)
    check('pocket: the figure of a one-folder project builds with no error, and every file is in a box',
          code == 0 and 'ERROR' not in out and 'belong' not in out and 'points at' not in out, out + err)
    code, out, err = run(root)
    check('pocket: the example\'s two changes, one of them a moved box, fold with no error', code == 0 and 'ERROR' not in out, out + err)
    check('pocket: system.json becomes the example\'s', unordered(system(root)) == unordered(want))
    data = page_data(root)
    over, cc = data['views'][0], data['snap']['cc']
    check('pocket: four regions on one folder are four regions on the page, with their links',
          [r['id'] for r in over['rows']] + [over['band']['id']] == ['entry', 'core', 'external', 'platform']
          and [(l['from'], l['to']) for l in over['links']] == [('entry', 'core'), ('core', 'external')], over['links'])
    check('pocket: the moved box is marked as its change\'s', 'pocket/notify/#notify' in cc['hits']['0'] and cc['boxes'].get('pocket/notify/') == 'add', cc['hits'])
    got = json.loads(read(os.path.join(root, SV + 'lines.json')))
    check('pocket: the moved file keeps its few words', got.get('pocket/notify/macos.py') == words['pocket/notify/macos.py'] and 'pocket/notify.py' not in got, got)
    commit(root, 'the two changes')
    code, out, err = run(root)
    check('pocket: once committed both entries leave the list', code == 0 and 'Took 2 built entries out' in out and changes(root) == [], out + err)


def main():
    tmp = tempfile.mkdtemp(prefix='tressoir-system-view-tests.')
    try:
        tally(tmp)
        marlin(tmp)
        no_repository(tmp)
        checks(tmp)
        empty(tmp)
        review(tmp)
        trial(tmp)
        pocket(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\nResult: %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
