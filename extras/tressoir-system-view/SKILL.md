---
name: tressoir-system-view
description: Keep the system view current, one page that draws the project's major parts and lists them as code (modules, their functions and types, and flows through them), with the files and what changed or is planned. Use for every task that changes code (write its named changes and run the script before committing), when a plan is written or built, and before adding a component, a folder or a file that several components would share. Experimental.
---

# System view

I no longer read most of the code, so I lose track of how a project is put together. The system
view is how I keep the picture: one page, `WORK/SYSTEM_VIEW.html`. At the top is a figure of the
major parts. Under it the same parts are listed as
code: each box is a module, with the functions and types it offers; a function that has a flow
opens into it, the body of that function as a short sketch. Beside them is a file view. The tabs
show the last commit, the current state, what changed between them, what changed since I last
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
`WORK/skills/tressoir-system-view/examples/`: `tally/` (one view, the usual shape), `marlin/` (a
large system, with views inside its boxes) and `pocket/` (all the code in one folder). Each has
flows. Copy the shape of the one nearest to the project.

## Two phases

**Architecting, with me.** The regions, the boxes, what is inside a box, the interface listing and
which functions have a flow are decided together and change rarely. They live in `system.json`.

**Mechanical, on your own.** For every task you write entries in `changes.json` and run the
script. You decide nothing about the figure, you ask me nothing, and you do not edit
`system.json`: the script writes the entries' lines, boxes, flows and moves into it.

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
| `flows` | a flow as it is now, whole | when the steps of a function that has a flow changed |
| `moves` | a box's old path, then its new one | when its code moved and it is otherwise the same box |
| `renames` | a listed function, then its new name | when it was renamed and is otherwise the same function |
| `plan` | the plan's name, 24 characters at most: it is written on the plan's tab | only while it is not built |

An entry restates whatever is no longer true, and nothing else:

- A line under `interface` replaces the line of that name in that box, or is added last. Leave the
  words out to keep them. `- name` removes a line. A changed signature goes here and not also in
  `affects`; so does a line whose words are no longer true while its signature stays. A new type
  goes under the box that owns it.
- A function that only changed its name is said under `renames`: `"renames": {
  "app/notify.py: send": "deliver" }`. The line keeps its place, its words and its flow, and
  the sketches that call it follow. If its arguments changed too, also state the new line under
  `interface`, with the new name. A renamed type has no such key: write `- Old` and the new line.
- A function the entry renames, or whose flow or line it states, is marked by that. It need not
  also go under `affects`.
- When two built entries state the same line, the later one in the file stands. The script takes
  the line out of the earlier entry, puts its name under that entry's `affects`, and says so.
- A box under `boxes` is matched by `folder`. Write a new one whole, with its `interface`. For an
  existing one give only what changed; `also` adds paths.
- A new box is a folder directly in a region's folder, in a row's, or in the folder of a box that
  already holds modules. The script does not place any other: a folder inside a box that holds
  none is not a box, and where two regions share the folder (a flat project) the region is mine
  to choose. Leave such a box out of `boxes` and tell me.
- A box whose folder or file was renamed is said under `moves`: `"moves": { "app/notify.py":
  "app/notify/" }`. The box keeps its region, name, line and interface, and its flows follow. The
  new path stays in the same row or region and outside every other box (a box inside another
  stays inside it, in its folder). Until it is said, the script keeps the box and gives an error that proposes the
  line. A box that changes region, splits, or joins another is not a move.
- A flow under `flows` is matched by its function (`of`) and replaces that function's flow. State
  it whole, as in `system.json` (see "Flows" below): copy it from there, or from what the script
  prepares, and edit it. Do it when the task changed the steps I would name: a step added,
  removed, reordered, or now calling another listed function; or when the words on a line are no
  longer true. A change inside a step that leaves its line and its words true leaves the flow
  alone. Removing a function (`- name`) removes its flow; a rename under `renames` keeps it. When
  two built entries state the same flow, the later one stands, as for lines. Do not give a flow
  to a function that has none, and do not drop one, unless I asked: which functions have a flow
  is architecture. When I did ask, a flow stated with an empty `sketch` is taken out.
- A renamed file is written once under `files`, with its new path.
- A planned entry also says what git cannot know yet: a note that starts with `+ ` is a file the
  plan adds, `- ` one it removes. Only the step that adds a file marks it `+ `; a later step of
  the same plan names it plainly. Each step states a line or a flow as it will be once that step
  is built, so two steps that change one flow each state it whole.

How many entries: with a plan, one per plan step, with the same names (for a plan written with
`tressoir-plan`, its milestones). Without a plan, one per
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
> arguments, a route) names that function too. Stop there, and never go into another box.

- If the box lists nothing that reaches the edit, name nothing: the change shows on the box's
  `// internal:` line. Edits to data and prose files name nothing either, nor does a file that
  only moved.
- Do not ask whether behaviour changed. Edited means named.
- A name is looked up in the boxes the entry's files belong to, and the boxes those are inside.
  If two of them list it, write `"<box folder>: name"`.
- The script proposes `affects` from the diff by following callers inside the box. Check the
  proposal; it reads text and can miss a call or find a false one.

## The routine

1. **A plan is written**: I asked for a plan. Write one entry per plan step, each with
   `"plan": "<plan name>"`, and run the script. Seen stays where it is.
2. **Building a plan starts**, in the same task or a later one. Before the first step is built,
   run the script with `--seen`, unless I said to keep Seen. Then, as each step is built, correct
   its entry to what was built (file names, signatures) and delete its `plan` key. There is no
   other command for building a plan.
3. **A task ends**, planned or not. Run the script. Answer every error; read every note; run again
   until no error is left, except one that is architecture (see below).
4. **Then commit**, code and `WORK/SYSTEM_VIEW/` together. If the figure, a flow or a listed line
   changed, say so in one line of the hand-off. Do not run the script again after the commit: the
   committed entry stays in `changes.json` until the next task's first run with no option takes
   it out. A run with `--check` or `--seen` leaves it there.

```bash
uv run WORK/skills/tressoir-system-view/system_view.py            # fold, check, build the page
uv run WORK/skills/tressoir-system-view/system_view.py --check    # only print the checks
uv run WORK/skills/tressoir-system-view/system_view.py --seen     # I have seen everything up to the last commit
uv run WORK/skills/tressoir-system-view/system_view.py --from <commit>   # also show a delta from that commit
uv run WORK/skills/tressoir-system-view/system_view.py --check --flows   # also print each flow, and each flow a plan changes, with the calls found
uv run WORK/skills/tressoir-system-view/system_view.py --draft <file>.json   # a page from a draft, beside it (see "Starting")
```

It needs only Python 3 and git; `python3` works in place of `uv run`. A run with `--check` that
finds no error ends with `Checked: … No error.` Once the last commit holds a
built entry, the next run takes it out of `changes.json` by itself: a built and committed change
reads as if it was always there. "Holds" means the commit has the entry unchanged and its
`system.json` already says what the entry states, so an entry committed before the script ran
stays for one more commit. Work that goes on in the same files after that commit needs an entry
of its own. Seen is the last commit that existed when the building of the current plan
started, so that its tab shows what the task has done since. Move it only when the building of
a plan starts, when the first figure is committed, or when I say so. A plan that is only
written does not move it, and when I say to keep Seen, it stays.

A file in a shape the script cannot read (a list where an object belongs, text where a list
belongs, a file not saved as UTF-8) stops it with one sentence that says what to write. Nothing
is folded until that is corrected.

What the script prints:

| Error: the entry is not folded | Note: only said |
| --- | --- |
| a changed file under the figure that no entry explains (it prepares an entry, with the flow of each function it names) | a file under a region that belongs to no box (an empty file, such as a package marker, is not counted) |
| a name in `affects` found nowhere, or in two boxes | a listed name that appears nowhere in its box's code |
| a built entry's file that does not differ while its other files do | a planned entry that looks built |
| a built entry with a `+ ` file that does not exist | an entry changes a function that has a flow and does not state the flow: check it still reads true |
| a planned path that does not exist and has no `+ ` | an open plan restates a line that has changed since the last commit |
| a name twice in a box; a path in two boxes; a bare name with no single match | an entry replaced a line: what it was, what it is |
| a new box the script will not place: inside a box that holds no modules, deeper than a row, or where regions share the folder | a link or a neighbour that points at nothing |
| a box with no file left whose files were renamed (it proposes the `moves` line) | a box with no file; a figure whose regions give no folder |
| a flow of a function no box lists; two flows of one function; in `system.json`, a flow with no line or still written as steps | a box removed because its files were deleted; a function removed with its flow |
| a call stated by hand in a sketch that names no listed function | a call in a sketch into a box that does not list it, or that two boxes answer to |
| `moves` to another region or row, onto or into another box, or of a box with boxes inside | a sketch that began with its `def` line (the script takes it out); a sketch over 40 lines |
| `renames` of a function no box lists, or to a name its box already lists | two entries state the same flow: the later one stands |
| a flow of an interface's method | a parenthesis that names a type no box lists as an interface or a class; a method listed in another box than its type |
| a box three levels deep, written or planned; an `inside` that lists both modules and rows; a plan's name over 24 characters (these stop the script) | an earlier entry named a box at the path a later entry moved it from: the script corrects the entry |
| | a new folder with no words in `lines.json`, beside folders that have some |
| | a type that a listed line names and no box lists: list it, unless it is a library's |
| | a box, a listed function, a method or a listed type of any kind with no words; a step of a flow with no words: write them, in the task's entry or, while the figure is being written, in `system.json` |
| | no box written yet |

Reading a diff:

| In the diff | In the entry |
| --- | --- |
| a changed, new or removed file | a line under `files` |
| an edit inside a listed function, or in private code a listed function reaches | the name in `affects` |
| a listed signature changed, a new function another box calls, a new command | the line under `interface` |
| a listed line's words, or a box's `line`, no longer true | restate it |
| the steps of a function that has a flow changed | the flow, whole, under `flows` |
| a box's folder or file renamed, the box otherwise the same | `moves`, old path then new path |
| a listed function renamed, otherwise the same | `renames`, the function then its new name |
| a new folder inside a box that holds no modules | nothing |
| a new folder directly in a row, a region or a box that holds modules | a box under `boxes`, with a name and a line |
| a new file in a flat project | `also` on the only box that imports it |

**Architecture is never decided mechanically:** a new row or region; a box that changes region,
splits or merges; a box that gains its first module, or a view of its own; in a project whose code is one folder, a new box, or
a file that two boxes import; a function that gains or loses a flow. Leave the figure alone and
tell me in your report. An error that is architecture stays until I have answered: commit the code with the
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
2. **Inside a box.** `inside` lists the modules a box holds: each is a box like any other, in a
   folder inside its folder. That is all it takes. They are listed under it and drawn inside its
   box, in the figure the box is in; one that is only a variation is listed and not drawn (see
   "A module may hold modules"). Only a subsystem of a large system has a view of its own
   (see "One overview, unless the system is large"): its `inside` then lists rows instead, each
   an object with `boxes`; a row is a folder and its boxes are folders in it. Such a box may give
   `links` between its rows, and `from` and `uses`: the outside boxes it works with, each with a
   sentence.
3. **Interface.** One string per line. A function is `name(arg: Type) → Type  // words`; a type
   is `Name = shape  // words`, `interface Name  // words` or `class Name(Parent)  // words`. See
   "Three kinds of type" below.
4. **Flows.** A flow is the body of one listed function, as a short sketch: `of` (the box's
   folder, a colon, the function) and `sketch` (its lines). See "Flows" below.

Boxes go two levels deep and no more. A box of the overview may hold boxes, directly or in the
rows of a view of its own; a box inside it holds none, and the script stops on a third level. The
rows of a view only group its boxes in the figure, as the regions group the overview's: a row is
not a module and lists nothing.

**A module may hold modules, and stays an ordinary box.** When a module is made of parts I would
name, each in a folder of its own, list them in its `inside`: a Devices module with macOS, Android
and Windows; a Connectors module with a module per provider. The outer module lists what the rest
of the system uses (the interfaces, the functions), each inner module what is its own (its
classes). Do not leave such modules out of `system.json` to keep the figure simple, and do not
turn the module into a subsystem with rows and a view to be allowed them.

The figure draws an inner module only when it has a job of its own. One that is a variation on a
common interface (every line it lists is a class with a parent: macOS, Android and Windows under
Devices) is listed under the outer module and not drawn: the outer box is enough for me. The
script decides this from the listing; there is nothing to mark.

**One overview, unless the system is large.** Most projects are drawn whole in the overview, and
no box has a view of its own. A box gets one only when it is a subsystem of a large system (a
database's optimizer, an operating system's scheduler): it has several groups of parts, each a
folder I would name, so its view has several rows. Or when I ask for one. A box whose view would
be a single row is not a subsystem: list its modules directly, and they are drawn in the
overview.

**Complete, or not shown.** A figure that names things it does not explain confuses me more than
it helps. Prefer a complete view to a quick one:

- Every type a listed line names is itself listed, in the box that owns it, with its words and its
  fields or methods. The exceptions are the language's own types, a library's, and the names of
  the cases of a choice (`Mode = Fast | Slow`). The script names the others.
- An interface is listed with its methods, and with every class that implements it. A project
  that runs on macOS, Windows and Android shows all three, not the one that was written first.
- A module that exists in the design is in the figure, with its listing. A box with an empty
  listing beside boxes that have one reads as forgotten.
- When part of a design is not decided yet, do not list half of it. Say in the box's line that it
  is open, and ask me.

**An interface that is hard to describe is a finding.** When I cannot say in one line what a
module, an interface or a type is for, or its methods will not come out as a short list with
clear types, the abstraction is probably wrong: it does two jobs, or the boundary is in the wrong
place. Do not paper over it with vague words or leave it unlisted. Write what is true, and tell
me what was hard to describe and what would make it simple: it is a chance to improve the
design, and that is mine to decide.

- A box has `name`, `folder` and `line`. `folder` is its main path and its identifier everywhere.
  In a project whose code is flat it may be a single file, and `also` lists further paths. A file
  belongs to the box with the longest matching path, so a box may claim one file inside another
  box's folder; the same path is never written on two boxes.
  `"shared": true` marks the one box of helpers with no better home.
- A box lists what other boxes call. An entry box lists its entry points: commands, routes.
  A function that callers reach through a module of the box is written with that name
  (`youtube.minutes`). A constant or the value of a setting is not listed; a function that
  returns one is.
- Names are spelt as in the code. Where the code has no single name (a command, a route), choose
  one; the note that it appears nowhere is then expected. The name of a line is its first word, so
  two routes cannot both start with `GET`: write `get_users  // GET /users, lists the users`.
- A type is written in the box that owns it. It is one of three kinds: see below.
- Every line has words after `//`: a function says what it does for its caller, a type what it
  stands for. A type with no words is as bad as a function with none. The script names each
  listed line and each box that has no words, and the page shows no docstring for it.
- A bare name (`"lookup"`) is the function of that name from a box inside, and must match exactly
  one. A parent never writes out a signature that an inner box lists.
- A name appears once per box; a type once in the file.
- Tests, documents and scripts are in the file view and are never boxes.
- Write types as the examples do: `[T]` is a list, `T?` may be absent, `{T}` is a set, `(A, B)`
  a pair, `A | B` one or the other, `→` (or `->`) gives the result. The page shows every
  signature as Python (`def`, `list[T]`, `T | None`), whatever the project's language. Turning a
  C or Rust signature into such a line is yours to do; keep the project's own names for types
  (`str` and `int` in a Python project, `u64` in a Rust one). Leave out default values and
  keyword markers. An argument the code gives no type may stand bare (`run(client, db)`), or
  carry the type it holds.

### Three kinds of type

```json
"interface": [
  "Batch = { columns: [Column], rows: Int }  // a few thousand rows, held by column",
  "interface Operator  // anything that hands out batches: a scan, a join, a sort",
  "Operator.next() → Batch?  // the next batch, or nothing when the input is finished",
  "class Sort(Operator)  // orders its input, on disk when it does not fit in memory",
  "Sort.spill()  // writes the sorted runs held in memory to disk"
]
```

- **Data** is `Name = shape`: a record, an alias, a choice between values. It says what a value
  holds.
- **An interface** is `interface Name`: what something can do, with no code of its own. A
  protocol, a trait, an abstract base class and a set of callbacks a module is handed are all
  written this way. A capability is an interface, never a record whose fields are functions.
- **A class** is `class Name`: something with code and state of its own that another module holds
  or calls. What it implements or extends goes in a parenthesis, as in Python:
  `class Sort(Operator)`, `class TopN(Sort)`. A class no other module names is private detail and
  is not listed.
- A method is a line of its own, in the same box, named with its type in front:
  `Operator.next() → Batch?  // words`. It is a function line like any other: it has words, it
  goes under `affects`, `renames` and `interface` in an entry by that name, and a class's method
  may have a flow (`"of": "<box folder>: Sort.spill"`). List the methods a caller uses, not all of
  them. A class does not list again a method it only inherits or implements unchanged. Fields are
  not listed.
- Write them as the code has them. A type is an interface only when the code has one (a
  protocol, a trait, an abstract class, a table of functions); do not invent an interface or a
  parent to make the figure tidier. A parenthesis names only types the figure lists.
- The page shows the three apart, each with its methods under it.
- Under every open type one line opens, on a click, onto who implements or extends it and where
  it is used: the listed functions that return it, the ones that take it, and the types it is a
  part of. The page collects this from the parentheses and the signatures, so a signature must
  name the types it passes; do not write "returned by" or "implemented by" in the words.
- `- Name` in an entry removes an interface or a class with its methods and their flows.

### Flows

```json
{ "of": "src/core/transactions/durability/commit/: commit",
  "sketch": [
    "conflicts.check(txn)  # fails when another transaction wrote the same row first",
    "at: Timestamp = next_timestamp()  # the commit time fixes the order other transactions see",
    "lsn: Lsn = wal.append(records_of(txn, at))  # the changes are appended to the log",
    "wal.flush_group(lsn)  # one flush serves every commit waiting in the group",
    "replicas.ship(lsn)  # the other nodes receive the log",
    "return at"
  ] }
```

On the page the function carries a small mark; opened, its line becomes this sketch, and each
line that has words or calls a listed function opens in turn.

- `of` names the function: its box's folder, a colon, its name. That box must list it. (The
  box's name in place of its folder is read too; the script writes the folder.) A function has
  one flow. Do not write the `def` line: the page writes it from the listed signature. Where
  two listed functions share one body (two commands that run the same pipeline), give the flow to
  one and say in the other's words how it differs.
- The sketch is Python, whatever the project's language: assignments, typed where the type helps,
  `if`, `for`, `while`, `with`, `return`, four spaces a level. Two additions: `parallel for x in
  xs:` for work done at once, and `xs.where(test)` for a filter. Keep the project's names, a
  private helper's leading underscore included.
- One line per step I would name on a whiteboard. Leave out error handling, logging and private
  detail that explains nothing. A flow is a sketch, not the code.
- The words after `#` say why the step is there or what it decides. I read them when I open the
  line. Do not repeat the code in words. Every step has them. A line that says itself may go
  without: one that only opens a block (`if`, `for`, `else`), one that returns a name, `break`,
  `continue`, `pass`, `raise`. The script names the other steps that have none.
- A call into another box is written `box.function(...)`: `box` is the last part of the box's
  folder or its name, as an identifier (`wal`, `join_order`, `write_ahead_log`), and `function`
  is a line that box lists. A box inside another may be reached through its parent when the
  parent lists the bare name (`transactions.snapshot(...)`). A call to a listed function of the
  flow's own box is written bare. A function listed with a module in front is called as it is
  listed (`recency.is_recent(item)`). A listed function handed on without being called counts
  too (`items.where(recency.is_recent)`). The script finds these calls, and the page shows each
  called function under the line, with its box. Private helpers and library calls are written
  bare, as the code has them, and are not looked up.
- A call on a variable is found when the sketch says what the variable is, and that is a listed
  interface or class: an argument of the function (`source: Operator`), `self` in a method, a
  typed line (`p: Pipeline = …`), the variable of a loop over a typed list (`ps: list[Pipeline]`,
  then `for p in ps:`). `source.next()` is then `Operator.next`, and the page says under the line
  that the class behind the interface answers. A method the class does not list is looked for in
  what its parenthesis names. Type the variable where the call matters; do not type every line.
- An interface's method has no flow: it has no body. Give the flow to the method of a class.
- Run with `--check --flows` to see which calls the script found on each line. Where it cannot
  tell (two boxes answer to the same word, the call goes through a variable the sketch gives no
  type, a step reaches a function its code does not name), state them by hand: write the line as an object,
  `{ "code": "...", "says": "the words", "calls": ["<box folder>: <function>"] }`.
  `"calls": []` says the line calls nothing listed.
- A called function that has a flow of its own is not written out again: the page links to it.
- Types are named as the interface lists them; the page links each to its card.
- Which functions have a flow is decided with me: the entry points, and the few functions where
  the order of the steps is the design.

### Starting in a project that already has code

Propose the regions and boxes from the code as it is, and settle them with me before going
further. Draw what a system architect would put on a whiteboard: a box is a part with a job of its
own, not a file, and its lines are what an architect needs to know to connect it to the others.
That is around a dozen boxes; a simple project needs fewer, a complex one more. Once the
figure is agreed, add the interface and one or two flows. Draw one overview and give no box a
view of its own, unless the system is large (see "One overview, unless the system is large").
Where a component is spread out, give the box its main folder and list the rest under `also`. Leave
`changes.json` as `[]`. Do not move code to make the first figure look tidy.

**Show me a figure before it is agreed as a draft.** Write it as a `system.json` of its own in
the task's artifacts, never in `WORK/SYSTEM_VIEW/`, and build its page with `--draft <file>`: the
page is written beside the draft, with one tab, and the project's own system view stays as it
is. The script prints the same notes as for the real one. For a layout the code does not have
yet (a proposed reorganization), list the files it would have, one path per line, and add
`--files <list>`: the file view then shows that layout. Once I agree to a first figure, copy it
into `WORK/SYSTEM_VIEW/system.json`. A reorganization I agree to is not copied there: it is a
plan, written as planned entries.

Where all the code is in one folder (`app/`, say), every region that applies gets that folder, and
a box's `folder` is a file or a folder directly in it, with its other files under `also`, as in
the `pocket/` example. The script then cannot tell which region a new box belongs to, so a new
box is mine to place.

Write `lines.json` once at this point, a few words per source file; later the script follows
renames and adds a new file's words from its entry, when the entry leaves `changes.json`; a new
folder's words are yours to add. Commit the first figure, then run the script with `--seen`: the
first figure is the first thing I have seen. The `seen` file goes in with the next commit.

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
Restructuring is mine to decide. The same holds for a part that is hard to describe (see "An
interface that is hard to describe is a finding"): say so, propose the simpler shape, and wait.

## This is experimental

When any of these happens, add a dated line to `WORK/SYSTEM_VIEW/FEEDBACK.md` saying what happened
and what would have helped:

- the files made you write something awkward, or the same thing twice;
- the script reported something wrong, unclear or useless, or its proposal for `affects` was off;
- the project's layout fought the view;
- I commented on the view or on this skill.

Do not patch this skill, its script or its page inside the project. They belong to the kit and are
replaced on the next refresh. The feedback is collected from time to time and applied to the kit.
