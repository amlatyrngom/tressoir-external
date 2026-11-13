---
name: tressoir-system-view
description: Keep the system view current, one page that draws the project's major parts, what is inside them, the interfaces between them, the files, and what changed or is planned. Use for every task that changes code (write its named changes and run the script before committing), when a plan is written or built, and before adding a component, a folder or a file that several components would share. Experimental.
---

# System view

I no longer read most of the code, so I lose track of how a project is put together. The system
view is how I keep the picture: one page, `WORK/SYSTEM_VIEW.html`, with a figure of the major
parts, views inside the larger ones, flows, the interface each part offers, and a file view. Its
tabs show the last commit, the current state, what changed between them, what changed since I last
looked, and what each plan would change.

```text
WORK/
  SYSTEM_VIEW.html      the page; the script rebuilds it, git ignores it
  SYSTEM_VIEW/
    system.json         the architecture             written with me, rarely
    changes.json        named changes and plans      yours, for every task
    lines.json          a few words per file         optional
    seen                one commit                   the script writes it
    FEEDBACK.md         what got in the way
```

Commit `WORK/SYSTEM_VIEW/` together with the code, never separately. The page is not committed:
anyone rebuilds it with the script. Three worked examples are in
`WORK/skills/tressoir-system-view/examples/`: `tally/` (one view), `marlin/` (views inside boxes)
and `pocket/` (all the code in one folder). Copy the shape of the one nearest to the project.

## Two phases

**Architecting, with me.** The regions, the boxes, what is inside a box, the flows and the
interface listing are decided together and change rarely. They live in `system.json`.

**Mechanical, on your own.** For every task you write entries in `changes.json` and run the
script. You decide nothing about the figure, you ask me nothing, and you do not edit
`system.json`: the script writes the entries' lines, boxes and moves into it.

**The files say what is true. They never say what changed.** The script finds what changed by
comparing git, `system.json` at an earlier commit, and the planned entries. So never write a
status, a mark, what a line used to be, or a count.

## `changes.json`: one entry per named change

The same shape for work that is planned and work that is done.

```json
{ "name": "Group commit", "line": "many commits share one flush",
  "files": {
    "src/core/transactions/durability/commit/commit.rs": "waits briefly to share a flush",
    "src/core/transactions/durability/commit/group.rs": "the queue of waiting commits",
    "src/core/storage/disk/wal/wal.rs": "one flush for the whole group"
  },
  "affects": ["commit"],
  "interface": {
    "src/core/storage/disk/wal/": ["flush_group(upto: Lsn)  // flushes once for every commit waiting below this position"]
  } }
```

| Field | What you write | When |
| --- | --- | --- |
| `name`, `line` | what the change is, and how it works, in a few words | always |
| `files` | each file and what changed in it | always |
| `affects` | listed functions whose signature is the same but whose code this change reaches | when there are any |
| `interface` | a listed line as it is now, under its box's folder | when its signature or its words are new or different |
| `boxes` | a box as it is now | when it is new, or its `line` changed, or it gains a path (`also`) |
| `moves` | a box's old path, then its new one | when its code moved and it is otherwise the same box |
| `plan` | the plan's name | only while it is not built |

An entry restates whatever is no longer true, and nothing else:

- A line under `interface` replaces the line of that name in that box, or is added last. Leave the
  words out to keep them. `- name` removes a line. A rename is `- old` and the new line. A changed
  signature goes here and not also in `affects`; so does a line whose words are no longer true
  while its signature stays. A new type goes under the box that owns it.
- When two built entries state the same line, the later one in the file stands. The script takes
  the line out of the earlier entry, puts its name under that entry's `affects`, and says so.
- A box under `boxes` is matched by `folder`. Write a new one whole, with its `interface`. For an
  existing one give only what changed; `also` adds paths.
- A new box is a folder directly in a row's or a region's folder. The script does not place any
  other: a folder inside a box is not a box, and where two regions share the folder (a flat
  project) the region is mine to choose. Leave such a box out of `boxes` and tell me.
- A box whose folder or file was renamed is said under `moves`: `"moves": { "app/notify.py":
  "app/notify/" }`. The box keeps its region, name, line and interface, and the flow steps that
  were at the old path follow. The new path stays in the same row or region and outside every
  other box. Until it is said, the script keeps the box and gives an error that proposes the
  line. A box that changes region, splits, or joins another is not a move.
- A renamed file is written once under `files`, with its new path.
- A planned entry also says what git cannot know yet: a note that starts with `+ ` is a file the
  plan adds, `- ` one it removes.

How many entries: with a plan, one per plan step, with the same names. Without a plan, one per
task I asked for, in place before the task's first commit. Write it before or after the code:
run with `--check` and no entry, and the script prepares one from the diff for you to name and
correct. Every entry has its own name: two built
entries, or two of one plan, with the same name stop the script. Do not rebuild entries later from
an old diff.

### `affects`: the nearest listed function

A change deep in private code must show on the nearest function I can see.

> For each edit in code, name the listed function it is in. If it is in code no listing shows (a
> private helper, a constant), name every listed function **of the same box** through which that
> code is reached: the ones that call it, the first listed function on each path, or the one that
> returns the object it belongs to. An edit to a row that registers a listed function (a command's
> arguments, a route) names that function. Stop there, and never go into another box.

- If the box lists nothing that reaches the edit, name nothing: the change shows on the box's
  `// internal:` line. Edits to data and prose files name nothing either.
- Do not ask whether behaviour changed. Edited means named.
- A name is looked up in the boxes the entry's files belong to and the boxes around them. If two
  of them list it, write `"<box folder>: name"`.
- The script proposes `affects` from the diff by following callers inside the box. Check the
  proposal; it reads text and can miss a call or find a false one.

## The routine

1. **A planned task starts.** Run the script with `--seen`, write one entry per plan step, each
   with `"plan": "<plan name>"`, and run the script.
2. **As each step is built.** Correct its entry to what was built (file names, signatures), then
   delete its `plan` key. There is no other command for building a plan.
3. **A task ends**, planned or not. Run the script. Answer every error; read every note; run again
   until no error is left, except one that is architecture (see below).
4. **Then commit**, code and `WORK/SYSTEM_VIEW/` together. If the figure, a flow or a listed line
   changed, say so in one line of the hand-off. Do not run the script again after the commit: the
   committed entry stays in `changes.json` until the next task's first run takes it out.

```bash
uv run WORK/skills/tressoir-system-view/system_view.py            # fold, check, build the page
uv run WORK/skills/tressoir-system-view/system_view.py --check    # only print the checks
uv run WORK/skills/tressoir-system-view/system_view.py --seen     # I have seen everything up to the last commit
uv run WORK/skills/tressoir-system-view/system_view.py --from <commit>   # also show a delta from that commit
```

It needs only Python 3 and git; `python3` works in place of `uv run`. Once the last commit holds a
built entry, the next run takes it out of `changes.json` by itself: a built and committed change
reads as if it was always there. "Holds" means the commit has the entry unchanged and its
`system.json` already says what the entry states, so an entry committed before the script ran
stays for one more commit. Work that goes on in the same files after that commit needs an entry
of its own. Move Seen only when a planned task starts, when the first figure is committed, or
when I say so.

A file in a shape the script cannot read (a list where an object belongs, text where a list
belongs, a file not saved as UTF-8) stops it with one sentence that says what to write. Nothing
is folded until that is corrected.

What the script prints:

| Error: the entry is not folded | Note: only said |
| --- | --- |
| a changed file under the figure that no entry explains (it prepares an entry) | a file under a region that belongs to no box |
| a name in `affects` found nowhere, or in two boxes | a listed name that appears nowhere in its box's code |
| a built entry's file that does not differ while its other files do | a planned entry that looks built |
| a built entry with a `+ ` file that does not exist | a flow passing a box an entry changes: check it still reads true |
| a planned path that does not exist and has no `+ ` | an open plan restates a line that has changed since the last commit |
| a name twice in a box; a path in two boxes; a bare name with no single match | an entry replaced a line: what it was, what it is |
| a new box the script will not place: inside a box, deeper than a row, or where regions share the folder | a link or a neighbour that points at nothing |
| a box with no file left whose files were renamed (it proposes the `moves` line) | a box with no file; a figure whose regions give no folder |
| a flow step at a path that is not a box | a box removed because its files were deleted |
| `moves` to another region or row, onto or into another box, or of a box with boxes inside | no box written yet |

Reading a diff:

| In the diff | In the entry |
| --- | --- |
| a changed, new or removed file | a line under `files` |
| an edit inside a listed function, or in private code a listed function reaches | the name in `affects` |
| a listed signature changed, a new function another box calls, a new command | the line under `interface` |
| a listed line's words, or a box's `line`, no longer true | restate it |
| a box's folder or file renamed, the box otherwise the same | `moves`, old path then new path |
| a new folder inside a box | nothing |
| a new folder directly in a row or a region | a box under `boxes`, with a name and a line |
| a new file in a flat project | `also` on the only box that imports it |

**Architecture is never decided mechanically:** a new row or region; a box that changes region,
splits or merges; in a project whose code is one folder, a new box, or a file that two boxes
import; a flow step that has become false. Leave the figure and the flows alone and tell me in
your report. An error that is architecture stays until I have answered: commit the code with the
error left, and put it first in the hand-off. Once I have answered, write my answer into
`system.json`.

## `system.json`: the architecture

Written with me. Four layers; each is optional and the page works without the later ones.

1. **Regions and boxes.** Five regions: `entry` (how work gets in), `core` (what the project
   does), `external` (services it calls), `platform` (what differs per platform), `separate`
   (another product in the same repository). A region has a `folder`, a `line` and `boxes`; leave
   it empty when it does not apply. Where the code sits at the top of the repository, the folder
   is written `"./"`. `links` between regions have `from`, `to` (the regions' keys, such as
   `entry` and `core`), a short `label` and a sentence, `says`.
2. **Inside a box.** `inside` lists its rows; a row is a folder and its boxes are folders in it.
   A box with an inside may give `links` between its rows, and `from` and `uses`: the outside
   boxes it works with, each with a sentence.
3. **Interface.** One string per line. A function is `name(arg: Type) → Type  // words`; a type
   is `Name = shape  // words`.
4. **Flows.** Ordered steps: `at` (a box's folder), `gets` (what arrives), `does` (a sentence),
   `calls` (the function called there, which that box must list).

- A box has `name`, `folder` and `line`. `folder` is its main path and its identifier everywhere.
  In a project whose code is flat it may be a single file, and `also` lists further paths. A file
  belongs to the box with the longest matching path; a path belongs to one box only.
  `"shared": true` marks the one box of helpers with no better home.
- A box lists what other boxes call. An entry box lists its entry points: commands, routes.
  A function that callers reach through a module of the box is written with that name
  (`youtube.minutes`). Constants and settings are not listed.
- Names are spelt as in the code. Where the code has no single name (a command, a route), choose
  one; the note that it appears nowhere is then expected. The name of a line is its first word, so
  two routes cannot both start with `GET`: write `get_users  // GET /users, lists the users`.
- A type is written in the box that owns it.
- A bare name (`"lookup"`) is the function of that name from a box inside, and must match exactly
  one. A parent never writes out a signature that an inner box lists.
- A name appears once per box; a type once in the file.
- Tests, documents and scripts are in the file view and are never boxes.

### Starting in a project that already has code

Propose the regions and boxes from the code as it is, and settle them with me before going
further. Draw what a system architect would put on a whiteboard: a box is a part with a job of its
own, not a file, and its lines are what an architect needs to know to connect it to the others.
That is around a dozen boxes; a simple project needs fewer, a complex one more. Once the
figure is agreed, add the interface and one or two flows. Give a box an inside only when it has
folders of its own that I would name; a box that is one file or one flat folder has none. Where a
component is spread out, give the box its main folder and list the rest under `also`. Leave
`changes.json` as `[]`. Do not move code to make the first figure look tidy.

Where all the code is in one folder (`app/`, say), every region that applies gets that folder, and
a box is a file or a folder directly in it, as in the `pocket/` example. The script then cannot
tell which region a new box belongs to, so a new box is mine to place.

Write `lines.json` once at this point, a few words per source file; later the script adds a new
file's words from its entry and follows renames. Commit the first figure, then run the script
with `--seen`: the first figure is the first thing I have seen.

## Keep the code easy to draw

The view only works when the folders match the figure: one region is one parent folder, one box is
one folder inside it, and I can point at a box and get its code.

- A new component gets its own folder under the region it belongs to, and its box, in the same
  change.
- Code that talks to an outside service goes in that service's folder, not in the component that
  uses it. Code for one platform goes under that platform, not in the core.
- Avoid a component spread across several folders or split by kind of file, one folder holding
  two components, and a file that serves two components.
- Shared stays small. Put something there only when two boxes need it and it belongs to neither.
- Files at the top of the source folder only wire things together.

Do not reorganize existing code to fit the view. Record the mismatch with `also`, and tell me.
Restructuring is mine to decide.

## This is experimental

When any of these happens, add a dated line to `WORK/SYSTEM_VIEW/FEEDBACK.md` saying what happened
and what would have helped:

- the files made you write something awkward, or the same thing twice;
- the script reported something wrong, unclear or useless, or its proposal for `affects` was off;
- the project's layout fought the view;
- I commented on the view or on this skill.

Do not patch this skill, its script or its page inside the project. They belong to the kit and are
replaced on the next refresh. The feedback is collected from time to time and applied to the kit.
