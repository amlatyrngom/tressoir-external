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


def mini(tmp):
    root = os.path.join(tmp, 'mini')
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
        marlin(tmp)
        no_repository(tmp)
        checks(tmp)
        empty(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\nResult: %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
