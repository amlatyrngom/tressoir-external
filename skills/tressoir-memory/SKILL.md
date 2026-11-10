---
name: tressoir-memory
description: Keep the work area's state and memory in order. Use before shortening STATE.md, before ending or clearing a long session, when memory needs reorganizing, after a merge or rebase that touched the work area, and when work involves a project inside another project.
---

# State, memory and artifacts

The files under `WORK/` are the only memory. Harness-private memory stays off, so anything worth
keeping has to land in one of the places below.

## What goes where

- `STATE.md`: what is true and in progress now. Decisions in force, where each workstream stands,
  what is blocked, the next step, and pointers to the artifacts and memory that hold the detail.
  It is read at the start of every session, so keep it short; past roughly 16,000 characters,
  consolidate it with the procedure below.
- `MEMORY/`: what an agent should still know in a month. My standing instructions, decisions with
  their reasons, constraints, conventions, techniques that worked, facts that were expensive to
  establish. Not progress, not chronology, not "we just did this".
- `ARTIFACTS/<TASK>/`: the durable outputs of one workstream: its plan page, briefings, research,
  scripts, reports. One upper-case folder per workstream, reused for its whole life; small
  unrelated jobs can share one folder. `ARTIFACTS/ARCHIVES/` is cold storage: write to it, and do
  not read it unless I ask.
- `TMP/`: logs, dumps, downloads, experiments. Nothing there is expected to survive.

Memory must not depend on a temporary file. If a rule lives only in a plan or a report, move the
rule itself into memory.

## Harvest, then prune

Do this before removing anything from `STATE.md`, and before ending or clearing a long session. The
order matters: once a line leaves state, nothing else remembers it.

1. **Snapshot.** Copy `STATE.md` to `ARTIFACTS/ARCHIVES/STATE/<date-time>.STATE.md`.
2. **Sort** every item that is about to go:
   - *memory*: still useful in a month;
   - *stays*: still current;
   - *pointer*: finished work whose detail lives in an artifact, kept as one line saying where;
   - *drop*: superseded, or recoverable from git or the artifact.

   When unsure, keep it. My standing instructions always go to memory, close to my own words, with
   the date.
3. **Write memory first**, and check it is on disk.
4. **Only then rewrite state.**
5. **Report** what moved where: what went into which memory file, what became a pointer, what was
   dropped, and where the snapshot is. A few lines in chat are enough.

At the end of a long session, also harvest what exists only in the conversation: decisions I made,
corrections I gave, anything learned the hard way.

## Keeping memory tidy

- `ROOT_MEMORY.md` stays small: what cuts across the whole project, and an index with one line per
  subject file. The rest goes in `<SUBJECT>_MEMORY.md` files: a few coherent subjects, not many
  tiny files.
- Search before adding, and merge into the existing entry instead of appending a second one.
- Write timelessly: what is true and why, not the story of how it was found. Keep a date or a
  source where it helps judge whether the entry still holds.
- Split a file when it mixes unrelated subjects or grows large (roughly 20,000 characters for the
  root, 40,000 for a subject), and update the index.
- When memory has drifted, become duplicated or contradicts itself, reconcile it against the
  current code and my accepted decisions, then tell me what merged, moved or went.

## Examples

`MEMORY/EXAMPLES/` holds things better kept in their own format than described: a known-good
config, script, template or fixture. A file goes there only once it is checked to work, free of
secrets and machine-specific paths, with a line in `EXAMPLES/README.md` saying what it is for, how
to use it and its limits. Until then it stays in `ARTIFACTS/` or `TMP/`.

## After a merge or rebase

Resolve the source first, by what was intended. Then reconcile state and memory against the merged
result instead of merging them line by line: keep what is true now, fold duplicates together, and
ask me when two branches hold intentions that cannot both stand. Never rewrite `TASK.md` as part
of a merge.

## Projects inside projects

- A project is a git repository, and it has exactly one work area, at its own root. Child
  repositories live in the parent's top-level `REPOS/`, next to `WORK/`.
- Use the nearest `WORK/` above the files you are changing. The child owns its state, memory,
  plans and artifacts.
- The parent's `STATE.md` keeps one pointer line per child and nothing about the child's progress.
- Work with no repository of its own stays a task folder under `ARTIFACTS/`. It becomes a project
  when it has source that is built or installed, or when I want it to have its own `STATE.md`.
- Kit skills are copied into each repository. Refresh them by running the kit's installer with
  `--override`.
