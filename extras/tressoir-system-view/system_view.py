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
EMPTY_BLOB = 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'


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
        """({path: add | chg | del}, {new path: old path}) between a commit and the working tree, untracked files
        included. A renamed file is `del` under its old path and `add` under its new one, and is in the second map."""
        out = self._run('diff', '--name-status', '-M', '--relative', '-z', commit)[1].split('\0')
        st, moved, i = {}, {}, 0
        while i < len(out) - 1:
            code = out[i][:1]
            if code in ('R', 'C') and i + 2 < len(out):
                if code == 'R':
                    st[out[i + 1]], moved[out[i + 2]] = 'del', out[i + 1]
                st[out[i + 2]] = 'add'
                i += 3
            else:
                st[out[i + 1]] = {'A': 'add', 'D': 'del'}.get(code, 'chg')
                i += 2
        new = [p for p in self._run('ls-files', '-z', '--others', '--exclude-standard')[1].split('\0') if p]
        for p in new:
            st[p] = 'add'
        # a file moved without telling git: the same content under a new name git does not follow yet
        gone = [p for p, v in st.items() if v == 'del' and p not in moved.values()]
        if gone and new and len(new) <= 500:
            was = {}
            for p in gone:
                code, sha = self._run('rev-parse', '%s:./%s' % (commit, p))
                if code == 0 and sha.strip() != EMPTY_BLOB:
                    was.setdefault(sha.strip(), p)
            code, shas = self._run('hash-object', '--', *new)
            if code == 0:
                for p, sha in zip(new, shas.split('\n')):
                    if sha in was and was[sha] not in moved.values():
                        moved[p] = was[sha]
        st = {p: v for p, v in st.items() if self.keep([p])}
        return st, {n: o for n, o in moved.items() if n in st and o in st}

    def diff(self, commit, path):
        return self._run('diff', '-U0', commit, '--', path)[1]

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
                if b['folder'] in self.boxes and problems is not None:
                    problems.error('The box %s is written twice.' % b['folder'])
                self.boxes[b['folder']] = b
                self.parent[b['folder']] = parent['folder'] if parent else None
        owner = {}
        for folder in self.boxes:
            for p in self.paths(folder):
                if p in owner and owner[p] != folder and problems is not None:
                    problems.error('The path %s is given to two boxes: %s and %s.' % (p, owner[p], folder))
                owner.setdefault(p, folder)
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


def hits_of(entry, world, problems=None, base=None):
    """The listed lines a change marks: the names under `affects`, the lines it states, the lines of a box it brings,
    and the lines of a box that goes with its files. A name is looked up in the boxes the entry's files belong to
    and the boxes around them. `world` is the state the change leads to, `base` the one it starts from."""
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
    if base is not None:
        for f in base.boxes:
            if f not in world.boxes and any(base.holds(f, p) for p in entry.get('files') or {}):
                hit.extend(base.order.get(f, []))
    # a box that lists a function of a box inside it shows the same line
    out = []
    for i in hit:
        target = (world.lines[i]['alias'] or i) if i in world.lines else i
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


def delta_snap(lists, a, b, a_files, b_files, changed, all_files, moved=None):
    """From state a to state b. `changed` is {path: add | chg | del}; `moved` is {new path: old path}."""
    listed = World(lists.sys)
    snap = {'files': {}, 'boxes': {}, 'lines': {}}
    for p in all_files:
        if p in changed:
            snap['files'][p] = changed[p]
        elif p not in a_files and p not in b_files:
            snap['files'][p] = None
    # a renamed file is one line: its new path, with the old name beside it
    for new, old in (moved or {}).items():
        snap['files'][new], snap['files'][old] = 'chg', None
    if moved:
        snap['moved'] = dict(moved)
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


# ---------------------------------------------------------------- the checks

def check_shape(system, entries, shown):
    """Stops on a file whose shape the rest of the script cannot read."""
    regions = system.get('regions')
    if regions is not None and not isinstance(regions, dict):
        raise Stop('%s: "regions" must be an object.' % shown('system.json'))

    def row(r, where):
        if not isinstance(r, dict) or not isinstance(r.get('boxes') or [], list):
            raise Stop('%s: %s must be an object with a list under "boxes".' % (shown('system.json'), where))
        for b in r.get('boxes') or []:
            if not isinstance(b, dict) or not isinstance(b.get('folder'), str) or not b['folder']:
                raise Stop('%s: a box in %s has no "folder"%s.' % (shown('system.json'), where,
                           ' (%s)' % b['name'] if isinstance(b, dict) and b.get('name') else ''))
            if not isinstance(b.get('interface') or [], list) or not all(isinstance(t, str) for t in b.get('interface') or []):
                raise Stop('%s: "interface" of %s must be a list of lines.' % (shown('system.json'), b['folder']))
            for inner in b.get('inside') or []:
                row(inner, 'the rows inside ' + b['folder'])

    for key, r in (regions or {}).items():
        if key not in REGIONS:
            raise Stop('%s has a region "%s". The regions are: %s.' % (shown('system.json'), key, ', '.join(REGIONS)))
        if r is not None:
            row(r, 'the region "%s"' % key)
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get('name'), str) or not e['name']:
            raise Stop('%s: every entry is an object with a "name".' % shown('changes.json'))
        ok = (isinstance(e.get('files') or {}, dict) and all(isinstance(n, str) for n in (e.get('files') or {}).values())
              and isinstance(e.get('affects') or [], list) and all(isinstance(a, str) for a in e.get('affects') or [])
              and isinstance(e.get('interface') or {}, dict)
              and all(isinstance(l, list) and all(isinstance(t, str) for t in l) for l in (e.get('interface') or {}).values())
              and isinstance(e.get('boxes') or [], list) and all(isinstance(b, dict) for b in e.get('boxes') or [])
              and all(isinstance(b.get('interface') or [], list) for b in e.get('boxes') or []))
        if not ok:
            raise Stop('%s: the entry "%s" is not in the shape the skill gives: "files" is an object of notes, "affects" a list of '
                       'names, "interface" an object of lists of lines, "boxes" a list of boxes.' % (shown('changes.json'), e['name']))


def stated(entry):
    """Every interface line an entry states: (the list it is in, the box's folder, the text)."""
    out = []
    for folder, lines in (entry.get('interface') or {}).items():
        out.extend((lines, folder, t) for t in list(lines))
    for b in entry.get('boxes') or []:
        if b.get('folder'):
            out.extend((b['interface'], b['folder'], t) for t in list(b.get('interface') or []))
    return out


def line_id(folder, text):
    p = parse_line(text[2:] if text.startswith('- ') else text)
    return p['name'] if p['type'] else folder + '#' + p['name']


def later_wins(built, problems):
    """A built line is stated once. When two built entries state the same line the later one stands: the line is taken
    out of the earlier entry, and its name goes under that entry's `affects` unless the line is gone."""
    first, rewritten = {}, False
    for e in built:
        for lines, folder, text in stated(e):
            i = line_id(folder, text)
            old = first.get(i)
            if old is not None and old[0] is not e and old[2] in old[1]:
                old[1].remove(old[2])
                name = parse_line(text[2:] if text.startswith('- ') else text)['name']
                if not text.startswith('- ') and not old[2].startswith('- ') \
                        and name not in [a.rpartition(': ')[2] for a in old[0].get('affects') or []]:
                    old[0].setdefault('affects', []).append(name)
                problems.note('"%s" and "%s" both state %s in %s. The later one stands, and the line is taken out of the earlier '
                              'entry. It was: %s. It is: %s.' % (old[0].get('name', '?'), e.get('name', '?'), name, folder, old[2], text))
                rewritten = True
            first[i] = (e, lines, text)
    if rewritten:
        for e in built:
            if 'interface' in e:
                e['interface'] = {f: l for f, l in e['interface'].items() if l}
                if not e['interface']:
                    del e['interface']
    return rewritten


def check_files(entry, now_files, changed, problems):
    """A built entry's files: a `+ ` file exists, and no file is unchanged while the others differ."""
    name, files = entry.get('name', '?'), entry.get('files') or {}
    missing = [p for p, n in files.items() if n.startswith('+ ') and p not in now_files]
    for p in missing:
        problems.error('%s: %s is written as a new file ("+ ") and does not exist.' % (name, p))
    if changed is None:
        return
    same = [p for p in files if p not in changed and p not in missing]
    if same and len(same) < len(files):
        for p in same:
            problems.error('%s: %s does not differ from the last commit, while other files of the entry do. '
                           'Take it out of the entry, or make the change its note describes.' % (name, p))


def figure_paths(*worlds):
    """Every path the figure covers: the regions' folders and the boxes' paths."""
    out = set()
    for w in worlds:
        if w is None:
            continue
        for r in (w.sys.get('regions') or {}).values():
            if r and r.get('folder'):
                out.add(r['folder'])
        for f in w.boxes:
            out.update(w.paths(f))
    return out


def some(items, most=6):
    items = list(items)
    return ', '.join(items[:most]) + (' and %d more' % (len(items) - most) if len(items) > most else '')


def differs(a, b):
    return (a is None) != (b is None) or (a is not None and (a['sig'], a['words']) != (b['sig'], b['words']))


def note_loose_files(world, now_files, problems):
    for key in REGIONS:
        folder = ((world.sys.get('regions') or {}).get(key) or {}).get('folder')
        if not folder:
            continue
        loose = sorted(p for p in now_files if under(folder, p) and world.box_of(p) is None)
        if loose:
            problems.note('%d %s under %s belong%s to no box: %s.' % (len(loose), 'file' if len(loose) == 1 else 'files', folder,
                                                                      's' if len(loose) == 1 else '', some(loose)))


def note_unseen_names(world, code, now_files, problems):
    """A listed name that appears nowhere in the files of its box."""
    words = {}
    for p in now_files:
        homes = [f for f in world.boxes if world.order.get(f) and world.holds(f, p)]
        if homes:
            ids = set(re.findall(r'[A-Za-z_]\w*', code.text(p)))
            for f in homes:
                words.setdefault(f, set()).update(ids)
    for folder, ids in world.order.items():
        if folder in words:
            missing = [world.lines[i]['name'] for i in ids if world.lines[i]['name'].split('.')[-1] not in words[folder]]
            if missing:
                problems.note('Listed in %s and found nowhere in its files: %s.' % (folder, some(missing)))


def note_flows(system, built, world, problems):
    """A flow that passes a box a built entry states a line of, or calls a function it marks."""
    for f in system.get('flows') or []:
        for e in built:
            boxes = set(folder for _l, folder, _t in stated(e))
            marks = set(hits_of(e, world))
            where = [s.get('at') for s in f.get('steps') or []
                     if s.get('at') in boxes or (s.get('calls') and '%s#%s' % (s.get('at'), s['calls']) in marks)]
            if where:
                problems.note('The flow "%s" passes %s, which "%s" changes. Check that the flow still reads true.'
                              % (f.get('name', '?'), some(sorted(set(where)), 3), e.get('name', '?')))


def note_dangling(system, world, problems):
    """A flow step, a link or a neighbour that points at nothing."""
    regions = system.get('regions') or {}
    ends = set(r['folder'] for r in regions.values() if r and r.get('folder'))
    for l in system.get('links') or []:
        for k in ('from', 'to'):
            if l.get(k) not in ends:
                problems.note('A link of the overview points at %s, which is not a region\'s folder. It is not drawn.' % l.get(k))
    for folder, b in world.boxes.items():
        rows = set(r.get('folder') for r in b.get('inside') or [])
        for l in b.get('links') or []:
            for k in ('from', 'to'):
                if l.get(k) not in rows:
                    problems.note('A link inside %s points at %s, which is none of its rows. It is not drawn.' % (folder, l.get(k)))
        for k in ('from', 'uses'):
            for x in (b.get(k) or {}).get('boxes') or []:
                if x not in world.boxes:
                    problems.note('%s: "%s" names %s, which is not a box.' % (folder, k, x))
    for f in system.get('flows') or []:
        for n, s in enumerate(f.get('steps') or []):
            at = s.get('at')
            if at not in world.boxes:
                problems.note('The flow "%s", step %d, is at %s, which is not a box.' % (f.get('name', '?'), n + 1, at))
            elif s.get('calls') and '%s#%s' % (at, s['calls']) not in world.lines:
                problems.note('The flow "%s", step %d, calls %s, which %s does not list. The page draws the step without its call.'
                              % (f.get('name', '?'), n + 1, s['calls'], at))


# ---------------------------------------------------------------- what the text of the code shows

DEF = re.compile(r'^\s*(?:(?:pub(?:\([a-z]+\))?|export|default|async|static|public|private|protected|internal|inline|virtual|override'
                 r'|unsafe|extern|final|abstract)\s+)*(?:def|fn|func|function|fun|sub|proc)\b\s*\*?\s*(?:\([^)]*\)\s*)?([A-Za-z_]\w*)')
CALLISH = re.compile(r'([A-Za-z_]\w*)\s*\(')
NOT_A_NAME = set('if for while switch return catch sizeof function def fn func class new typeof elif with and or not in is'.split())


def name_in(text):
    """The function a line of code starts, as far as its text shows."""
    m = DEF.match(text)
    if m:
        return m.group(1)
    for n in CALLISH.findall(text):
        if n not in NOT_A_NAME:
            return n
    return None


class Code:
    """Where functions start, which hold changed lines, and who calls whom inside a box. Read from the text alone:
    a help for writing `affects`, never a check."""

    def __init__(self, root, git, commit, world, now_files):
        self.root, self.git, self.commit, self.world, self.now = root, git, commit, world, now_files
        self._text, self._defs, self._box = {}, {}, {}

    def text(self, path):
        if path not in self._text:
            full, text = os.path.join(self.root, path), ''
            try:
                if os.path.getsize(full) <= 512 * 1024:
                    with open(full, encoding='utf-8', errors='ignore') as f:
                        text = f.read()
            except OSError:
                pass
            self._text[path] = text
        return self._text[path]

    def defs(self, path):
        """[(name, the lines up to the next function)] for one file."""
        if path not in self._defs:
            lines = self.text(path).split('\n')
            starts = [(i, m.group(1)) for i, m in ((i, DEF.match(l)) for i, l in enumerate(lines)) if m]
            self._defs[path] = [(n, '\n'.join(lines[i + 1:starts[k + 1][0] if k + 1 < len(starts) else len(lines)]))
                                for k, (i, n) in enumerate(starts)]
        return self._defs[path]

    def changed_fns(self, path, status):
        """The functions of a file that hold changed lines."""
        if status == 'add':
            return [n for n, _body in self.defs(path)]
        if status != 'chg' or not self.commit:
            return []
        out, ctx, first = [], None, False
        for line in self.git.diff(self.commit, path).split('\n'):
            if line.startswith('@@'):
                ctx, first = (name_in(line.split('@@', 2)[-1]) if line.count('@@') >= 2 else None), True
            elif line[:1] in ('+', '-') and not line.startswith(('+++', '---')):
                m = DEF.match(line[1:])
                if m:
                    ctx = m.group(1)
                if ctx and (m or first) and ctx not in out:
                    out.append(ctx)
                first = False
        return out

    def home(self, path):
        """The nearest box around a file that lists a function, and the names it lists."""
        chain = self.world.around(self.world.box_of(path))
        for f in chain:
            names = [self.world.lines[i]['name'] for i in self.world.order.get(f, []) if not self.world.lines[i]['type']]
            if names:
                return f, names
        return (chain[0] if chain else None), []

    def reach(self, path, fns):
        """The listed functions of the file's box through which these functions are reached: the first listed one on each path."""
        home, names = self.home(path)
        if not home or not names or not fns:
            return []
        if home not in self._box:
            files = sorted(p for p in self.now if self.world.holds(home, p))[:400]
            self._box[home] = [d for p in files for d in self.defs(p)]
        short = {n.split('.')[-1]: n for n in names}
        out, seen, todo = [], set(), list(fns)
        while todo and len(seen) < 400:
            f = todo.pop(0)
            if f in seen:
                continue
            seen.add(f)
            if f in short:
                if short[f] not in out:
                    out.append(short[f])
                continue
            pat = re.compile(r'\b%s\s*\(' % re.escape(f))
            todo.extend(n for n, body in self._box[home] if n not in seen and pat.search(body))
        return out

    def proposal(self, paths, changed, moved):
        """(names proposed for `affects`, whether any changed function was found, one line of help per file)."""
        names, found, said = [], False, []
        for p in paths:
            st = changed.get(p)
            fns = self.changed_fns(p, st) if p not in moved else []
            found = found or bool(fns)
            for n in self.reach(p, fns):
                if n not in names:
                    names.append(n)
            what = 'renamed from %s' % moved[p] if p in moved else {'add': 'new', 'del': 'removed'}.get(st, 'changed')
            if fns:
                what += (', with ' if st == 'add' else ' in ') + some(fns, 8)
            home, listed = self.home(p)
            where = 'It is in no box.' if not home else 'Its box %s lists %s.' % (home, some(listed, 12) if listed else 'nothing')
            said.append('  %s: %s. %s' % (p, what, where))
        return names, found, said


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
    check_shape(system, entries, shown)
    problems = Problems()
    built = [e for e in entries if not e.get('plan')]
    plans = []
    for e in entries:
        if e.get('plan') and e['plan'] not in plans:
            plans.append(e['plan'])

    def at_commit(commit):
        raw = git.show(commit, '%s/SYSTEM_VIEW/system.json' % name)
        old = parse_json_text(raw) if raw else None
        try:
            return World(old) if isinstance(old, dict) and old else None
        except (KeyError, TypeError, AttributeError):
            return None

    # ---- what git knows
    now_files = git.files_now() if git.ok else set(scan(root, git.hidden))
    head_files = git.files_at(git.head) if git.head else None
    changed, moved = git.changed_since(git.head) if git.head else ({}, {})
    at_head = at_commit(git.head) if git.head else None

    # ---- the built entries: each line stated once, then folded one entry at a time
    on_disk = copy.deepcopy(built)
    rewritten = later_wins(built, problems)
    base = Problems()
    World(system, base)
    for t in base.errors:
        problems.error(t)
    folded, failed = system, []
    for e in built:
        mine = Problems()
        trial = fold(folded, [e], mine)
        hits_of(e, World(trial, mine), mine)
        check_files(e, now_files, changed if git.head else None, mine)
        new = [t for t in mine.errors if t not in base.errors]
        if new:
            failed.append(e)
            for t in new:
                problems.error(t if t.startswith(e['name'] + ':') else '%s: %s' % (e['name'], t))
            continue
        for t in mine.notes:
            problems.note(t)
        folded = trial
    if head_files is not None:
        folded, gone = drop_removed(folded, head_files, now_files)
        for f in gone:
            problems.note('The box %s is removed: every file it had at the last commit is gone.' % f)
    current = World(folded)
    text = pretty(folded) + '\n'
    path = os.path.join(here, 'system.json')
    before = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if text != before and not args.check and system:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        print('Folded the built changes into %s.' % shown('system.json'))

    # ---- then dropped: a built entry goes once the last commit holds it, its files and its lines unchanged
    dropped, new_words = [], False
    if at_head is not None:
        raw = git.show(git.head, '%s/SYSTEM_VIEW/changes.json' % name)
        held = {}
        for x in (parse_json_text(raw) if raw else None) or []:
            if isinstance(x, dict) and not x.get('plan'):
                held[x.get('name')] = x
        for e, was in zip(built, on_disk):
            if any(e is f for f in failed) or held.get(was['name']) != was or any(p in changed for p in e.get('files') or {}):
                continue
            if any(differs(at_head.lines.get(line_id(folder, t)), current.lines.get(line_id(folder, t))) for _l, folder, t in stated(was)):
                continue
            if any(b.get('folder') not in at_head.boxes or b.get('folder') not in current.boxes
                   or any(at_head.boxes[b['folder']].get(k) != current.boxes[b['folder']].get(k) for k in ('name', 'line', 'also'))
                   for b in e.get('boxes') or []):
                continue
            dropped.append(e)
    if dropped:
        built = [e for e in built if not any(e is d for d in dropped)]
        entries = [e for e in entries if not any(e is d for d in dropped)]
        for e in dropped:
            for p, n in (e.get('files') or {}).items():
                if p in now_files and not words.get(p) and note_of(n):
                    words[p], new_words = note_of(n), True
    if not args.check:
        if rewritten or dropped:
            with open(os.path.join(here, 'changes.json'), 'w', encoding='utf-8') as f:
                f.write(pretty(entries) + '\n')
        if dropped:
            print('Took %d built %s out of %s, now that the last commit holds %s: %s.' % (
                len(dropped), 'entry' if len(dropped) == 1 else 'entries', shown('changes.json'),
                'it' if len(dropped) == 1 else 'them', some([e['name'] for e in dropped])))
        if new_words:
            with open(os.path.join(here, 'lines.json'), 'w', encoding='utf-8') as f:
                f.write(pretty(words) + '\n')

    committed = at_head
    if git.head and committed is None:
        committed = current
        problems.note('The last commit has no %s, so nothing in the figure or the listing is marked as new.' % shown('system.json'))

    # ---- what no entry explains, and what the files and the code say beside the entries
    code = Code(root, git, git.head, current, now_files)
    loose, prepared = [], None
    if git.head:
        explained = set(p for e in built for p in e.get('files') or {})
        unexplained = sorted(p for p in changed if p not in explained and p not in moved.values())
        fig = figure_paths(current, at_head)
        loose = [p for p in unexplained if any(under(f, p) for f in fig)]
        if loose:
            problems.error('%d changed %s under the figure %s in no entry: %s. An entry is prepared below.' % (
                len(loose), 'file' if len(loose) == 1 else 'files', 'is' if len(loose) == 1 else 'are', some(loose)))
            names, _found, said = code.proposal(unexplained, changed, moved)
            prepared = ({'name': '?', 'line': '?', 'files': {p: '?' for p in unexplained}}, said)
            if names:
                prepared[0]['affects'] = names
        for e in built:
            if any(e is f for f in failed):
                continue
            paths = [p for p in e.get('files') or {} if p in changed]
            names, found, _said = code.proposal(paths, changed, moved)
            states = set(parse_line(t)['name'] for _l, _f, t in stated(e) if not t.startswith('- '))
            mine = [a.rpartition(': ')[2] for a in e.get('affects') or []]
            names = [n for n in names if n not in states]
            if found and set(names) != set(mine):
                problems.note('%s: "affects" has %s. Following its changed lines to the nearest listed functions gives %s. '
                              'Only said: correct the entry if the second is right.'
                              % (e['name'], ', '.join(mine) or 'nothing', ', '.join(names) or 'nothing'))
    note_loose_files(current, now_files, problems)
    note_unseen_names(current, code, now_files, problems)
    note_flows(folded, built, current, problems)
    note_dangling(folded, current, problems)

    plan_worlds = []
    for pl in plans:
        mine = [e for e in entries if e.get('plan') == pl]
        files = dict(changed_by_plan(mine, now_files, problems))
        after = (now_files | set(p for p, s in files.items() if s == 'add')) - set(p for p, s in files.items() if s == 'del')
        psys, _gone = drop_removed(fold(folded, mine, problems, quiet=True), now_files, after)
        plan_worlds.append((pl, mine, World(psys), files, after))
        for e in mine:
            done = [p for p, n in (e.get('files') or {}).items()
                    if (n.startswith('+ ') and p in now_files) or (n.startswith('- ') and p not in now_files)]
            if done:
                problems.note('%s, of the plan %s, looks built: %s %s. Once it is built, correct the entry and delete its "plan" key.' % (
                    e['name'], pl, some(done, 3), 'is already as the plan leaves it' if len(done) == 1 else 'are already as the plan leaves them'))
            moved_on = [parse_line(t[2:] if t.startswith('- ') else t)['name'] for _l, folder, t in stated(e)
                        if at_head is not None and differs(at_head.lines.get(line_id(folder, t)), current.lines.get(line_id(folder, t)))]
            if moved_on:
                problems.note('%s, of the plan %s, restates %s, which %s changed since the last commit. Check the plan against the line as it is now.' % (
                    e['name'], pl, some(moved_on), 'has' if len(moved_on) == 1 else 'have'))

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
        start_worlds.append((tab, label, c, w, git.files_at(c)) + git.changed_since(c))
    all_files = set(now_files)
    if head_files is not None:
        all_files |= head_files
    for _pl, _mine, _w, files, after in plan_worlds:
        all_files |= after
    for _tab, _label, _c, _w, files, _ch, _mv in start_worlds:
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
        s = delta_snap(lists, committed, current, head_files, now_files, changed, all_files, moved)
        s['changes'] = [change(e) for e in built]
        s['hits'] = {str(change(e)): hits_of(e, current, base=committed) for e in built}
        snap['cc'] = s
    for tab, label, c, w, files, ch, mv in start_worlds:
        tabs.append({'id': tab, 'label': label, 'delta': True})
        s = delta_snap(lists, w, current, files, now_files, ch, all_files, mv)
        since = built + [e for e in entries_since(git, name, c) if (e.get('name', ''), '') not in set((b.get('name', ''), '') for b in built)]
        s['changes'] = [change(e) for e in since]
        s['hits'] = {str(change(e)): hits_of(e, current, base=w) for e in since}
        snap[tab] = s
    for k, (pl, mine, w, files, after) in enumerate(plan_worlds):
        tab = 'plan:%d' % k
        tabs.append({'id': tab, 'label': 'Current → Plan' if len(plan_worlds) == 1 else 'Current → Plan: ' + pl, 'delta': True})
        s = delta_snap(lists, current, w, now_files, after, files, all_files)
        s['changes'] = [change(e) for e in mine]
        s['hits'] = {str(change(e)): hits_of(e, w, problems, base=current) for e in mine}
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
        data['none'] = 'No boxes yet. Write the regions and their boxes in %s, with the project\'s owner.' % shown('system.json')
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    foot.insert(0, 'Built %s%s.' % (stamp, ' from commit %s and the working tree' % git.short(git.head) if git.head else ''))
    data['built'] = foot

    for t in problems.errors:
        print('ERROR  ' + t)
    for t in problems.notes:
        print('note   ' + t)
    if prepared:
        print('\nPrepared for the changed files no entry explains. Put it in %s, name it, and correct it:' % shown('changes.json'))
        print(pretty(prepared[0], '  ').join(['  ', '']))
        print('\n'.join(prepared[1]))
    if problems.errors:
        print('%d %s.%s Fix %s and run again.' % (
            len(problems.errors), 'error' if len(problems.errors) == 1 else 'errors',
            ' Nothing was folded from: %s.' % some([e['name'] for e in failed]) if failed else '',
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
