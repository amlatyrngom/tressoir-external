# Work area guide

`WORK/` is this project's shared memory and workspace. Any agent on any harness should be able
to continue from these files alone, so nothing important lives only in chat or in a harness's
private memory.

- `STATE.md`: what is true and in progress now. Read it before substantial work; update it when
  a decision is made or a milestone lands. Keep it short.
- `MEMORY/`: what an agent should still know in a month: my standing instructions, decisions and
  their reasons, techniques that worked. Start at `ROOT_MEMORY.md`.
- `ARTIFACTS/<TASK>/`: durable outputs, one folder per workstream. Never read
  `ARTIFACTS/ARCHIVES/` unless I ask.
- `TMP/`: disposable.
- `TASK.md`: mine. Do not read or edit it unless I ask.

Easy to get wrong:

1. Before removing anything from `STATE.md` or ending a long session, first move what is still
   useful into `MEMORY/`. When unsure, keep it.
2. Use the nearest `WORK/` above the files you are changing. A parent project keeps only a
   one-line pointer to each child.
3. Give me non-trivial results as a briefing (`tressoir-present`), and end a hand-off with `Open:`
   and the file's path and `Decide:` and the names of the decisions waiting on me. When you label
   something (a decision, an option, a milestone, an experiment), try for a human-readable name
   that mostly tells me what I need to know on its own, even several days later.
4. Do the work yourself; use subagents only for independent review or truly parallel research.
   Prefer the simplest solution that meets every requirement. Validate in proportion to risk.

Skills, loaded when the situation arises:

- `tressoir-memory`: consolidating state, reorganizing memory, merges, sub-projects.
- `tressoir-plan`: work that needs my decision before implementation.
- `tressoir-present`: showing me a page or a narrated presentation.
- `tressoir-system-view`, only where `WORK/SYSTEM_VIEW/` exists: every task that changes code.
