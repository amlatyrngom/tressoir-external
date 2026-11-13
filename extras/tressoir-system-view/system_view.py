#!/usr/bin/env python3
"""Builds WORK/SYSTEM_VIEW.html, the system view of a project.

    system_view.py            fold the built changes into system.json, print the checks, write the page
    system_view.py --check    print the checks and write nothing
    system_view.py --seen     move Seen to the last commit (done when a planned task starts)
    system_view.py --from C   also show a delta that starts at commit C

It reads WORK/SYSTEM_VIEW/system.json (the architecture, written with the project's owner),
changes.json (one entry per named change, written by the agent for every task), lines.json (a few
words per file) and seen (one commit). The files say what is true and never what changed: every
mark on the page comes from comparing git, system.json at an earlier commit, and the planned
entries. Standard library and the git command only.
"""
import argparse
import copy
import datetime
import html
import json
import os
import re
import subprocess
import sys

REGIONS = ['entry', 'core', 'external', 'platform', 'separate']
SLOT = {'entry': 'entry', 'core': 'core', 'external': 'ext', 'platform': 'plat'}
TITLE = {'entry': 'Entry points', 'core': 'Core application', 'external': 'External services',
         'platform': 'Platform-<br>specific'}
INNER_SLOTS = ['entry', 'core', 'ext', 'plat']
HEAD_KEYS = ['name', 'folder', 'line', 'plan', 'shared']
# left out of the file view: the harness's links to the skills
LINK_FOLDERS = ['.claude/skills/', '.agents/skills/']


class Stop(Exception):
    """Something the script cannot work around; the message is for the reader."""


# ---------------------------------------------------------------- reading the files

PLAIN = [
    ("Expecting ',' delimiter", 'a comma is missing just before this point'),
    ("Expecting ':' delimiter", 'a colon is missing after a name'),
    ('Expecting property name enclosed in double quotes',
     'a name in double quotes is expected here; often there is one comma too many just before'),
    ('Expecting value', 'a value is expected here; often there is one comma too many, or a quote is missing'),
    ('Extra data', 'there is text after the end of the file'),
    ('Unterminated string', 'a string is not closed'),
    ('Invalid control character', 'a line break or a tab sits inside a string'),
    ('Invalid \\escape', 'a backslash is followed by something that is not allowed'),
]


def read_json(path, default, shown):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        text = f.read()
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        words = next((w for k, w in PLAIN if e.msg.startswith(k)), e.msg)
        raise Stop('%s cannot be read. Line %d, column %d: %s.' % (shown, e.lineno, e.colno, words))


def parse_json_text(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- git

class Git:
    def __init__(self, root, hidden):
        self.root = root
        self.hidden = hidden            # path prefixes left out of the file view
        self.ok = self._run('rev-parse', '--is-inside-work-tree')[1].strip() == 'true'
        self.head = self.commit('HEAD') if self.ok else None

    def _run(self, *args):
        try:
            p = subprocess.run(['git'] + list(args), cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            return 1, ''
        return p.returncode, p.stdout.decode('utf-8', 'replace')

    def commit(self, name):
        code, out = self._run('rev-parse', '--verify', '-q', name + '^{commit}')
        return out.strip() if code == 0 and out.strip() else None

    def keep(self, paths):
        return [p for p in paths if p and not any(p.startswith(h) for h in self.hidden)]

    def files_at(self, commit):
        return set(self.keep(self._run('ls-tree', '-r', '--name-only', '-z', commit)[1].split('\0')))

    def files_now(self):
        there = self._run('ls-files', '-z', '--cached', '--others', '--exclude-standard')[1].split('\0')
        gone = set(self._run('ls-files', '-z', '--deleted')[1].split('\0'))
        return set(self.keep(p for p in there if p not in gone))

    def show(self, commit, path):
        code, out = self._run('show', '%s:./%s' % (commit, path))
        return out if code == 0 else None

    def changed_since(self, commit):
        """{path: add | chg | del} between a commit and the working tree, untracked files included."""
        out = self._run('diff', '--name-status', '--no-renames', '--relative', '-z', commit)[1].split('\0')
        st = {}
        for i in range(0, len(out) - 1, 2):
            st[out[i + 1]] = {'A': 'add', 'D': 'del'}.get(out[i][:1], 'chg')
        for p in self._run('ls-files', '-z', '--others', '--exclude-standard')[1].split('\0'):
            if p:
                st[p] = 'add'
        return {p: s for p, s in st.items() if self.keep([p])}

    def commits_between(self, older, newer='HEAD'):
        return [c for c in self._run('rev-list', '--reverse', '%s..%s' % (older, newer))[1].split('\n') if c]

    def short(self, commit):
        return self._run('rev-parse', '--short', commit)[1].strip() or commit[:7]


# ---------------------------------------------------------------- interface lines

def tidy(code):
    """One spelling for the same line: an arrow is →, and one space separates words."""
    return re.sub(r'\s+', ' ', code.replace('->', '→')).strip()


def parse_line(text):
    code, _, words = text.partition('  // ')
    if not _ and ' // ' in text:
        code, _, words = text.partition(' // ')
    code, words = tidy(code), words.strip()
    t = re.match(r'^([A-Za-z_]\w*) = (.*)$', code)
    if t:
        return {'type': True, 'name': t.group(1), 'sig': t.group(2), 'words': words, 'bare': False}
    m = re.match(r'^[\w.]+', code)
    name = m.group(0) if m else code
    return {'type': False, 'name': name, 'sig': code, 'words': words, 'bare': code == name}


def write_line(p):
    return (p['name'] + ' = ' if p['type'] else '') + p['sig'] + ('  // ' + p['words'] if p['words'] else '')


def under(prefix, path):
    """Whether a path is this path, or lies under this folder."""
    return path == prefix or path.startswith(prefix if prefix.endswith('/') else prefix + '/')


# ---------------------------------------------------------------- one state of the system

def rows_of(system):
    """Every row of boxes, outermost first: the five regions, then the rows inside boxes."""
    regions = system.get('regions') or {}
    out = []

    def inside(box):
        for row in box.get('inside') or []:
            out.append((row, box, None))
            for b in row.get('boxes') or []:
                inside(b)

    for key in REGIONS:
        row = regions.get(key)
        if row is None:
            continue
        out.append((row, None, key))
        for b in row.get('boxes') or []:
            inside(b)
    return out


class World:
    """system.json as it is in one state, with what the page needs looked up."""

    def __init__(self, system, problems=None):
        self.sys = system
        self.boxes = {}        # folder -> box
        self.parent = {}       # folder -> the folder of the box it is inside, or None
        self.lines = {}        # id -> {name, sig, words, type, home, alias}
        self.order = {}        # folder -> ids of its lines, in order
        for row, parent, _key in rows_of(system):
            for b in row.get('boxes') or []:
                self.boxes[b['folder']] = b
                self.parent[b['folder']] = parent['folder'] if parent else None
        bare = []
        for folder, b in self.boxes.items():
            self.order[folder] = []
            for text in b.get('interface') or []:
                p = parse_line(text)
                p['home'], p['alias'] = folder, None
                lid = p['name'] if p['type'] else folder + '#' + p['name']
                if lid in self.lines and problems is not None:
                    where = self.lines[lid]['home']
                    problems.error('%s is written twice: %s.' % (p['name'], 'in ' + where if where == folder else 'in %s and in %s' % (where, folder)))
                self.lines[lid] = p
                self.order[folder].append(lid)
                if p['bare']:
                    bare.append(lid)
        # a bare name is the function of that name from a box inside: the same line
        for lid in bare:
            p = self.lines[lid]
            inner = [i for i, q in self.lines.items() if not q['type'] and not q['bare'] and q['name'] == p['name']
                     and q['home'] != p['home'] and under(p['home'], q['home'])]
            if len(inner) == 1:
                p['alias'], p['sig'] = inner[0], self.lines[inner[0]]['sig']
                p['words'] = p['words'] or self.lines[inner[0]]['words']
            elif problems is not None:
                problems.error('%s in %s is a bare name, and %s inside it lists a function of that name.'
                               % (p['name'], p['home'], 'no box' if not inner else 'more than one box'))

    def paths(self, folder):
        return [folder] + list(self.boxes[folder].get('also') or [])

    def holds(self, folder, path):
        return any(under(p, path) for p in self.paths(folder))

    def box_of(self, path):
        """The box a file belongs to: the one with the longest matching path."""
        best, size = None, -1
        for folder in self.boxes:
            for p in self.paths(folder):
                if under(p, path) and len(p) > size:
                    best, size = folder, len(p)
        return best

    def around(self, folder):
        out = []
        while folder is not None:
            out.append(folder)
            folder = self.parent.get(folder)
        return out

    def row_for(self, folder):
        """The row a new box belongs in: the row or region whose folder most closely contains it."""
        best, size = None, -1
        for row, _parent, _key in rows_of(self.sys):
            f = row.get('folder')
            if f and folder != f and under(f, folder) and len(f) > size:
                best, size = row, len(f)
        return best


# ---------------------------------------------------------------- folding

def merge_lines(box, lines):
    """An entry restates a line: it replaces the line of that name, or is added last. `- name` removes one."""
    iface = list(box.get('interface') or [])
    said = []
    for text in lines:
        if text.startswith('- '):
            name = text[2:].strip()
            kept = [x for x in iface if parse_line(x)['name'] != name]
            if len(kept) != len(iface):
                said.append('removed %s from %s' % (name, box['folder']))
            iface = kept
            continue
        p = parse_line(text)
        at = next((i for i, x in enumerate(iface) if parse_line(x)['name'] == p['name']), -1)
        if at < 0:
            iface.append(write_line(p))
            continue
        old = parse_line(iface[at])
        if not p['words']:
            p['words'] = old['words']
        new = write_line(p)
        if new != write_line(old):
            said.append((old, p))
        iface[at] = new
    if iface or 'interface' in box:
        box['interface'] = iface
    return said


def fold(system, entries, problems, quiet=False):
    """system.json with these entries' boxes and lines written in. The entries keep them."""
    out = copy.deepcopy(system)
    for e in entries:
        world = World(out)
        for b in e.get('boxes') or []:
            folder = b.get('folder')
            if not folder:
                problems.error('%s: a box under "boxes" has no folder.' % e.get('name', '?'))
                continue
            old = world.boxes.get(folder)
            if old is None:
                row = world.row_for(folder)
                if row is None:
                    problems.error('%s: the new box %s is in no row and no region. A new row or region is architecture: '
                                   'leave the figure alone and tell the owner.' % (e.get('name', '?'), folder))
                    continue
                new = copy.deepcopy(b)
                if new.get('interface'):
                    new['interface'] = [write_line(parse_line(x)) for x in new['interface']]
                row.setdefault('boxes', []).append(new)
                world = World(out)
                continue
            for k, v in b.items():
                if k == 'folder':
                    continue
                if k == 'also':
                    old['also'] = list(old.get('also') or []) + [p for p in v if p not in (old.get('also') or [])]
                elif k == 'interface':
                    merge_lines(old, v)
                else:
                    old[k] = copy.deepcopy(v)
        for folder, lines in (e.get('interface') or {}).items():
            box = World(out).boxes.get(folder)
            if box is None:
                problems.error('%s: "interface" names %s, which is not a box.' % (e.get('name', '?'), folder))
                continue
            for was in merge_lines(box, lines):
                if not quiet and not isinstance(was, str) and not e.get('plan'):
                    problems.note('%s replaced a line of %s. It was: %s. It is: %s.'
                                  % (e.get('name', '?'), folder, write_line(was[0]), write_line(was[1])))
    return out


def drop_removed(system, had, has):
    """A box whose files all existed before and are all gone is removed."""
    world = World(system)
    gone = [f for f in world.boxes
            if any(world.holds(f, p) for p in had) and not any(world.holds(f, p) for p in has)]
    if not gone:
        return system, []
    out = copy.deepcopy(system)
    for row, _parent, _key in rows_of(out):
        row['boxes'] = [b for b in row.get('boxes') or [] if b['folder'] not in gone]
    return out, gone


def pretty(v, ind='', width=150):
    """Compact, readable JSON: what fits on one line stays on one line. The script is the only formatter of system.json."""
    js = lambda x: json.dumps(x, ensure_ascii=False)
    if not isinstance(v, (dict, list)):
        return js(v)
    kids = lambda x: list(x.values()) if isinstance(x, dict) else list(x)

    def flat(x):
        if not isinstance(x, (dict, list)):
            return js(x)
        if isinstance(x, list):
            return '[' + ', '.join(flat(y) for y in x) + ']'
        return '{ ' + ', '.join(js(k) + ': ' + flat(y) for k, y in x.items()) + ' }'

    n, one = ind + '  ', flat(v)
    deep = any(isinstance(x, (dict, list)) and any(isinstance(y, (dict, list)) for y in kids(x)) for x in kids(v))
    if isinstance(v, list):
        if not deep and len(ind) + len(one) <= width:
            return one
        return '[\n' + ',\n'.join(n + pretty(x, n, width) for x in v) + '\n' + ind + ']'
    head = [(k, x) for k, x in v.items() if k in HEAD_KEYS]
    rest = [(k, x) for k, x in v.items() if k not in HEAD_KEYS]
    if not rest or (not head and not deep and len(ind) + len(one) <= width):
        return one
    hl = ', '.join(js(k) + ': ' + js(x) for k, x in head)
    rl = ',\n'.join(n + js(k) + ': ' + pretty(x, n, width) for k, x in rest)
    return '{ ' + hl + ',\n' + rl + ' }' if head else '{\n' + rl + '\n' + ind + '}'


# ---------------------------------------------------------------- what the checks say

class Problems:
    def __init__(self):
        self.errors, self.notes = [], []

    def error(self, text):
        if text not in self.errors:
            self.errors.append(text)

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)


# ---------------------------------------------------------------- the lines a change is placed on

def note_of(text):
    return re.sub(r'^[+-] ', '', text)


def hits_of(entry, world, problems=None):
    """The listed lines a change marks: the names under `affects`, the lines it states, and the lines of a box it brings.
    A name is looked up in the boxes the entry's files belong to and the boxes around them."""
    name = entry.get('name', '?')
    near = []
    for p in entry.get('files') or {}:
        for f in world.around(world.box_of(p)):
            if f not in near:
                near.append(f)
    for b in entry.get('boxes') or []:
        if b.get('folder') in world.boxes and b['folder'] not in near:
            near.append(b['folder'])
    hit = []
    for said in entry.get('affects') or []:
        where, _, n = said.rpartition(': ')
        boxes = [where] if where else near
        ids = [f + '#' + n for f in boxes if f + '#' + n in world.lines]
        if n in world.lines and world.lines[n]['type']:
            ids.append(n)
        same = set(world.lines[i]['alias'] or i for i in ids)
        if len(same) == 1:
            hit.extend(ids)
        elif problems is not None:
            if not same:
                problems.error('%s: "affects" names %s, which no box around its files lists. Listed there: %s.'
                               % (name, n, ', '.join(sorted(set(world.lines[i]['name'] for f in near for i in world.order.get(f, [])))) or 'nothing'))
            else:
                problems.error('%s: "affects" names %s, which %s list. Write it as "<box folder>: %s".'
                               % (name, n, ' and '.join(sorted(set(i.split('#')[0] for i in ids))), n))
    for folder, lines in (entry.get('interface') or {}).items():
        for text in lines:
            p = parse_line(text[2:] if text.startswith('- ') else text)
            hit.append(p['name'] if p['type'] else folder + '#' + p['name'])

    def brought(box):
        for text in box.get('interface') or []:
            p = parse_line(text)
            hit.append(p['name'] if p['type'] else box['folder'] + '#' + p['name'])
        for row in box.get('inside') or []:
            for b in row.get('boxes') or []:
                brought(b)

    for b in entry.get('boxes') or []:
        if b.get('folder'):
            brought(b)
    # a box that lists a function of a box inside it shows the same line
    out = []
    for i in hit:
        target = world.lines[i]['alias'] or i if i in world.lines else i
        for j in [i, target] + [k for k, q in world.lines.items() if q['alias'] == target]:
            if j not in out:
                out.append(j)
    return out


# ---------------------------------------------------------------- everything the page lists, across every state

class Lists:
    """The boxes and lines of every state shown, in one order: the current state's, with what only another state has put in beside it."""

    def __init__(self, first):
        self.sys = copy.deepcopy(first.sys)
        self.order = {f: list(ids) for f, ids in first.order.items()}
        self.lines = {i: dict(p) for i, p in first.lines.items()}

    def add(self, world):
        mine = World(self.sys)
        for row, parent, key in rows_of(world.sys):
            target = self._row(row, parent, key)
            if target is None:
                continue
            before = None
            for b in row.get('boxes') or []:
                if b['folder'] in mine.boxes:
                    before = b['folder']
                    continue
                boxes = target.setdefault('boxes', [])
                at = next((i + 1 for i, x in enumerate(boxes) if x['folder'] == before), len(boxes) if before else 0)
                new = copy.deepcopy(b)
                boxes.insert(at, new)
                before = b['folder']
                mine = World(self.sys)
        for folder, ids in world.order.items():
            have = self.order.setdefault(folder, [])
            before = None
            for i in ids:
                if i in self.lines:
                    if i in have:
                        before = i
                    continue
                self.lines[i] = dict(world.lines[i])
                have.insert(have.index(before) + 1 if before in have else (len(have) if before else 0), i)
                before = i

    def _row(self, row, parent, key):
        if key:
            return (self.sys.setdefault('regions', {})).setdefault(key, {'boxes': []})
        box = World(self.sys).boxes.get(parent['folder'])
        if box is None:
            return None
        for r in box.setdefault('inside', []):
            if r.get('folder') == row.get('folder'):
                return r
        new = {k: v for k, v in row.items() if k != 'boxes'}
        new['boxes'] = []
        box['inside'].append(new)
        return new


# ---------------------------------------------------------------- snapshots: what a tab shows

def state_snap(lists, world, files, all_files):
    listed = World(lists.sys)
    snap = {'files': {p: None for p in all_files if p not in files},
            'boxes': {f: None for f in listed.boxes if f not in world.boxes}, 'lines': {}}
    for i, d in lists.lines.items():
        w = world.lines.get(i)
        if w is None:
            snap['lines'][i] = None
        else:
            e = {}
            if w['sig'] != d['sig']:
                e['sig'] = w['sig']
            if w['words'] != d['words']:
                e['line'] = w['words']
            if e:
                snap['lines'][i] = e
    return snap


def delta_snap(lists, a, b, a_files, b_files, changed, all_files):
    """From state a to state b. `changed` is {path: add | chg | del}."""
    listed = World(lists.sys)
    snap = {'files': {}, 'boxes': {}, 'lines': {}}
    for p in all_files:
        if p in changed:
            snap['files'][p] = changed[p]
        elif p not in a_files and p not in b_files:
            snap['files'][p] = None
    for f in listed.boxes:
        ina, inb = f in a.boxes, f in b.boxes
        if not ina and not inb:
            snap['boxes'][f] = None
        elif not ina:
            snap['boxes'][f] = 'add'
        elif not inb:
            snap['boxes'][f] = 'del'
        elif any(b.holds(f, p) for p in changed):
            snap['boxes'][f] = 'chg'
    for i, d in lists.lines.items():
        x, y = a.lines.get(i), b.lines.get(i)
        if x is None and y is None:
            snap['lines'][i] = None
            continue
        now = y or x
        e = {}
        if y is None:
            e['s'] = 'del'
        elif x is None:
            e['s'] = 'add'
        elif x['sig'] != y['sig']:
            e['s'], e['was'] = 'chg', x['sig']
        if now['sig'] != d['sig']:
            e['sig'] = now['sig']
        if now['words'] != d['words']:
            e['line'] = now['words']
        if e:
            snap['lines'][i] = e
    return snap


# ---------------------------------------------------------------- the page's lists

def emit_box(b):
    out = {'name': b.get('name', b['folder']), 'folder': b['folder'], 'line': b.get('line', '')}
    if b.get('shared'):
        out['shared'] = True
    return out


def emit_views(system):
    regions = system.get('regions') or {}
    drawn = [k for k in ('entry', 'core', 'external') if (regions.get(k) or {}).get('boxes')]

    def region(k):
        r = regions[k]
        return {'slot': SLOT[k], 'title': TITLE[k], 'dir': r.get('folder', ''), 'line': r.get('line', ''),
                'boxes': [emit_box(b) for b in r.get('boxes') or []]}

    over = {'id': '', 'name': 'Overview', 'line': 'the whole system', 'rows': [region(k) for k in drawn],
            'sep': [emit_box(b) for b in (regions.get('separate') or {}).get('boxes') or []]}
    if (regions.get('platform') or {}).get('boxes'):
        over['band'] = region('platform')
    ends = set(r['dir'] for r in over['rows'] + ([over['band']] if 'band' in over else []))
    over['links'] = [l for l in system.get('links') or [] if l.get('from') in ends and l.get('to') in ends]
    views = [over]
    for row, _parent, _key in rows_of(system):
        for b in row.get('boxes') or []:
            if not b.get('inside'):
                continue
            v = {'id': b['folder'], 'rows': [], 'links': b.get('links') or []}
            for i, r in enumerate(b['inside']):
                v['rows'].append({'slot': INNER_SLOTS[i % len(INNER_SLOTS)], 'title': r.get('name', ''), 'dir': r.get('folder', ''),
                                  'line': r.get('line', ''), 'boxes': [emit_box(x) for x in r.get('boxes') or []]})
            for k in ('from', 'uses'):
                if b.get(k):
                    v[k] = b[k]
            views.append(v)
    return views


def emit_flows(system):
    out = []
    for f in system.get('flows') or []:
        steps = []
        for s in f.get('steps') or []:
            steps.append([s.get('at', ''), s.get('gets', ''), s.get('does', '')] + ([s['calls']] if s.get('calls') else []))
        out.append({'name': f.get('name', ''), 'line': f.get('line', ''), 'steps': steps})
    return out


# ---------------------------------------------------------------- the build

def find_work(start, given):
    if given:
        work = os.path.abspath(given)
        if not os.path.isdir(work):
            raise Stop('There is no folder %s.' % given)
        return os.path.dirname(work), work
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, 'WORK')):
            return d, os.path.join(d, 'WORK')
        up = os.path.dirname(d)
        if up == d:
            raise Stop('No WORK/ folder here or above. Run this inside a project that has the starter kit, or name the folder with --work.')
        d = up


def build(args):
    root, work = find_work(os.getcwd(), args.work)
    name = os.path.basename(work)
    here = os.path.join(work, 'SYSTEM_VIEW')
    shown = lambda f: '%s/SYSTEM_VIEW/%s' % (name, f)
    if not os.path.isdir(here):
        raise Stop('There is no %s/SYSTEM_VIEW/ folder. Install the extra with install.sh --experimental-system-view.' % name)
    git = Git(root, [name + '/'] + LINK_FOLDERS + ['.git/'])

    if args.seen:
        if not git.head:
            raise Stop('There is no commit yet, so Seen has nothing to point at.')
        with open(os.path.join(here, 'seen'), 'w', encoding='utf-8') as f:
            f.write(git.head + '\n')
        print('Seen is now %s.' % git.short(git.head))
        return 0

    system = read_json(os.path.join(here, 'system.json'), {}, shown('system.json'))
    entries = read_json(os.path.join(here, 'changes.json'), [], shown('changes.json'))
    words = read_json(os.path.join(here, 'lines.json'), {}, shown('lines.json'))
    if not isinstance(system, dict) or not isinstance(entries, list) or not isinstance(words, dict):
        raise Stop('system.json must hold an object, changes.json a list, and lines.json an object.')
    problems = Problems()
    built = [e for e in entries if not e.get('plan')]
    plans = []
    for e in entries:
        if e.get('plan') and e['plan'] not in plans:
            plans.append(e['plan'])

    # ---- the states: the last commit, now, and each plan
    now_files = git.files_now() if git.ok else set(scan(root, git.hidden))
    head_files = git.files_at(git.head) if git.head else None
    changed = git.changed_since(git.head) if git.head else {}
    folded = fold(system, built, problems)
    if head_files is not None:
        folded, gone = drop_removed(folded, head_files, now_files)
        for f in gone:
            problems.note('The box %s is removed: every file it had at the last commit is gone.' % f)
    current = World(folded, problems)
    for e in built:
        hits_of(e, current, problems)
    text = pretty(folded) + '\n'
    path = os.path.join(here, 'system.json')
    before = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if text != before and not problems.errors and not args.check and system:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        print('Folded the built changes into %s.' % shown('system.json'))

    def at_commit(commit):
        raw = git.show(commit, '%s/SYSTEM_VIEW/system.json' % name)
        old = parse_json_text(raw) if raw else None
        return World(old) if isinstance(old, dict) and old else None

    committed = at_commit(git.head) if git.head else None
    if git.head and committed is None:
        committed = current
        problems.note('The last commit has no %s, so nothing in the figure or the listing is marked as new.' % shown('system.json'))

    plan_worlds = []
    for pl in plans:
        mine = [e for e in entries if e.get('plan') == pl]
        files = dict(changed_by_plan(mine, now_files, problems))
        after = (now_files | set(p for p, s in files.items() if s == 'add')) - set(p for p, s in files.items() if s == 'del')
        psys, _gone = drop_removed(fold(folded, mine, problems, quiet=True), now_files, after)
        plan_worlds.append((pl, mine, World(psys), files, after))

    # ---- starting points other than the last commit
    starts = []
    seen_path = os.path.join(here, 'seen')
    seen = open(seen_path, encoding='utf-8').read().strip() if os.path.exists(seen_path) else ''
    if seen and git.head:
        c = git.commit(seen)
        if c is None:
            problems.note('Seen names %s, which is not a commit here; the Seen tab is left out.' % seen[:12])
        elif c != git.head:
            starts.append(('seen', 'Seen → Current', c))
    if args.start and git.head:
        c = git.commit(args.start)
        if c is None:
            raise Stop('%s is not a commit here.' % args.start)
        if c != git.head:
            starts.append(('from', '%s → Current' % git.short(c), c))

    # ---- one set of lists for every tab
    lists = Lists(current)
    for _pl, _mine, w, _files, _after in plan_worlds:
        lists.add(w)
    if committed is not None:
        lists.add(committed)
    start_worlds = []
    for tab, label, c in starts:
        w = at_commit(c) or committed or current
        lists.add(w)
        start_worlds.append((tab, label, c, w, git.files_at(c), git.changed_since(c)))
    all_files = set(now_files)
    if head_files is not None:
        all_files |= head_files
    for _pl, _mine, _w, files, after in plan_worlds:
        all_files |= after
    for _tab, _label, _c, _w, files, _ch in start_worlds:
        all_files |= files

    changes, index = [], {}

    def change(e):
        key = (e.get('name', ''), e.get('plan', ''))
        if key not in index:
            index[key] = len(changes)
            changes.append({'name': e.get('name', ''), 'line': e.get('line', ''),
                            'files': {p: note_of(n) for p, n in (e.get('files') or {}).items()}})
        return index[key]

    tabs, snap = [], {}
    if committed is not None:
        tabs.append({'id': 'committed', 'label': 'Committed', 'idle': 'as of the last commit.'})
        snap['committed'] = state_snap(lists, committed, head_files, all_files)
    tabs.append({'id': 'current', 'label': 'Current', 'idle': 'as it is now, committed or not.'})
    snap['current'] = state_snap(lists, current, now_files, all_files)
    if committed is not None:
        tabs.append({'id': 'cc', 'label': 'Committed → Current', 'delta': True})
        s = delta_snap(lists, committed, current, head_files, now_files, changed, all_files)
        s['changes'] = [change(e) for e in built]
        s['hits'] = {str(change(e)): hits_of(e, current) for e in built}
        snap['cc'] = s
    for tab, label, c, w, files, ch in start_worlds:
        tabs.append({'id': tab, 'label': label, 'delta': True})
        s = delta_snap(lists, w, current, files, now_files, ch, all_files)
        since = built + [e for e in entries_since(git, name, c) if (e.get('name', ''), '') not in set((b.get('name', ''), '') for b in built)]
        s['changes'] = [change(e) for e in since]
        s['hits'] = {str(change(e)): hits_of(e, current) for e in since}
        snap[tab] = s
    for k, (pl, mine, w, files, after) in enumerate(plan_worlds):
        tab = 'plan:%d' % k
        tabs.append({'id': tab, 'label': 'Current → Plan' if len(plan_worlds) == 1 else 'Current → Plan: ' + pl, 'delta': True})
        s = delta_snap(lists, current, w, now_files, after, files, all_files)
        s['changes'] = [change(e) for e in mine]
        s['hits'] = {str(change(e)): hits_of(e, w, problems) for e in mine}
        snap[tab] = s

    # ---- the file view: a line of words per file; a new file's line is its change note
    said = {}
    for e in entries:
        for p, n in (e.get('files') or {}).items():
            said.setdefault(p, note_of(n))
    file_rows = [[p, words.get(p) or (said.get(p, '') if p not in (head_files or ()) else '')] for p in sorted(all_files)]

    listed = World(lists.sys)
    data = {'name': system.get('name') or os.path.basename(root), 'views': emit_views(lists.sys), 'flows': emit_flows(folded)}
    if lists.lines:
        data['api'], data['types'] = {}, {}
        for folder in listed.boxes:
            fns = [[lists.lines[i]['sig'], lists.lines[i]['words']] for i in lists.order.get(folder, []) if not lists.lines[i]['type']]
            if fns:
                data['api'][folder] = fns
            for i in lists.order.get(folder, []):
                if lists.lines[i]['type']:
                    data['types'][i] = [lists.lines[i]['sig'], lists.lines[i]['words'], folder]
    data.update({'dirs': {p: w for p, w in words.items() if p.endswith('/')}, 'files': file_rows, 'changes': changes,
                 'tabs': tabs, 'snap': snap})

    # ---- what the script has to say
    foot = []
    if not git.ok:
        foot.append('This folder is not a git repository, so only the current state is shown.')
    elif not git.head:
        foot.append('There is no commit yet, so only the current state is shown.')
    if not listed.boxes:
        foot.append('No boxes yet. Write the regions and their boxes in %s, with the project\'s owner.' % shown('system.json'))
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    foot.insert(0, 'Built %s%s.' % (stamp, ' from commit %s and the working tree' % git.short(git.head) if git.head else ''))
    data['built'] = foot

    for t in problems.errors:
        print('ERROR  ' + t)
    for t in problems.notes:
        print('note   ' + t)
    if problems.errors:
        print('%d %s. Nothing was folded. Fix %s and run again.' % (len(problems.errors), 'error' if len(problems.errors) == 1 else 'errors',
                                                                  'it' if len(problems.errors) == 1 else 'them'))
    if args.check:
        return 1 if problems.errors else 0
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'view', 'page.html')
    with open(template, encoding='utf-8') as f:
        page = f.read()
    page = page.replace('__TITLE__', html.escape('System view: ' + data['name']))
    page = page.replace('__DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    out = os.path.join(work, 'SYSTEM_VIEW.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print('Wrote %s/SYSTEM_VIEW.html.' % name)
    return 1 if problems.errors else 0


def changed_by_plan(mine, now_files, problems):
    """What a plan does to the files: `+ ` adds one, `- ` removes one, anything else changes one that exists."""
    adds = set(p for e in mine for p, n in (e.get('files') or {}).items() if n.startswith('+ '))
    for e in mine:
        for p, n in (e.get('files') or {}).items():
            if n.startswith('+ '):
                yield p, 'add'
            elif n.startswith('- '):
                yield p, 'del'
            else:
                if p not in now_files and p not in adds:
                    near = sorted(q for q in now_files if os.path.dirname(q) == os.path.dirname(p))[:3]
                    problems.error('%s: %s does not exist and its note has no "+ ". %s' % (
                        e.get('name', '?'), p, 'Nearest: ' + ', '.join(near) + '.' if near else 'Nothing exists in that folder.'))
                yield p, 'chg'


def entries_since(git, name, commit):
    """The built entries of changes.json as it was at each commit after this one, joined by name; the latest text wins."""
    found = {}
    for c in git.commits_between(commit):
        raw = git.show(c, '%s/SYSTEM_VIEW/changes.json' % name)
        for e in parse_json_text(raw) or [] if raw else []:
            if not isinstance(e, dict) or e.get('plan'):
                continue
            old = found.get(e.get('name', ''))
            if old:
                files = dict(old.get('files') or {})
                files.update(e.get('files') or {})
                e = dict(e, files=files)
            found[e.get('name', '')] = e
    return list(found.values())


def scan(root, hidden):
    """Every file of a folder that is not a repository."""
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != '.git']
        for f in files:
            p = os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/')
            if not any(p.startswith(h) for h in hidden):
                yield p


def main():
    ap = argparse.ArgumentParser(description='Builds the system view of a project: WORK/SYSTEM_VIEW.html.')
    ap.add_argument('--check', action='store_true', help='print the checks and write nothing')
    ap.add_argument('--seen', action='store_true', help='move Seen to the last commit')
    ap.add_argument('--from', dest='start', metavar='COMMIT', help='also show a delta that starts at this commit')
    ap.add_argument('--work', metavar='FOLDER', help='the work folder, when it is not the nearest WORK/')
    args = ap.parse_args()
    try:
        return build(args)
    except Stop as e:
        print('system_view.py: %s' % e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
