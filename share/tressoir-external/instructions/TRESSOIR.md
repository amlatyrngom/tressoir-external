# Tressoir Working Agreement

`IB/` means **Interpretable Blueprint**: the project-local, human-inspectable workspace shared by agents, harnesses, and sessions. This file is the canonical always-on guide. Setup may register it in root `CLAUDE.md` and/or `AGENTS.md` only when the user explicitly accepts the root-guidance prompt; otherwise the user decides whether and how to reference it.

## Start and maintain work

1. Read `IB/STATE.md` before substantial work when it exists. It contains current decisions, constraints, progress, and active artifact pointers.
2. `IB/TASK.md` is not an automatic startup file. Read or edit it only when the user explicitly asks, and only at the relevant point in the work. The same rule applies to a plan-local `TASK.md`.
3. Keep `IB/STATE.md` current at decision and milestone boundaries. When it grows to roughly 16,000 characters, proactively condense it toward 8,000: preserve current decisions, constraints, validation, and next steps; replace completed chronology with grouped summaries.
4. Put durable, reusable outputs in `IB/ARTIFACTS/` and disposable logs, screenshots, dumps, downloads, and experiments in `IB/TMP/`.
5. Preserve existing project files, harness instructions, skills, and user-authored IB content. The only setup exception is an explicitly requested, idempotent `# Tressoir Guidance` section in root `CLAUDE.md` and/or `AGENTS.md`; report unsafe targets rather than replacing them.

Treat each upper-case directory under `IB/ARTIFACTS/` as a reusable workspace for one broad task. Keep its initial plan, later `<STEP>_PLAN.md` + `<STEP>_PLAN.tressoir.md` pairs, explainers, research, and artifacts such as `NEXT_INTERACTIVE.tressoir.md` together. Create another folder only for a genuinely separate workstream or when the user requests one.

## Cautious subagent usage

Prefer doing work directly and synchronously. Use subagents only for reviewers at or before important milestones, or for parallel research/investigation divided into chunky domains—not fine-grained fragments. Always use high-end agents; if a task seems suited only to a low-end agent, do it yourself instead.

## Communication and solution shape

- Use clear, user-friendly language in artifacts, code comments, and chat. Prefer plain, intuitive wording; expand uncommon acronyms and avoid unexplained internal shorthand.
- For MVP work, avoid needless complexity. Prefer the smallest intuitive, interpretable solution that fully meets every requirement and preserves important constraints.

## Skills — read the matching one before the work

All portable skills live under `IB/skills/`:

- **`tressoir-working-area`** — use `TASK.md`, `STATE.md`, `ARTIFACTS/`, and `TMP/`; perform working-set upkeep.
- **`tressoir-artifact-md`** — author or revise projected `.tressoir.md` plans, research, reviews, and decision surfaces; use its template folder and checker.
- **`tressoir-artifact-html`** — author raw trusted HTML/CSS/JavaScript artifacts and use their contained interaction API.
- **`tressoir-plan`** — create the `PLAN.md` + `PLAN.tressoir.md` pair, collect decisions, and maintain milestone completion reports.
- **`tressoir-memory`** — promote durable lessons into `CANON/`, split and realign growing canon, and reconcile canon after merges.
- **`tressoir-structured-review`** — review non-trivial plans or changes with the Tressoir verdict and finding classifications.

The Markdown artifact resources are:

```bash
ls IB/skills/tressoir-artifact-md/user_artifact_md_template/
node IB/skills/tressoir-artifact-md/scripts/check_md.js path/to/file.tressoir.md
```

Copy the relevant template files into the existing broad-task artifact folder and rename them for the requested step or surface; never overwrite an occupied path. The checker requires Node but no installed npm packages.

## Memory and upkeep

Consult `IB/CANON/ROOT_CANON.md`, then only relevant subsystem canon. At natural milestones, proactively promote stable decisions, invariants, constraints, conventions, and validated techniques from `STATE.md` or active artifacts into canon. Do not promote transient debugging or status chronology.

When canon becomes duplicated, stale, contradictory, or hard to retrieve, use the `tressoir-memory` realignment workflow: reconcile against current source and accepted intent, deduplicate, remove obsolete chronology, split large mixed-domain files, update the root index, and keep durable guidance timeless. After promotion, shorten `STATE.md` and avoid leaving canon dependent on temporary artifacts.

## Merge and rebase reconciliation

For non-trivial merges or rebases, inspect source and IB changes together. Resolve the source according to accepted intent first, then reconcile `STATE.md`, skills, docs, and canon against the merged behavior. Do not line-merge contradictory canon into an incoherent result: retain current guidance, mark useful superseded history, deduplicate equivalent lessons, and ask the user about genuine intent conflicts. Never synthesize or rewrite `TASK.md` unless explicitly requested.

## Normal operation

Work end-to-end unless the user requests a checkpoint, a design decision is genuinely blocked, or the active plan forbids implementation. Treat live user and IB edits as normal collaboration; do not infer a stop request without a clear instruction.
