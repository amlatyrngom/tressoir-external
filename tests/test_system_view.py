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
    # ---- flows: the page carries each one under the id of the function it is the body of
    flows, snap = data['flows'], data['snap']
    wire, sched, commit_id = 'src/entry/wire/#handle', 'src/core/execution/pipelines/scheduler/#run', 'src/core/transactions/durability/commit/#commit'
    codes = lambda lines: [l[1] for l in lines or []]
    called = lambda lines, code: next((l[3] for l in lines or [] if l[1] == code), None)
    check('marlin: the folded flows are the example\'s, and the flow an entry states is written into system.json',
          got.get('flows') == want['flows'] and 'wal.flush_group(lsn)  # one flush serves every commit waiting in the group' in got['flows'][3]['sketch'], got.get('flows'))
    check('marlin: the page carries every flow under the id of its function, a list of [level, code, words, calls]',
          list(flows) == [wire, 'src/core/optimizer/#optimize', sched, commit_id]
          and all(len(l) == 4 and isinstance(l[0], int) and isinstance(l[3], list) for lines in flows.values() for l in lines), list(flows))
    check('marlin: a flow\'s lines keep their depth, their code and the words after the #',
          flows[wire][:3] == [[0, 'plan: Plan | None = sql.cached_plan(session, message.sql)',
                               'the same text run before keeps its plan, so most statements skip the next two steps', ['src/core/sql/#cached_plan']],
                              [0, 'if plan is None:', '', []],
                              [1, 'stmt: Statement = sql.compile(message.sql, catalog)', 'text to a checked, bound statement', ['src/core/sql/#compile']]], flows[wire][:3])
    check('marlin: a call written bare is a function of the flow\'s own box', called(flows[wire], 'send(session, batch)') == ['src/entry/wire/#send'], flows[wire])
    check('marlin: a call through a box that lists a bare name is the function of the box inside',
          called(flows[wire], 'rows: RowStream = execution.run(plan, snapshot)') == [sched]
          and called(flows[wire], 'snapshot: Snapshot = transactions.snapshot(session.txn)') == ['src/core/transactions/isolation/snapshots/#snapshot'], flows[wire])
    check('marlin: a box is called by the last part of its folder (wal, replicas, conflicts)',
          [l[3] for l in flows[commit_id]] == [['src/core/transactions/isolation/conflicts/#check'], [], ['src/core/storage/disk/wal/#append'],
                                               ['src/core/storage/disk/wal/#flush_group'], ['src/connectors/replicas/#ship'], []], flows[commit_id])
    check('marlin: calls stated by hand are carried as stated, with the words under "says"',
          flows['src/core/optimizer/#optimize'][1] == [0, 'tree: JoinTree = join_order.order(stmt)', 'which tables to join first, by how many rows each join should yield',
                                                       ['src/core/optimizer/search/join-order/#order', 'src/core/optimizer/estimates/cardinality/#estimate']],
          flows['src/core/optimizer/#optimize'])
    check('marlin: the Current tab has every flow as listed', 'flows' not in snap['current'], snap['current'].get('flows'))
    was = (snap['committed'].get('flows') or {}).get(commit_id)
    check('marlin: the Committed tab has the flow of commit as it was, without the line the entry adds',
          codes(was) == [c for c in codes(flows[commit_id]) if c != 'wal.flush_group(lsn)'] and len(codes(was)) == 5 and all(len(l) == 4 for l in was), was)
    wire_delta = (snap['cc'].get('flows') or {}).get(wire) or []
    check('marlin: the flow of handle, which another entry states, is given line by line: two lines out, four in',
          [l[1] for l in wire_delta if l[4:] == ['del']] == ['stmt: Statement = sql.compile(message.sql, catalog)', 'plan: Plan = optimizer.optimize(stmt, catalog)']
          and [l[1] for l in wire_delta if l[4:] == ['add']] == ['plan: Plan | None = sql.cached_plan(session, message.sql)', 'if plan is None:',
                                                                 'stmt: Statement = sql.compile(message.sql, catalog)', 'plan = optimizer.optimize(stmt, catalog)']
          and 'cached_plan' not in ' '.join(codes((snap['committed'].get('flows') or {}).get(wire))), wire_delta)
    delta = (snap['cc'].get('flows') or {}).get(commit_id) or []
    check('marlin: in Committed → Current the line the entry adds to the flow of commit ends with "add", and no other line is marked',
          codes(delta) == codes(flows[commit_id]) and [l[1] for l in delta if len(l) == 5] == ['wal.flush_group(lsn)']
          and [l[4] for l in delta if len(l) == 5] == ['add'], delta)
    check('marlin: a flow whose code did not change is not in the delta', list(snap['cc'].get('flows') or {}) == [wire, commit_id], list(snap['cc'].get('flows') or {}))
    check('marlin: the plan states no flow, so its tab has every flow as listed', 'flows' not in snap['plan:0'], snap['plan:0'].get('flows'))
    check('marlin: an entry that marks a function with a flow and does not state the flow is told to check it',
          'note   "Parallel hash join" changes run, which has a flow (src/core/execution/pipelines/scheduler/). Check that the flow still reads true' in out
          and '"Prepared statement cache" changes handle' not in out, out)
    check('marlin: the entry that states the flow is not told, nor one that changes another function of the same name',
          '"Group commit" changes commit' not in out and '"Backups to object storage" changes run' not in out, out)
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
    'flows': [
        {'of': 'src/entry/cli/: main', 'sketch': [
            'entry = NewEntry(argv)  # reads the command',
            'return entries.add(entry)  # records it']},
        {'of': 'src/core/entries/: add', 'sketch': [
            'key = _key(entry)  # the same entry gets the same key',
            'return _store(entry, key)']}]}
MAIN, ADD = 'src/entry/cli/#main', 'src/core/entries/#add'
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


def mini(tmp, name='mini', figure=None, files=None):
    root = os.path.join(tmp, name)
    for path, text in (files or MINI_FILES).items():
        write(root, path, text)
    write(root, SV + 'system.json', json.dumps(figure or MINI, ensure_ascii=False))
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


def put(root, change):
    """system.json with one thing changed by hand."""
    s = system(root)
    change(s)
    write(root, SV + 'system.json', json.dumps(s, ensure_ascii=False))


def flows_of(root):
    return system(root).get('flows', [])


def shown_flows(data, tab='current'):
    """The flows one tab shows: the page lists the flows of every state, and a tab has null for one its state lacks."""
    mine = data['snap'][tab].get('flows') or {}
    return [i for i in data['flows'] if mine.get(i, '') is not None]


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
    check('a built entry that marks a function with a flow, and does not state the flow, is told to check the flow',
          'note   "Keys are stable" changes add, which has a flow (src/core/entries/). Check that the flow still reads true; if its steps changed, '
          'state it again in the entry, under "flows".' in out, out)
    check('a change beneath a function a flow calls is not said of that flow, nor is anything said for an entry that was not folded',
          'changes main, which has a flow' not in out and '"Totals by year" changes' not in out and 'The flow "' not in out, out)
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
    bad['flows'][0]['sketch'] += ['nowhere.go()  # no box is called that', 'reports.yearly(2026)  # totals a year']
    bad['regions']['core']['boxes'][1]['uses'] = {'boxes': ['src/gone/'], 'says': 'nothing'}
    write(root, SV + 'system.json', json.dumps(bad, ensure_ascii=False))
    write(root, 'src/core/loose.py', 'x = 1\n')
    code, out, err = run(root)
    check('a link, a neighbour or a flow line that points at nothing is said, and the page is built',
          'A link of the overview points at src/nowhere/' in out
          and 'note   The flow of main (src/entry/cli/) calls reports.yearly(), which src/core/reports/ does not list. The line is shown without that call. '
              'If it is a listed function, write it as its box lists it; if the line calls nothing listed, say so: write the line as { "code": "...", "calls": [] }.' in out
          and 'src/core/reports/: "uses" names src/gone/' in out and os.path.exists(os.path.join(root, 'WORK/SYSTEM_VIEW.html')), out + err)
    check('a call through a word that names no box is not said: it is not a call into the figure', 'nowhere.go' not in out, out)
    check('the page shows such lines without a call',
          page_data(root)['flows'][MAIN][2:] == [[0, 'nowhere.go()', 'no box is called that', []], [0, 'reports.yearly(2026)', 'totals a year', []]], page_data(root)['flows'].get(MAIN))
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
        'flows an object': at(top, 'flows', {'of': ent + ': add', 'sketch': ['return 1']}), 'a flow that is text': at(top, 'flows', [ent + ': add']),
        'of a list': at(top, 'flows', [{'of': [ent, 'add'], 'sketch': ['return 1']}]), 'a sketch a number': at(top, 'flows', [{'of': ent + ': add', 'sketch': 5}]),
        'a sketch line a number': at(top, 'flows', [{'of': ent + ': add', 'sketch': ['return 1', 5]}]),
        'a sketch line with no code': at(top, 'flows', [{'of': ent + ': add', 'sketch': [{'says': 'records it'}]}]),
        'says of a sketch line a list': at(top, 'flows', [{'of': ent + ': add', 'sketch': [{'code': 'x()', 'says': ['a']}]}]),
        'calls of a sketch line a text': at(top, 'flows', [{'of': ent + ': add', 'sketch': [{'code': 'x()', 'calls': ent + ': add'}]}]),
        'a line a number': at(box, 'interface', [5]), 'a region folder "."': at(core, 'folder', '.')}
    wrong = ['%s (%s)' % (k, r) for k, r in ((k, stops(sysmod=f)) for k, f in shapes.items()) if r]
    check('a system.json in a wrong shape stops with one sentence: %d shapes' % len(shapes), not wrong, '; '.join(wrong))
    shapes = {
        'box folder a number': [entry(boxes=[{'folder': 5, 'name': 'x'}])], 'box interface holds a number': [entry(boxes=[{'folder': ent, 'interface': [5]}])],
        'box interface null': [entry(boxes=[{'folder': ent, 'interface': None}])], 'box also null': [entry(boxes=[{'folder': ent, 'also': None}])],
        'box also a number': [entry(boxes=[{'folder': ent, 'also': 5}])], 'box also a text': [entry(boxes=[{'folder': ent, 'also': 'src/core/x.py'}])],
        'new box inside holds text': [entry(boxes=[{'folder': 'src/core/n/', 'inside': ['x']}])],
        'inner box without folder': [entry(boxes=[{'folder': 'src/core/n/', 'inside': [{'folder': 'src/core/n/r/', 'boxes': [{'name': 'z'}]}]}])],
        'plan a list': [entry(plan=['p'])], 'plan true': [entry(plan=True), entry(name='B', plan='x')], 'files a list': [entry(files=[ENTRIES_PY])],
        'affects a text': [entry(affects='add')], 'an entry that is text': ['A'],
        'flows an object': [entry(flows={'of': ent + ': add', 'sketch': ['return 1']})], 'a flow that is text': [entry(flows=[ent + ': add'])],
        'a flow with no of': [entry(flows=[{'sketch': ['return 1']}])], 'a flow whose of is a list': [entry(flows=[{'of': [ent, 'add'], 'sketch': ['return 1']}])],
        'a flow whose sketch holds a number': [entry(flows=[{'of': ent + ': add', 'sketch': [5]}])],
        'a flow whose line states its calls as text': [entry(flows=[{'of': ent + ': add', 'sketch': [{'code': 'x()', 'calls': 'add'}]}])]}
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
    check('an entry that removes the lines of a box whose files are gone gives the same result on a second run',
          code == code2 == 0 and 'The box src/core/entries/ is removed' in out and 'ERROR' not in out + out2, out + err + out2 + err2)
    check('the flow of a function that goes with its box goes too, and no flow is left at a box that is gone',
          'note   No entries removed add from src/core/entries/, and its flow with it.' in out
          and [f['of'] for f in system(root)['flows']] == ['src/entry/cli/: main'], out + str(system(root)['flows']))
    data = page_data(root)
    cc = data['snap']['cc']
    check('a line that called into the box that is gone is shown without the call, and nothing is said of it',
          data['flows'][MAIN][1] == [0, 'return entries.add(entry)', 'records it', []] and 'entries.add' not in out + out2, out + out2)
    check('the page still has the flow that is gone, for the tabs that had it: it is null in the Current tab',
          ADD in data['flows'] and data['snap']['current'].get('flows', {}).get(ADD, '') is None
          and [l[3] for l in data['snap']['committed'].get('flows', {}).get(MAIN, [])] == [[], [ADD]], data['snap']['current'].get('flows'))
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
    add = 'src/core/entries/#add'
    was, delta = (data['snap']['committed'].get('flows') or {}).get(add) or [], (data['snap']['cc'].get('flows') or {}).get(add) or []
    check('tally: the Committed tab has the flow of add as it was, and Committed → Current marks the two lines the entry adds',
          [l[1] for l in was] == ['id: EntryId = next_id()', 'store.write(Change.insert(id, entry))', 'return id']
          and [l[1:2] + l[4:] for l in delta] == [['if already_recorded(entry):', 'add'], ['return None', 'add'], ['id: EntryId = next_id()'],
                                                 ['store.write(Change.insert(id, entry))'], ['return id']]
          and list(data['snap']['cc']['flows']) == [add] and 'flows' not in data['snap']['current'], str(was) + str(delta))
    code, out, err = run(root, '--check', '--flows')
    check('tally: --flows prints the flows, each line at its depth with the calls found',
          code == 0 and '\nThe flow of main (src/entry/cli/):\n  command = read(args)\n  if command.name == "import":\n'
                        '      found: list[NewEntry] = bank_files.parse(command.path)    -> src/connectors/bank-files/: parse\n      for entry in found:\n'
                        '          categories.categorize(entry)    -> src/core/categories/: categorize\n' in out
          and '\nThe flow of add (src/core/entries/):\n  if already_recorded(entry):\n      return None\n' in out, out + err)

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
    check('Seen → Current still marks the lines the milestone added to the flow of add; Committed → Current has no flow to mark',
          [l[1] for l in (seen.get('flows') or {}).get(add) or [] if l[4:] == ['add']] == ['if already_recorded(entry):', 'return None']
          and 'flows' not in cc, str(seen.get('flows')) + str(cc.get('flows')))


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
        'flows': [
            {'of': 'app/cli.py: main', 'sketch': [
                'seconds = store.save(argv)  # reads the command',
                {'code': 'block.block(seconds)', 'says': 'blocks', 'calls': ['app/block.py: block']}]},
            {'of': 'app/block.py: block', 'sketch': ['sleep(seconds)  # keeps the apps closed']}]}))
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
        s['flows'].append({'of': rep + ': monthly', 'sketch': ['return total(month)  # totals the month']})
        s['flows'][0]['sketch'].append({'code': 'show(this_month())', 'says': 'prints the month', 'calls': [rep + ': monthly']})
        s['flows'][0]['sketch'].append('reports.monthly(last_month())')
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
    check('and no note beside it says to take the box out', 'No file is in the box' not in out, out)

    root = renamed()
    entries(root, {'name': 'Reports become summaries', 'line': 'r', 'files': {summ + 'monthly.py': 'moved from reports/'}, 'moves': {rep: summ}})
    code, out, err = run(root)
    moved, s = box_at(root, summ), system(root)
    check('"moves" carries the box to its new path, with its name, line and interface',
          code == 0 and 'ERROR' not in out and box_at(root, rep) is None and moved is not None and moved['name'] == 'Reports'
          and moved['interface'] == ['monthly(month: Month) → Report  // one month'], out + err)
    check('the flow of a function of the box follows it, and so does a call stated by hand',
          [f['of'] for f in s['flows']] == ['src/entry/cli/: main', 'src/core/entries/: add', summ + ': monthly']
          and s['flows'][0]['sketch'][2] == {'code': 'show(this_month())', 'says': 'prints the month', 'calls': [summ + ': monthly']}, s['flows'])
    data = page_data(root)
    flows = data['flows']
    check('on the page the calls into the box are at its new path, a call written by the box\'s name among them',
          [l[3] for l in flows[MAIN][2:]] == [[summ + '#monthly'], [summ + '#monthly']]
          and [l[3] for l in data['snap']['committed']['flows'][MAIN][2:]] == [[rep + '#monthly'], [rep + '#monthly']], flows)
    check('and the flow is at its new path now, at its old one at the last commit',
          shown_flows(data) == [MAIN, ADD, summ + '#monthly'] and shown_flows(data, 'committed') == [MAIN, ADD, rep + '#monthly'], data['snap']['current'].get('flows'))
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
          and s['flows'][1]['of'] == 'app/blocking/: block' and s['flows'][0]['sketch'][1]['calls'] == ['app/blocking/: block'], out + err)
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

    # ---- a flow of nothing
    root = new()
    s = system(root)
    s['flows'][1]['of'] = 'src/core/nothing/: add'
    write(root, SV + 'system.json', json.dumps(s, ensure_ascii=False))
    code, out, err = run(root, '--check')
    check('a flow of a path that is not a box is an error',
          code == 1 and 'ERROR  The flow of add (src/core/nothing/) names src/core/nothing/, which is not a box. It is not shown.' in out, out + err)

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
    save = 'pocket/pages.py#save'
    check('pocket: the flows are the example\'s, each under the id of its function', system(root)['flows'] == want['flows']
          and list(data['flows']) == ['pocket/cli.py#cmd_add', save], list(data['flows']))
    check('pocket: a box that is one file is called by the file\'s name without its ending',
          [l[3] for l in data['flows']['pocket/cli.py#cmd_add']] == [[save], []]
          and [l[3] for l in data['flows'][save]] == [['pocket/fetch.py#fetch'], ['pocket/clean.py#clean'], ['pocket/store.py#put'], ['pocket/notify/#notify'], []],
          data['flows'])
    was = (data['snap']['committed'].get('flows') or {}).get(save) or []
    check('pocket: a call into the moved box follows it: the Committed tab has it at the old path, the delta has no line to mark',
          [l[3] for l in was][3:4] == [['pocket/notify.py#notify']] and 'flows' not in cc and 'flows' not in data['snap']['current'], data['snap']['committed'].get('flows'))
    commit(root, 'the two changes')
    code, out, err = run(root)
    check('pocket: once committed both entries leave the list', code == 0 and 'Took 2 built entries out' in out and changes(root) == [], out + err)


# ---------------------------------------------------------------- flows: the body of a listed function, as a sketch

def flows(tmp):
    """A flow is the body of one listed function, written as a sketch: how it names its function, how its lines are
    written, what is wrong with one, and what an entry of changes.json does to it. One case each."""
    count = [0]

    def new():
        count[0] += 1
        return mini(tmp, 'flows-%d' % count[0])

    ent, rep, cli = 'src/core/entries/', 'src/core/reports/', 'src/entry/cli/'
    monthly = rep + '#monthly'
    main_flow, add_flow = MINI['flows']

    # ---- how a flow names its function
    root = new()
    put(root, lambda s: s.update(flows=[{'of': 'Command line: main', 'sketch': ['return entries.add(argv)']},
                                        {'of': 'monthly', 'sketch': ['return total(month)']},
                                        {'of': 'src/core/entries: add', 'sketch': ['return _store(entry)']}]))
    code, out, err = run(root)
    check('a flow may name its box by the box\'s name, or the function alone when one box lists it: the script writes the folder',
          code == 0 and 'ERROR' not in out and [f['of'] for f in flows_of(root)] == [cli + ': main', rep + ': monthly', ent + ': add'], out + err + str(flows_of(root)))
    check('and the page has each flow under the id of its function', list(page_data(root)['flows']) == [MAIN, monthly, ADD], list(page_data(root)['flows']))

    def twice(s):
        for b in s['regions']['core']['boxes']:
            b['interface'].append('export() → Text  // as text')
        s['flows'] = [{'of': 'export', 'sketch': ['return text()']}, {'of': 'Nowhere: add', 'sketch': ['return 1']}]
    back(root)
    put(root, twice)
    code, out, err = run(root)
    check('a flow that names only a function two boxes list is an error that asks for the box',
          code == 1 and 'ERROR  The flow of export names export, which src/core/entries/ and src/core/reports/ list: write "<box folder>: export". It is not shown.' in out
          and 'ERROR  The flow of add (Nowhere) names Nowhere, which is not a box. It is not shown.' in out and shown_flows(page_data(root)) == [], out + err)

    def same_name(s):
        s['regions']['core']['boxes'][1]['name'] = 'Entries'
        s['flows'][1]['of'] = 'Entries: add'
    back(root)
    put(root, same_name)
    code, out, err = run(root, '--check')
    check('a flow that names its box by a name two boxes have is an error that asks for the folder',
          code == 1 and 'ERROR  The flow of add (Entries) names Entries, which is the name of src/core/entries/ and src/core/reports/: write the box\'s folder. '
                        'It is not shown.' in out, out + err)

    # ---- how a sketch may be written, and how the script writes it back
    root = new()
    put(root, lambda s: s.update(flows=[
        {'of': cli + ': main', 'sketch': 'def main(argv):\n\t\tif argv:\n\t\t\treturn entries.add(argv)  # records it\n\n\t\treturn usage()\n'},
        {'of': ent + ': add', 'sketch': ['      async def add(entry):', '        # only words', '        if new(entry):',
                                         '          key = _key(entry, "#1")  # a key', '        return key']},
        {'of': rep + ': monthly', 'sketch': ['  rows = load(month)', {'code': '  for row in rows:', 'calls': []},
                                             {'code': '   total += row', 'says': 'adds it up', 'calls': [rep + ': monthly']}, '  return total']}]))
    code, out, err = run(root)
    wrote = [f.get('sketch') for f in flows_of(root)]
    check('a sketch written as one text, with tabs, is written back one line per line, four spaces a level',
          code == 0 and 'ERROR' not in out and wrote[0] == ['if argv:', '    return entries.add(argv)  # records it', 'return usage()'], out + err + str(wrote[:1]))
    check('a sketch that starts at any depth, indented by any regular step, is written back the same way',
          wrote[1] == ['# only words', 'if new(entry):', '    key = _key(entry, "#1")  # a key', 'return key'], wrote[1:2])
    check('a line that states its calls stays an object, with its code at its depth',
          wrote[2] == ['rows = load(month)', {'code': 'for row in rows:', 'calls': []},
                       {'code': '    total += row', 'says': 'adds it up', 'calls': [rep + ': monthly']}, 'return total'], wrote[2:])
    check('a first line that repeats the def, async or not, is taken out of the sketch, and it is said',
          'note   The flow of main (src/entry/cli/): the first line of its sketch repeated the def.' in out
          and 'note   The flow of add (src/core/entries/): the first line of its sketch repeated the def.' in out and 'The flow of monthly' not in out, out)
    text = read(os.path.join(root, SV + 'system.json'))
    check('system.json keeps a sketch one line per line, however short it is',
          '    { "of": "src/core/entries/: add",\n      "sketch": [\n        "# only words",\n        "if new(entry):",\n'
          '        "    key = _key(entry, \\"#1\\")  # a key",\n        "return key"\n      ] }' in text
          and '        { "code": "for row in rows:", "calls": [] },\n' in text, text[text.find('"flows"'):])
    got = page_data(root)['flows']
    check('a line that is only a comment stays a line, and the words of a line start at the first # outside a string',
          got.get(ADD) == [[0, '# only words', '', []], [0, 'if new(entry):', '', []], [1, 'key = _key(entry, "#1")', 'a key', []], [0, 'return key', '', []]], got.get(ADD))
    check('the page has each line as [level, code, words, calls], and a call to the flow\'s own function is left out',
          got.get(MAIN) == [[0, 'if argv:', '', []], [1, 'return entries.add(argv)', 'records it', [ADD]], [0, 'return usage()', '', []]]
          and got.get(monthly) == [[0, 'rows = load(month)', '', []], [0, 'for row in rows:', '', []], [1, 'total += row', 'adds it up', []], [0, 'return total', '', []]], got)
    code, out, err = run(root)
    check('a second run finds the sketches as it wrote them: nothing is said and nothing changes',
          code == 0 and 'note' not in out and read(os.path.join(root, SV + 'system.json')) == text, out + err)

    # ---- what is wrong with a flow: an error, the page is built, and the flow is not shown
    root = new()
    old = {'name': 'Adding an entry', 'line': 'from the command to the record', 'steps': [
        {'at': cli, 'does': 'reads the command', 'calls': 'main'}, {'at': ent, 'gets': 'the entry', 'does': 'records it', 'calls': 'add'}]}
    for what, change, said, shown in [
            ('of a function its box does not list', lambda s: s['flows'][1].update(of=rep + ': yearly'),
             'The flow of yearly (src/core/reports/) names yearly, which src/core/reports/ does not list. Listed there: monthly. It is not shown.', [MAIN]),
            ('with no line', lambda s: s['flows'][1].update(sketch=[]),
             'The flow of add (src/core/entries/) has no line under "sketch". Write its lines, or take the flow out.', [MAIN]),
            ('with no sketch at all', lambda s: s['flows'][1].pop('sketch'), 'The flow of add (src/core/entries/) has no line under "sketch".', [MAIN]),
            ('still written as steps', lambda s: s['flows'].__setitem__(1, old),
             'The flow "Adding an entry" is written as steps, as flows were before they were code. It is not shown. Write it again as the body of one '
             'listed function: "of": "<box folder>: <function>", then "sketch", its lines.', [MAIN]),
            ('that does not say which function it is the body of', lambda s: s['flows'][1].pop('of'),
             'A flow does not say which function it is the body of. Write "of": "<box folder>: <function>".', [MAIN])]:
        back(root)
        put(root, change)
        os.remove(os.path.join(root, 'WORK/SYSTEM_VIEW.html'))
        code, out, err = run(root)
        built = os.path.exists(os.path.join(root, 'WORK/SYSTEM_VIEW.html'))
        check('a flow %s is an error; the page is built without it' % what,
              code == 1 and 'ERROR  ' + said in out and built and shown_flows(page_data(root)) == shown, out + err)
    back(root)
    put(root, lambda s: s.update(flows=[old]))
    run(root)
    commit(root, 'the flows still as steps')
    put(root, lambda s: s.update(flows=MINI['flows']))
    code, out, err = run(root)
    data = page_data(root)
    check('once a flow is written again as code, a last commit that still has it as steps is no error: the Committed tab has no flow, and the comparison marks each flow whole as added',
          code == 0 and 'ERROR' not in out and shown_flows(data) == [MAIN, ADD] and shown_flows(data, 'committed') == []
          and all(l[4] == 'add' for lid in (MAIN, ADD) for l in data['snap']['cc']['flows'][lid]), out + err)
    back(root)
    put(root, lambda s: s['flows'].append({'of': 'Entries: add', 'sketch': ['return 1']}))
    code, out, err = run(root)
    check('two flows of one function are an error, however each names it; the first is the one shown',
          code == 1 and 'ERROR  The flow of add (src/core/entries/) is written twice. A function has one flow.' in out
          and [l[1] for l in page_data(root)['flows'].get(ADD, [])] == ['key = _key(entry)', 'return _store(entry, key)'], out + err)
    back(root)
    put(root, lambda s: s['flows'][0]['sketch'].append({'code': 'show(total)', 'calls': [rep + ': yearly', ent + ': add']}))
    code, out, err = run(root)
    check('a call stated by hand that names nothing listed is an error that says what is listed',
          code == 1 and 'ERROR  The flow of main (src/entry/cli/): "calls" names yearly, which src/core/reports/ does not list. Listed there: monthly. '
                        'A call is written "<box folder>: <function>".' in out and os.path.exists(os.path.join(root, 'WORK/SYSTEM_VIEW.html')), out + err)
    back(root)
    put(root, lambda s: s['flows'][1].update(sketch=['step_%d()' % i for i in range(40)]))
    code, out, err = run(root, '--check')
    check('a sketch of 40 lines is not said to be long', code == 0 and 'lines long' not in out, out + err)
    put(root, lambda s: s['flows'][1].update(sketch=['step_%d()' % i for i in range(41)]))
    code, out, err = run(root, '--check')
    check('a sketch of more than 40 lines is only said',
          code == 0 and 'note   The flow of add (src/core/entries/) is 41 lines long. A flow is a sketch of the steps an architect would name, not the code.' in out, out + err)

    # ---- --flows prints every flow with the calls found
    back(root)
    code, out, err = run(root, '--check', '--flows')
    check('--flows prints every flow, and beside each line the listed functions found on it',
          code == 0 and '\nThe flow of main (src/entry/cli/):\n  entry = NewEntry(argv)\n  return entries.add(entry)    -> src/core/entries/: add\n' in out
          and '\nThe flow of add (src/core/entries/):\n  key = _key(entry)\n  return _store(entry, key)\n' in out, out + err)
    code, out, err = run(root, '--check')
    check('without --flows no flow is printed', code == 0 and 'The flow of' not in out, out + err)
    put(root, lambda s: s.update(flows=[]))
    code, out, err = run(root, '--check', '--flows')
    check('--flows says so when no flow is written', code == 0 and 'No flow is written.' in out, out + err)

    # ---- an entry states a flow: it replaces the flow of that function
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    stated = {'name': 'Adds are checked', 'line': 'an entry already there is not recorded again', 'files': {ENTRIES_PY: 'looks before it records'},
              'flows': [{'of': 'add', 'sketch': 'if taken(entry):\n\treturn None\nreturn _store(entry, key)'}]}
    entries(root, stated)
    code, out, err = run(root)
    now_add = {'of': ent + ': add', 'sketch': ['if taken(entry):', '    return None', 'return _store(entry, key)']}
    check('a flow an entry states replaces the flow of that function, written in the script\'s layout',
          code == 0 and 'ERROR' not in out and 'Folded the built changes' in out and flows_of(root) == [main_flow, now_add], out + err + str(flows_of(root)))
    check('the entry that states the flow is not told to check it', 'which has a flow' not in out, out)
    data = page_data(root)
    cc = data['snap']['cc']
    check('an entry that states a flow marks that function', cc['hits'] == {'0': [ADD]} and 'src/core/entries/#add' not in cc['lines'], cc['hits'])
    check('Committed → Current gives the flow line by line: a line only the last commit has ends with "del", one only the current state has with "add"',
          cc.get('flows') == {ADD: [[0, 'key = _key(entry)', 'the same entry gets the same key', [], 'del'], [0, 'if taken(entry):', '', [], 'add'],
                                    [1, 'return None', '', [], 'add'], [0, 'return _store(entry, key)', '', []]]}, cc.get('flows'))
    check('the Committed tab has the flow as it was, and the Current tab as it is listed',
          data['snap']['committed'].get('flows') == {ADD: [[0, 'key = _key(entry)', 'the same entry gets the same key', []], [0, 'return _store(entry, key)', '', []]]}
          and 'flows' not in data['snap']['current'] and [l[1] for l in data['flows'][ADD]] == ['if taken(entry):', 'return None', 'return _store(entry, key)'],
          data['snap']['committed'].get('flows'))
    code, out, err = run(root)
    check('a second run changes nothing and folds nothing', code == 0 and 'Folded' not in out and flows_of(root) == [main_flow, now_add] and changes(root) == [stated], out + err)
    git(root, 'checkout', 'HEAD', '--', SV + 'system.json')
    commit(root, 'committed with system.json not folded')
    code, out, err = run(root)
    check('an entry that states a flow stays while system.json at the last commit has the flow as it was',
          code == 0 and 'Took' not in out and changes(root) == [stated] and flows_of(root) == [main_flow, now_add]
          and [data['changes'][i]['name'] for i in page_data(root)['snap']['cc']['changes']] == ['Adds are checked'], out + err)
    commit(root, 'the fold')
    code, out, err = run(root, '--from', 'base')
    data = page_data(root)
    check('and leaves once the last commit holds the flow', code == 0 and 'Took 1 built entry out' in out and changes(root) == []
          and flows_of(root) == [main_flow, now_add] and 'flows' not in data['snap']['cc'], out + err)
    tab = data['snap'].get('from', {})
    check('a delta from an earlier commit still gives the flow line by line, and marks the function for the change',
          [l[4:] for l in (tab.get('flows') or {}).get(ADD, [])] == [['del'], ['add'], ['add'], []]
          and [tab['hits'][str(i)] for i in tab.get('changes', []) if data['changes'][i]['name'] == 'Adds are checked'] == [[ADD]], tab.get('flows'))

    # ---- an entry adds a flow, and takes one out
    root = new()
    redrawn = {'name': 'Flows redrawn', 'line': 'f', 'files': {}, 'flows': [
        {'of': rep + ': monthly', 'sketch': ['return total(month)  # adds up the month']}, {'of': ent + ': add', 'sketch': []}, {'of': 'main'}]}
    entries(root, redrawn)
    code, out, err = run(root)
    data = page_data(root)
    check('an entry adds the flow of a function that had none, and takes a flow out by stating it with no line or with no sketch',
          code == 0 and 'ERROR' not in out and flows_of(root) == [{'of': rep + ': monthly', 'sketch': ['return total(month)  # adds up the month']}], out + err + str(flows_of(root)))
    check('each of those functions is marked for the entry', sorted(data['snap']['cc']['hits']['0']) == sorted([MAIN, ADD, monthly]), data['snap']['cc']['hits'])
    check('the page keeps a flow only one state has: null in the tab of the state that lacks it',
          sorted(data['flows']) == sorted([MAIN, ADD, monthly]) and data['snap']['current'].get('flows') == {MAIN: None, ADD: None}
          and data['snap']['committed'].get('flows') == {monthly: None}, str(data['snap']['current'].get('flows')) + str(data['snap']['committed'].get('flows')))
    commit(root, 'the fold')
    code, out, err = run(root)
    check('an entry that takes a flow out leaves once the last commit no longer has the flow', code == 0 and 'Took 1 built entry out' in out and changes(root) == [], out + err)

    # ---- a function an entry removes takes its flow with it
    root = new()
    edit(root, ENTRIES_PY, 'def add(entry):', 'def record(entry):')
    renamed = {'name': 'Add becomes record', 'line': 'r', 'files': {ENTRIES_PY: 'add is now record'},
               'interface': {ent: ['- add', 'record(entry: NewEntry) → EntryId  // records one entry']}}
    entries(root, renamed)
    code, out, err = run(root)
    check('a function an entry removes takes its flow with it, and the entry is told how to keep the flow if the function was renamed',
          code == 0 and 'note   Add becomes record removed add from src/core/entries/, and its flow with it. If the function was renamed, say so under '
                        '"renames" instead of removing it, and its flow stays.' in out and flows_of(root) == [main_flow], out + err + str(flows_of(root)))
    check('a line that called the function that is gone is said, and shown without the call',
          'note   The flow of main (src/entry/cli/) calls entries.add(), which src/core/entries/ does not list. The line is shown without that call.' in out
          and page_data(root)['flows'][MAIN][1][3] == [], out)
    entries(root, dict(renamed, flows=[{'of': ent + ': record', 'sketch': add_flow['sketch']}]))
    code, out, err = run(root)
    check('stated again under its new name, the flow is back', code == 0 and 'ERROR' not in out
          and flows_of(root) == [main_flow, {'of': ent + ': record', 'sketch': add_flow['sketch']}] and ent + '#record' in page_data(root)['flows'], out + err + str(flows_of(root)))
    back(root)
    edit(root, ENTRIES_PY, 'def add(entry):', 'def record(entry):')
    entries(root, dict(renamed, flows=[{'of': ent + ': record', 'sketch': add_flow['sketch']}]))
    code, out, err = run(root)
    check('the same in one run: the old flow goes with the function, the entry\'s flow of the new one is added',
          code == 0 and 'ERROR' not in out and [f['of'] for f in flows_of(root)] == [cli + ': main', ent + ': record'], out + err + str(flows_of(root)))

    # ---- an entry's flow that names nothing listed
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2\n\n\ndef count():\n    return 0')
    counts = {'name': 'Counts', 'line': 'c', 'files': {ENTRIES_PY: 'counts the entries'}, 'interface': {ent: ['count() → Int  // how many entries']}}
    entries(root, dict(counts, flows=[{'of': ent + ': tally', 'sketch': ['return len(rows)']}]))
    before = read(os.path.join(root, SV + 'system.json'))
    code, out, err = run(root)
    check('an entry whose flow names a function its box does not list is an error, and nothing of the entry is folded',
          code == 1 and 'ERROR  Counts: a flow under "flows" names tally, which src/core/entries/ does not list. Listed there: add, listing, count.' in out
          and 'Nothing was folded from: Counts.' in out and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    entries(root, dict(counts, flows=[{'of': 'Nowhere: count', 'sketch': ['return len(rows)']}]))
    code, out, err = run(root, '--check')
    check('and so is one whose flow names a box that is not there', code == 1 and 'ERROR  Counts: a flow under "flows" names Nowhere, which is not a box.' in out, out + err)
    entries(root, dict(counts, flows=[{'of': ent + ': count', 'sketch': ['return len(listing())  # one for every entry']}]))
    code, out, err = run(root)
    check('an entry may state the flow of a function it brings',
          code == 0 and 'ERROR' not in out and flows_of(root)[2:] == [{'of': ent + ': count', 'sketch': ['return len(listing())  # one for every entry']}]
          and page_data(root)['flows'].get(ent + '#count') == [[0, 'return len(listing())', 'one for every entry', [ent + '#listing']]], out + err + str(flows_of(root)))

    # ---- a planned entry states a flow: only its tab shows it
    root = new()
    before = read(os.path.join(root, SV + 'system.json'))
    yearly = rep + '#yearly'
    entries(root, {'name': 'Adds are checked', 'line': 'a', 'plan': 'Checks', 'files': {ENTRIES_PY: 'looks before it records'},
                   'flows': [{'of': ent + ': add', 'sketch': ['if taken(entry):', '    return None', 'return _store(entry, key)']}]},
            {'name': 'Totals by year', 'line': 'a year at a time', 'plan': 'Checks', 'files': {rep + 'yearly.py': '+ adds up the months'},
             'interface': {rep: ['yearly(year: Int) → Report  // one year']},
             'flows': [{'of': rep + ': yearly', 'sketch': ['for month in months(year):', '    total += monthly(month)  # month by month', 'return total']}]})
    code, out, err = run(root)
    data = page_data(root)
    pl = data['snap'].get('plan:0', {})
    check('a planned entry that states a flow is not folded', code == 0 and 'ERROR' not in out and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    check('the plan tab gives the flow line by line: a line the plan takes out ends with "del", one it adds with "add"',
          (pl.get('flows') or {}).get(ADD) == [[0, 'key = _key(entry)', 'the same entry gets the same key', [], 'del'], [0, 'if taken(entry):', '', [], 'add'],
                                              [1, 'return None', '', [], 'add'], [0, 'return _store(entry, key)', '', []]], pl.get('flows'))
    check('the planned entry marks the function whose flow it states', pl.get('hits', {}).get('0') == [ADD] and yearly in pl.get('hits', {}).get('1', []), pl.get('hits'))
    check('the other tabs have the flow as it is now', [l[1] for l in data['flows'][ADD]] == ['key = _key(entry)', 'return _store(entry, key)']
          and ADD not in (data['snap']['current'].get('flows') or {}) and ADD not in (data['snap']['cc'].get('flows') or {}), data['snap']['cc'].get('flows'))
    check('the flow of a function the plan brings is on the page, with its calls, is null in the tabs before the plan, and is marked whole as added in the plan tab',
          data['flows'].get(yearly) == [[0, 'for month in months(year):', '', []], [1, 'total += monthly(month)', 'month by month', [monthly]], [0, 'return total', '', []]]
          and data['snap']['current'].get('flows') == {yearly: None} and data['snap']['committed'].get('flows') == {yearly: None}
          and data['snap']['cc'].get('flows') == {yearly: None} and set(pl.get('flows') or {}) == {ADD, yearly}
          and [l[4] for l in pl['flows'][yearly]] == ['add'] * 3, str(data['flows'].get(yearly)) + str(data['snap']['current'].get('flows')) + str(pl.get('flows')))

    # ---- a box that goes with its files takes its flows with it
    root = new()
    put(root, lambda s: s['flows'].append({'of': rep + ': monthly', 'sketch': ['return total(month)  # adds up the month']}))
    run(root)
    commit(root, 'a flow of monthly')
    shutil.rmtree(os.path.join(root, rep))
    entries(root, {'name': 'No reports', 'line': 'gone', 'files': {MONTHLY_PY: 'removed'}})
    code, out, err = run(root)
    data = page_data(root)
    check('a box removed because its files are gone takes its flows with it, with no error',
          code == 0 and 'ERROR' not in out and 'The box src/core/reports/ is removed' in out and flows_of(root) == [main_flow, add_flow], out + err + str(flows_of(root)))
    check('the page still has that flow for the Committed tab: it is null in the Current tab',
          monthly in data['flows'] and data['snap']['current'].get('flows') == {monthly: None} and 'flows' not in data['snap']['committed'], data['snap']['current'].get('flows'))


def calls(tmp):
    """The listed functions a line of a sketch calls, in a project whose boxes have names of several words, a box that is
    one file, two boxes one word names, and a listed name with a dot."""
    root = os.path.join(tmp, 'calls')
    box = lambda n, f, *lines: {'name': n, 'folder': f, 'line': 'does ' + n, 'interface': list(lines)}
    cli, wal, archive, order, videos = 'src/entry/cli.py', 'src/core/wal/', 'src/core/archive/', 'src/core/join-order/', 'src/core/videos/'
    sketch = [
        'usage()',
        'flush()',
        'lsn = write_ahead_log.append(record)  # by the box\'s name',
        'wal.flush()  # by the last part of its folder',
        'tree = join_order.order(stmt)',
        'n = youtube.minutes(id) + videos.youtube.minutes(other)',
        'cli.usage()',
        'main(rest)',
        'log("wal.flush() # not a call", x)  # the words',
        'wal.append(a); archive.trim()',
        'wal.trim()',
        'join_order.cost(stmt)',
        {'code': 'join_order.price(stmt)', 'calls': []},
        {'code': 'archive.keep(lsn)', 'says': 'kept', 'calls': [archive + ': trim', 'WAL: trim', 'youtube.minutes', cli + ': main']}]
    figure = {'name': 'Calls', 'regions': {
        'entry': {'folder': 'src/entry/', 'line': 'in', 'boxes': [box('Command line', cli, 'main(argv: [Text])  // runs', 'usage()  // prints the help')]},
        'core': {'folder': 'src/core/', 'line': 'does', 'boxes': [
            box('Write-ahead log', wal, 'append(record: Record) → Lsn  // appends', 'flush()  // flushes', 'trim()  // trims the log'),
            box('WAL', archive, 'trim()  // trims the archive'),
            box('Join order', order, 'order(stmt: Statement) → JoinTree  // orders the joins'),
            box('Videos', videos, 'youtube.minutes(id: Text) → Int  // how long a video is')]}},
        'flows': [{'of': cli + ': main', 'sketch': sketch}]}
    write(root, SV + 'system.json', json.dumps(figure, ensure_ascii=False))
    write(root, SV + 'changes.json', '[]\n')
    for path, text in {cli: 'def main(argv):\n    return usage()\n\n\ndef usage():\n    return 0\n', wal + 'wal.py': 'def append(r):\n    return flush()\n\n\ndef flush():\n    return trim()\n\n\ndef trim():\n    return 0\n',
                       archive + 'archive.py': 'def trim():\n    return 0\n', order + 'order.py': 'def order(stmt):\n    return stmt\n',
                       videos + 'youtube.py': 'def minutes(id):\n    return 0\n'}.items():
        write(root, path, text)
    git(root, 'init', '-q')
    code, out, err = run(root, '--flows')
    got = (page_data(root)['flows'] if code == 0 else {}).get(cli + '#main') or [[0, '', '', None]] * len(sketch)
    found = lambda at: got[at][3]
    said = out.split('\nThe flow of main (src/entry/cli.py):')[0]        # the notes, without what --flows prints after them
    check('calls: the project builds with no error', code == 0 and 'ERROR' not in out and len(got) == len(sketch), out + err)
    check('a call written bare is a function of the flow\'s own box', found(0) == [cli + '#usage'], got[0])
    check('a call written bare is not looked for in another box, and nothing is said', found(1) == [] and 'flush()' not in said, got[1])
    check('a box is called by its name written as an identifier: write_ahead_log', found(2) == [wal + '#append'], got[2])
    check('or by the last part of its folder: wal', found(3) == [wal + '#flush'], got[3])
    check('a folder with a dash is called with an underscore: join_order', found(4) == [order + '#order'], got[4])
    check('a listed name with a dot is found where it is written out in full, with its box before it or not, and once', found(5) == [videos + '#youtube.minutes'], got[5])
    check('a box that is one file is called by the file\'s name without its ending: cli', found(6) == [cli + '#usage'], got[6])
    check('a call to the flow\'s own function is left out', found(7) == [], got[7])
    check('what is inside a string is not a call, and a # there does not start the words',
          got[8] == [0, 'log("wal.flush() # not a call", x)', 'the words', []], got[8])
    check('two calls on one line are both found, in their order; a word two boxes have names the one that lists the function',
          found(9) == [wal + '#append', archive + '#trim'], got[9])
    check('a call two boxes match is said, and the line is shown without it',
          found(10) == [] and 'note   The flow of main (src/entry/cli.py) calls wal.trim(), which src/core/archive/ and src/core/wal/ list. The line is shown without that call.' in out, out)
    check('a call into a box that does not list the function is said, and the line is shown without it',
          found(11) == [] and 'note   The flow of main (src/entry/cli.py) calls join_order.cost(), which src/core/join-order/ does not list. The line is shown without that call.' in out, out)
    check('"calls": [] on a line says it calls nothing listed: nothing is said of it', found(12) == [] and 'join_order.price' not in said and 'join_order.cost' in said, out)
    check('calls stated by hand are taken as stated: by folder, by box name or alone, each once, and never the flow\'s own function',
          got[13] == [0, 'archive.keep(lsn)', 'kept', [archive + '#trim', videos + '#youtube.minutes']] and 'archive.keep' not in said, got[13])
    check('--flows prints each line at its depth with the calls found beside it',
          '\nThe flow of main (src/entry/cli.py):\n  usage()    -> src/entry/cli.py: usage\n  flush()\n  lsn = write_ahead_log.append(record)    -> src/core/wal/: append\n' in out
          and '\n  wal.append(a); archive.trim()    -> src/core/wal/: append, src/core/archive/: trim\n' in out, out)


# ---------------------------------------------------------------- boxes inside boxes: two levels and no more

NEST = 'src/core/entries/'


def nested(tmp, name):
    """Mini with two boxes inside Entries, in one row whose folder is the box's own: the inner boxes sit directly in it.
    Entries lists add as a bare name: the function of the box inside."""
    figure = json.loads(json.dumps(MINI))
    box = figure['regions']['core']['boxes'][0]
    box['interface'] = ['add', 'listing() → [Entry]  // every entry', 'NewEntry = { text: Text }  // an entry not yet recorded']
    box['inside'] = [{'name': 'Parts', 'folder': NEST, 'line': 'what recording an entry takes', 'boxes': [
        {'name': 'Records', 'folder': NEST + 'records/', 'line': 'the entries themselves', 'interface': ['add(entry: NewEntry) → EntryId  // records one entry']},
        {'name': 'Keys', 'folder': NEST + 'keys/', 'line': 'one key per entry', 'interface': ['key(entry: NewEntry) → Key  // the same key on every run']}]}]
    figure['flows'] = [{'of': 'src/entry/cli/: main', 'sketch': ['return entries.add(NewEntry(argv))  # records it']},
                       {'of': NEST + ': add', 'sketch': ['return _store(entry, keys.key(entry))  # under its key']}]
    files = dict(MINI_FILES)
    files[ENTRIES_PY] = 'class NewEntry:\n    pass\n\n\ndef listing():\n    return []\n'
    files[NEST + 'records/records.py'] = 'def add(entry):\n    return _store(entry, key(entry))\n\n\ndef _store(entry, key):\n    return key\n'
    files[NEST + 'keys/keys.py'] = 'def key(entry):\n    return 1\n'
    return mini(tmp, name, figure, files)


def levels(tmp):
    """Boxes go two levels deep: a box of the overview may have boxes inside it, and those have none."""
    records, keys, index = NEST + 'records/', NEST + 'keys/', NEST + 'index/'
    inner = lambda root: [b['folder'] for b in system(root)['regions']['core']['boxes'][0]['inside'][0]['boxes']]

    # ---- a box whose inner boxes sit directly in its own folder
    root = nested(tmp, 'levels-1')
    code, out, err = run(root)
    data = page_data(root)
    view = next((v for v in data['views'] if v['id'] == NEST), {'rows': []})
    check('a box whose one row has the box\'s own folder builds with no error and no note', code == 0 and 'ERROR' not in out and 'note' not in out, out + err)
    check('its view lists the boxes inside it, in that one row',
          [v['id'] for v in data['views']] == ['', NEST] and [(r['dir'], r['title'], [b['folder'] for b in r['boxes']]) for r in view['rows']] == [(NEST, 'Parts', [records, keys])],
          view)
    check('a file directly in the box\'s folder is the box\'s, and one in a box inside is that box\'s',
          'belong' not in out and data['api'].get(records) == [['add(entry: NewEntry) → EntryId', 'records one entry']]
          and data['api'].get(NEST) == [['add(entry: NewEntry) → EntryId', 'records one entry'], ['listing() → [Entry]', 'every entry']], data.get('api'))
    check('a flow of a bare name in a box is the flow of the function of the box inside: the script writes that box\'s folder',
          [f['of'] for f in flows_of(root)] == ['src/entry/cli/: main', records + ': add'] and list(data['flows']) == [MAIN, records + '#add'], flows_of(root))
    check('a call through the outer box is a call of the inner box\'s function, and the inner flow calls its neighbour by name',
          data['flows'][MAIN][0][3] == [records + '#add'] and data['flows'][records + '#add'][0][3] == [keys + '#key'], data['flows'])
    write(root, index + 'index.py', 'def find(x):\n    return x\n')
    found = {'name': 'Index', 'folder': index, 'line': 'finds entries', 'interface': ['find(x: Text) → Entry?  // finds one']}
    entries(root, {'name': 'An index', 'line': 'entries are found by their text', 'files': {index + 'index.py': '+ finds an entry'}, 'boxes': [found]})
    code, out, err = run(root)
    data = page_data(root)
    view = next((v for v in data['views'] if v['id'] == NEST), {'rows': [{'boxes': []}]})
    check('an entry adds a new box inside such a box through "boxes": it goes last in the row',
          code == 0 and 'ERROR' not in out and inner(root) == [records, keys, index] and system(root)['regions']['core']['boxes'][0]['inside'][0]['boxes'][2] == found, out + err)
    check('the page lists the new box in the box\'s view, marked as added, with its line marked as the entry\'s',
          [b['folder'] for b in view['rows'][0]['boxes']] == [records, keys, index] and data['snap']['cc']['boxes'].get(index) == 'add'
          and data['snap']['cc']['hits']['0'] == [index + '#find'], data['snap']['cc']['hits'])

    # ---- a third level is refused
    back(root)
    write(root, index + 'trees/tree.py', 'def find(x):\n    return x\n')
    before = read(os.path.join(root, SV + 'system.json'))
    deep = {'name': 'Index', 'folder': index, 'line': 'finds entries',
            'inside': [{'name': 'Kinds', 'folder': index, 'line': 'the kinds of index', 'boxes': [{'name': 'Trees', 'folder': index + 'trees/', 'line': 'sorted'}]}]}
    entries(root, {'name': 'An index', 'line': 'i', 'files': {index + 'trees/tree.py': '+ a sorted index'}, 'boxes': [deep]})
    code, out, err = run(root)
    check('an entry that would put boxes inside a box that is itself inside a box is an error, and is not folded',
          code == 1 and 'ERROR  An index: The box src/core/entries/index/trees/ is inside src/core/entries/index/, which is itself inside src/core/entries/. '
                        'Boxes go two levels deep and no more' in out and 'Nothing was folded from: An index.' in out
          and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    back(root)
    write(root, 'src/core/tags/names/names.py', 'def tag(x):\n    return x\n')
    tags = {'name': 'Tags', 'folder': 'src/core/tags/', 'line': 'tags',
            'inside': [{'name': 'Parts', 'folder': 'src/core/tags/', 'line': 'p', 'boxes': [{'name': 'Names', 'folder': 'src/core/tags/names/', 'line': 'the names'}]}]}
    entries(root, {'name': 'Tags', 'line': 't', 'files': {'src/core/tags/names/names.py': '+ names of tags'}, 'boxes': [tags]})
    code, out, err = run(root)
    check('a new box of the overview may come with boxes inside it: that is two levels',
          code == 0 and 'ERROR' not in out and system(root)['regions']['core']['boxes'][-1] == tags and 'src/core/tags/' in [v['id'] for v in page_data(root)['views']], out + err)
    back(root)
    before = read(os.path.join(root, SV + 'system.json'))
    put(root, lambda s: s['regions']['core']['boxes'][0]['inside'][0]['boxes'][0].update(
        inside=[{'name': 'Rows', 'folder': records, 'line': 'r', 'boxes': [{'name': 'Rows', 'folder': records + 'rows/', 'line': 'the rows'}]}]))
    written = read(os.path.join(root, SV + 'system.json'))
    code, out, err = run(root)
    check('a system.json with boxes three levels deep stops the script, which says that boxes go two levels deep',
          code == 2 and 'Traceback' not in err and len(err.strip().split('\n')) == 1 and 'two levels deep' in err
          and 'the box src/core/entries/records/ is inside another box and has boxes inside it' in err
          and read(os.path.join(root, SV + 'system.json')) == written != before, out + err)
    back(root)
    put(root, lambda s: s['regions']['core']['boxes'][0]['inside'][0]['boxes'][0].update(inside=[]))
    code, out, err = run(root, '--check')
    check('an empty "inside" on a box inside a box is no third level', code == 0 and 'ERROR' not in out, out + err)


def third(tmp):
    """What the third trial by a fresh agent and the review of the flows found (2026-11-13), one case each."""
    count = [0]

    def new(figure=None, files=None):
        count[0] += 1
        return mini(tmp, 'third-%d' % count[0], figure, files)

    ent, rep, cli, rec = 'src/core/entries/', 'src/core/reports/', 'src/entry/cli/', 'src/core/records/'
    monthly = rep + '#monthly'
    main_flow, add_flow = MINI['flows']
    sketch_of = lambda root, of: next((f['sketch'] for f in flows_of(root) if f['of'] == of), None)

    # ---- a function that only changed its name
    root = new()
    edit(root, ENTRIES_PY, 'def add(entry):', 'def record(entry):')
    code, out, err = run(root, '--check')
    check('with no entry, what is prepared does not put the old name under "affects", and says how a rename is written',
          'add is listed in src/core/entries/ and no function of that name is left in its files. If it was renamed, the entry says "renames": '
          '{ "src/core/entries/: add": "<its new name>" }; if it is gone, "- add" under "interface".' in out and '"affects"' not in out, out + err)
    renamed = {'name': 'Add becomes record', 'line': 'r', 'files': {ENTRIES_PY: 'add is now record'}, 'renames': {ent + ': add': 'record'}}
    entries(root, renamed)
    code, out, err = run(root)
    data = page_data(root)
    check('"renames" gives a listed function its new name: the line keeps its place and its words',
          code == 0 and 'ERROR' not in out and lines_of(root, ent)[0] == 'record(entry: NewEntry) → EntryId  // records one entry', out + err + str(lines_of(root, ent)))
    check('its flow stays, under the new name, and a sketch that called it calls it by the new name',
          flows_of(root) == [{'of': cli + ': main', 'sketch': [main_flow['sketch'][0], 'return entries.record(entry)  # records it']},
                             {'of': ent + ': record', 'sketch': add_flow['sketch']}]
          and data['flows'][MAIN][1][3] == [ent + '#record'], str(flows_of(root)))
    check('nothing is said about a flow lost or to be checked', 'its flow with it' not in out and 'which has a flow' not in out and 'does not list' not in out, out)
    check('the comparison marks the function under both names', set(data['snap']['cc']['hits']['0']) >= {ent + '#record', ADD}, data['snap']['cc']['hits'])
    before = read(os.path.join(root, SV + 'system.json'))
    code, out, err = run(root)
    check('a second run changes nothing', code == 0 and 'ERROR' not in out and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    commit(root, 'renamed')
    code, out, err = run(root)
    check('the entry leaves once the last commit holds the new name', code == 0 and 'Took 1 built entry out' in out and changes(root) == [], out + err)
    back(root)
    entries(root, dict(renamed, files={ENTRIES_PY: 'x'}, renames={ent + ': add': 'listing'}))
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    code, out, err = run(root)
    check('a rename to a name the box already lists is an error', code == 1 and 'ERROR  Add becomes record: add cannot be renamed listing, which src/core/entries/ already lists.' in out, out + err)
    entries(root, dict(renamed, files={ENTRIES_PY: 'x'}, renames={ent + ': nope': 'other'}))
    code, out, err = run(root)
    check('a rename of a function no box lists is an error', code == 1 and 'ERROR  Add becomes record: "renames" names nope, which src/core/entries/ does not list.' in out, out + err)
    entries(root, dict(renamed, renames={ent + ': add': 'not a name'}))
    code, out, err = run(root)
    check('a new name that is not a name stops the script, which says how "renames" is written',
          code == 2 and 'Traceback' not in err and '"renames" an object: "<box folder>: <function>", then its new name' in err, out + err)
    back(root)
    edit(root, ENTRIES_PY, 'def add(entry):', 'def record(entry):')
    entries(root, {'name': 'Add becomes record', 'line': 'r', 'files': {ENTRIES_PY: 'add is now record'},
                   'interface': {ent: ['- add', 'record(entry: NewEntry) → EntryId  // records one entry']},
                   'flows': [{'of': ent + ': record', 'sketch': add_flow['sketch']}]})
    code, out, err = run(root)
    check('an entry that removes a function and states a flow in the same box is not told that the flow went', code == 0 and 'its flow with it' not in out, out + err)

    # ---- what is prepared carries the flow of a function it names
    root = new()
    edit(root, ENTRIES_PY, 'return _store(entry)', 'return _store(entry) or 0')
    code, out, err = run(root, '--check')
    check('with no entry, what is prepared gives the flow of the function it names, ready to edit',
          '  add has a flow. If its steps changed, state it again in the entry, under "flows", whole. As it stands:' in out
          and '"of": "src/core/entries/: add"' in out and '"key = _key(entry)  # the same entry gets the same key"' in out, out + err)

    edit(root, ENTRIES_PY, 'def listing():', 'def count():\n    return 0\n\n\ndef _private():\n    return 0\n\n\ndef listing():')
    code, out, err = run(root, '--check')
    check('and names a function the change brings that the box does not list, leaving private ones out',
          '  New in src/core/entries/entries.py and not listed by src/core/entries/: count. One that another box calls goes under "interface".' in out, out + err)
    back(root)
    edit(root, ENTRIES_PY, 'def add(entry):', 'def record(entry):\n    return add(entry)\n\n\ndef add(entry):')
    entries(root, {'name': 'Flow in two steps', 'plan': 'Steps', 'line': 's', 'files': {ENTRIES_PY: 's'},
                   'flows': [{'of': ent + ': add', 'sketch': ['key = _key(entry)', 'return listing()']}]})
    code, out, err = run(root, '--check', '--flows')
    check('--flows also prints a flow as a plan leaves it, with the calls found',
          'The flow of add (src/core/entries/), as the plan Steps leaves it:' in out and '  return listing()    -> src/core/entries/: listing' in out, out + err)
    back(root)
    code, out, err = run(root, '--seen')
    first = out.strip()
    edit(root, 'docs/readme.md', 'How', 'Now how')
    commit(root, 'a word')
    code, out, err = run(root, '--seen')
    check('--seen says what Seen was', code == 0 and first.startswith('Seen is now ') and '(it was' not in first
          and re.match(r'^Seen is now \w+ \(it was \w+\)\.$', out.strip()), first + out + err)

    # ---- the closing lines
    root = new()
    code, out, err = run(root, '--check')
    check('a check that finds nothing wrong says so', code == 0 and out.strip() == 'Checked: 3 boxes, 2 flows. No error.', out + err)
    entries(root, {'name': 'Yearly', 'plan': 'Totals', 'line': 'y', 'files': {MONTHLY_PY: 'a yearly total'}})
    code, out, err = run(root)
    check('the closing line counts the planned changes', code == 0 and 'Wrote WORK/SYSTEM_VIEW.html: 3 boxes, 2 flows, 1 planned change.' in out, out + err)

    # ---- calls: a listed function handed on without being called
    root = new()
    put(root, lambda s: s.update(flows=[
        {'of': cli + ': main', 'sketch': ['kept = found.where(entries.add)', 'n = entry.text', 'show(reports.monthly, kept)']},
        {'of': ent + ': add', 'sketch': ['old = seen.where(listing)', 'new = seen.where(_fresh)', 'return _store(entry)']}]))
    code, out, err = run(root)
    got = page_data(root)['flows']
    check('box.function handed on without brackets counts as a call; an attribute of a variable does not, and nothing is said',
          code == 0 and 'note' not in out and [l[3] for l in got[MAIN]] == [[ADD], [], [monthly]], out + err + str(got[MAIN]))
    check('the one bare name inside where() is a listed function of the flow\'s own box, or nothing',
          [l[3] for l in got[ADD]] == [[ent + '#listing'], [], []], got[ADD])

    # ---- how a sketch is read
    root = new()
    put(root, lambda s: s.update(flows=[
        {'of': cli + ': main', 'sketch': ['if plan is None:', '    stmt = compile(sql)', '     plan = optimize(stmt)', 'return plan']},
        {'of': ent + ': add', 'sketch': ['def add(entry):', '    def retry():  # tries again when the store is busy', '        return _store(entry)', '    return with_backoff(retry)']},
        {'of': rep + ': monthly', 'sketch': [{'code': 'x = 1  # inline', 'says': 'said', 'calls': []}, {'code': '', 'says': 'only words', 'calls': []},
                                               'for x in xs:', '  if x:', '      y(x)']}]))
    code, out, err = run(root)
    check('one line indented a space too far is one level deeper, and the others keep their depth',
          code == 0 and sketch_of(root, cli + ': main') == ['if plan is None:', '    stmt = compile(sql)', '        plan = optimize(stmt)', 'return plan'], out + err + str(flows_of(root)))
    check('only the def of the flow\'s own function is taken out of a sketch: a function defined inside it stays',
          sketch_of(root, ent + ': add') == ['def retry():  # tries again when the store is busy', '    return _store(entry)', 'return with_backoff(retry)'], sketch_of(root, ent + ': add'))
    check('a line written as an object loses none of its words, and one with words and no code is a comment',
          sketch_of(root, rep + ': monthly') == [{'code': 'x = 1', 'says': 'said; inline', 'calls': []}, {'code': '# only words', 'calls': []},
                                                 'for x in xs:', '    if x:', '        y(x)'], sketch_of(root, rep + ': monthly'))
    before = read(os.path.join(root, SV + 'system.json'))
    code, out, err = run(root)
    check('a second run leaves those sketches as they are', code == 0 and read(os.path.join(root, SV + 'system.json')) == before, out + err)

    # ---- a comparison: a flow only one state has
    root = new()
    edit(root, MONTHLY_PY, 'return total(month)', 'return total(month) + 0')
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    entries(root, {'name': 'Flows move', 'line': 'f', 'files': {MONTHLY_PY: 'm', ENTRIES_PY: 'e'},
                   'flows': [{'of': rep + ': monthly', 'sketch': ['return total(month)  # adds']}, {'of': ent + ': add', 'sketch': []}]})
    code, out, err = run(root)
    cc = page_data(root)['snap']['cc'].get('flows') or {}
    check('a flow only the later state has is marked whole as added, and one only the earlier state has as removed',
          code == 0 and 'ERROR' not in out and [l[4] for l in cc.get(monthly) or []] == ['add'] and [l[4] for l in cc.get(ADD) or []] == ['del', 'del'], out + err + str(cc))

    # ---- two built entries state the same flow
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    first = {'name': 'First', 'line': 'a', 'files': {ENTRIES_PY: 'a'}, 'flows': [{'of': ent + ': add', 'sketch': ['return a()']}]}
    second = {'name': 'Second', 'line': 'b', 'files': {ENTRIES_PY: 'b'}, 'flows': [{'of': 'add', 'sketch': ['return b()']}]}
    entries(root, first, second)
    code, out, err = run(root)
    check('when two built entries state the same flow the later one stands: it is taken out of the earlier entry, which keeps the function under "affects"',
          code == 0 and 'note   "First" and "Second" both state the flow of add. The later one stands, and the flow is taken out of the earlier entry.' in out
          and sketch_of(root, ent + ': add') == ['return b()'] and 'flows' not in changes(root)[0] and changes(root)[0].get('affects') == [ent + ': add'], out + err + str(changes(root)))

    # ---- what an entry states about a flow is checked before it is written
    root = new()
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    before = read(os.path.join(root, SV + 'system.json'))
    entries(root, {'name': 'Drop', 'line': 'd', 'files': {ENTRIES_PY: 'd'}, 'flows': [{'of': ent + ': ad', 'sketch': []}]})
    code, out, err = run(root)
    check('taking out the flow of a function no box lists is an error, not a silence',
          code == 1 and 'ERROR  Drop: a flow under "flows" names ad, which src/core/entries/ does not list.' in out, out + err)
    entries(root, {'name': 'Call', 'line': 'c', 'files': {ENTRIES_PY: 'c'}, 'flows': [{'of': ent + ': add', 'sketch': [{'code': 'x()', 'calls': ['nope: x']}]}]})
    code, out, err = run(root)
    check('a call stated by hand in an entry\'s flow that names nothing is the entry\'s error, and the flow is not folded',
          code == 1 and 'ERROR  Call: the flow of add: "calls" names nope, which is not a box.' in out and 'Nothing was folded from: Call.' in out
          and read(os.path.join(root, SV + 'system.json')) == before, out + err)
    put(root, lambda s: s['flows'][1].update(sketch=[{'code': 'x()', 'calls': ['']}]))
    entries(root)
    code, out, err = run(root)
    check('an empty call stated by hand is said as what it is', code == 1 and '"calls" holds an empty text. A call is written "<box folder>: <function>".' in out, out + err)

    # ---- a box that moves: its flow is not to be checked, its words keep their place, an earlier entry follows
    root = new()
    write(root, SV + 'lines.json', json.dumps({'src/core/': 'the core', ent: 'the entries', rep: 'the reports'}))
    run(root)
    commit(root, 'a few words')
    edit(root, ENTRIES_PY, 'return 1', 'return 2')
    earlier = {'name': 'Faster keys', 'line': 'k', 'files': {ENTRIES_PY: 'a faster key'}, 'affects': [ent + ': add'],
               'interface': {ent: ['count() → Int  // how many entries']},
               'flows': [{'of': cli + ': main', 'sketch': ['entry = NewEntry(argv)', {'code': 'return record(entry)', 'calls': [ent + ': add']}]}]}
    entries(root, earlier)
    code, out, err = run(root)
    git(root, 'mv', 'src/core/entries', 'src/core/records')
    write(root, 'src/core/tags/tags.py', 'def tag(x):\n    return x\n')
    entries(root, dict(earlier, files={rec + 'entries.py': 'a faster key'}),
            {'name': 'Entries become records', 'line': 'r', 'files': {rec + 'entries.py': 'moved', 'src/core/tags/tags.py': '+ tags'}, 'moves': {ent: rec}})
    code, out, err = run(root)
    check('a box that only moved does not ask for its flow to be checked', code == 0 and '"Entries become records" changes add' not in out, out + err)
    check('the words of the moved folder keep their place in lines.json',
          list(json.loads(read(os.path.join(root, SV + 'lines.json')))) == ['src/core/', rec, rep], read(os.path.join(root, SV + 'lines.json')))
    check('a new folder with no words, beside folders that have some, is said',
          'note   The new folder src/core/tags/ has no words in WORK/SYSTEM_VIEW/lines.json.' in out and 'The new folder src/core/records/' not in out, out)
    code, out, err = run(root)
    first = changes(root)[0]
    check('on the next run an earlier entry that named the box at its old path is corrected to the new one, and that is said',
          code == 0 and 'ERROR' not in out and 'note   "Faster keys" named the box src/core/entries/, which "Entries become records" has since moved to src/core/records/.' in out
          and list(first['interface']) == [rec] and first['affects'] == [rec + ': add'] and first['flows'][0]['sketch'][1]['calls'] == [rec + ': add'], out + err + str(first))
    check('and system.json has the stated call at the new path', sketch_of(root, cli + ': main')[1]['calls'] == [rec + ': add'], sketch_of(root, cli + ': main'))
    code, out, err = run(root)
    check('the run after that has nothing more to correct', code == 0 and 'ERROR' not in out and 'named the box' not in out, out + err)

    # ---- a box inside another moves within its row
    root = nested(tmp, 'third-nested')
    git(root, 'mv', NEST + 'keys', NEST + 'hashes')
    entries(root, {'name': 'Keys become hashes', 'line': 'h', 'files': {NEST + 'hashes/keys.py': 'moved'}, 'moves': {NEST + 'keys/': NEST + 'hashes/'}})
    code, out, err = run(root)
    check('a box inside another may move within its row', code == 0 and 'ERROR' not in out
          and [b['folder'] for b in system(root)['regions']['core']['boxes'][0]['inside'][0]['boxes']] == [NEST + 'records/', NEST + 'hashes/'], out + err)

    # ---- a plan may not add a third level either
    back(root)
    index = NEST + 'index/'
    deep = {'name': 'Index', 'folder': index, 'line': 'finds entries',
            'inside': [{'name': 'Kinds', 'folder': index, 'line': 'the kinds of index', 'boxes': [{'name': 'Trees', 'folder': index + 'trees/', 'line': 'sorted'}]}]}
    entries(root, {'name': 'An index', 'plan': 'Finding', 'line': 'i', 'files': {index + 'trees/tree.py': '+ a sorted index'}, 'boxes': [deep]})
    code, out, err = run(root)
    check('a planned entry that would put boxes three levels deep is an error',
          code == 1 and 'ERROR  The plan Finding: The box src/core/entries/index/trees/ is inside src/core/entries/index/, which is itself inside src/core/entries/. '
                        'Boxes go two levels deep and no more' in out, out + err)

    # ---- names and folders that are not plain ASCII words
    figure = json.loads(json.dumps(MINI))
    figure['regions']['core']['boxes'].append({'name': 'C sharp', 'folder': 'src/core/c#/', 'line': 'the bindings', 'interface': ['build(x: Text) → Text  // builds one']})
    figure['regions']['core']['boxes'][0]['interface'].append('écrire(entrée: NewEntry) → EntryId  // records one, in French')
    figure['flows'] = [{'of': 'src/core/c#/: build', 'sketch': ['return entries.écrire(x)  # records it']},
                       {'of': ent + ': écrire', 'sketch': ['return add(entrée)']}]
    files = dict(MINI_FILES)
    files['src/core/c#/build.py'] = 'def build(x):\n    return x\n'
    files[ENTRIES_PY] += '\n\ndef écrire(entrée):\n    return add(entrée)\n'
    root = new(figure, files)
    code, out, err = run(root)
    data = page_data(root)
    check('a folder with a # in it keeps its flow: "of" is written back as it was',
          code == 0 and 'ERROR' not in out and [f['of'] for f in flows_of(root)] == ['src/core/c#/: build', ent + ': écrire'] and 'src/core/c#/#build' in data['flows'], out + err + str(flows_of(root)))
    check('a function whose name has letters beyond ASCII is called and found like any other',
          data['flows']['src/core/c#/#build'][0][3] == [ent + '#écrire'] and data['flows'][ent + '#écrire'][0][3] == [ADD], data['flows'])


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
        flows(tmp)
        calls(tmp)
        levels(tmp)
        third(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\nResult: %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
