---
name: tressoir-migrate
description: Move a project from the first Tressoir kit (an IB/ folder, canon, .tressoir files) to the current one (WORK/, memory, briefings). Use once per project when I ask to migrate or upgrade the kit. Temporary: delete this skill when no project with the old layout is left.
---

# Migrating a project to the current kit

One git repository at a time, in the order below. What changes:

| First kit | Now |
|---|---|
| `IB/` | `WORK/` |
| `IB/TRESSOIR.md` | `WORK/WORK_AREA_GUIDE.md` |
| `IB/CANON/ROOT_CANON.md`, `<SUBJECT>_CANON.md` | `WORK/MEMORY/ROOT_MEMORY.md`, `<SUBJECT>_MEMORY.md` |
| `IB/CANON/CANON_ARTIFACTS/` | `WORK/MEMORY/EXAMPLES/` |
| `IB/REPOS/<child>` | `REPOS/<child>`, at the top level |
| `.tressoir.md`, `.tressoir.html`, `interactions.json` | retired, not converted; results come back as briefings |
| skills `tressoir-working-area`, `tressoir-canon`, `tressoir-artifact-md`, `tressoir-artifact-html` | `tressoir-memory`, `tressoir-present` |

Do not read or edit any `TASK.md` along the way; moving it with its folder is fine.

## 1. Preflight

- The working tree must be clean. If it is not, stop and ask me. Never stash or discard my work.
- Work on a new branch, `migrate-work-area`. Note the commit you start from: that is the
  checkpoint.
- Take an inventory without changing anything, and tell me what it found before going on:
  - old-format files that git tracks, and separately those git ignores, since a commit does not
    protect ignored files:
    `git ls-files | grep -E '\.tressoir\.(md|html)$|interactions\.json$'`, and the same filter on
    `git ls-files --others`;
  - every mention of the old names: `git grep -nIE '(^|[^A-Za-z_])IB/|CANON|TRESSOIR\.md'`;
  - `.gitmodules`, links pointing into `IB/`, editor and dev-container settings;
  - anything outside the repository that may hold an absolute path into `IB/`: toolchains,
    virtual environments, installed apps, scheduled jobs;
  - nested projects: child repositories, and work areas that are not at a repository root.

## 2. Retire the old-format files

Ask me once for the whole project. The default: commit everything, tag that commit
`before-work-area-migration`, then delete the `.tressoir.*` and interaction files from the working
tree with `git rm`. Nothing is converted. List ignored old-format files separately and ask what to
do with them, because the tag does not hold them. A plain `PLAN.md` next to a retired
`PLAN.tressoir.md` stays.

## 3. Rename the folder and fix what points at it

`git mv IB WORK` moves the folder with everything in it, ignored files included. Then fix every
reference that something still follows: `.gitignore`, `.gitmodules`, links under `.claude/skills/`
and `.agents/skills/` (re-point each to `../../WORK/skills/<name>`), editor and dev-container
settings, scripts, the README, and paths inside `WORK/STATE.md` and memory. The root guidance files
are handled in step 6.

Leave two kinds of mention alone and name them in your report: history (old reports and archives
say what was true then) and subject matter (a project that is about these names, such as one
describing Tressoir itself).

## 4. Canon becomes memory

`git mv WORK/CANON WORK/MEMORY`, then rename `ROOT_CANON.md` to `ROOT_MEMORY.md`, each
`<SUBJECT>_CANON.md` to `<SUBJECT>_MEMORY.md`, and `CANON_ARTIFACTS/` to `EXAMPLES/`. Fix the links
and headings inside them. The entries themselves do not change.

## 5. Child repositories

Report what you find and ask me before moving anything: children with uncommitted work, a child
with no work area of its own, a child whose state is kept in the parent, a work area that is not at
a repository root. Then create `REPOS/` and, for each child I agree to move,
`git mv WORK/REPOS/<child> REPOS/<child>`, which updates `.gitmodules` too. A child is migrated separately, from its own root; here the parent
only moves it and keeps one pointer line for it in `STATE.md`.

## 6. Swap the skills

Run the kit's installer with `--override` from the project root. It installs the guide and the
current skills, removes the first kit's four retired skills and their links, replaces the first
kit's pointer in `AGENTS.md` and `CLAUDE.md` with the new one, and leaves everything else in those
files. It refreshes `tressoir-structured-review` and `tressoir-isolation` only where the project
already has them.

## 7. Rewrite the kit's part of `STATE.md`

State usually describes the old layout: where things live, which skills exist, how results are
shown. Bring it up to date, harvesting before pruning:

1. Copy `STATE.md` to `WORK/ARTIFACTS/ARCHIVES/STATE/<date-time>.STATE.md`.
2. Sort each item that is about to go: memory (still useful in a month), stays, a one-line pointer,
   or drop. When unsure, keep. My standing instructions go to memory, close to verbatim, dated.
3. Write memory first. Only then rewrite state, with one line recording the migration and the tag.
4. Tell me what moved where.

## 8. Verify

- Search for leftovers:
  `git grep -nIE '(^|[^A-Za-z_])IB/|CANON|\.tressoir\.|TRESSOIR\.md|interactions\.json' -- . ':!WORK/ARTIFACTS/ARCHIVES'`.
  Every hit is fixed, or named in the report as history or subject matter.
- No broken links: `find . -type l ! -exec test -e {} \; -print` prints nothing of ours.
- From `AGENTS.md` alone, a new session reaches the guide, the state and root memory.
- Commit on the branch. Do not merge, push or delete the tag without asking me.

Hand off with a briefing: what moved, what was retired and under which tag, what was left alone
and why, and anything that remains.

## If a step cannot be done safely

Do the steps that are safe. If the rename is the blocked one, usually because something outside the
repository holds an absolute path into `IB/`, leave a temporary link named `WORK` pointing at `IB`
so the new guide and skills resolve, and run the installer as in step 6. Record in `STATE.md` what
remains and why. If the project would be left worse than it started, go back to the checkpoint
commit and tell me what stopped you.
