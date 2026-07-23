---
name: tressoir-plan
description: Create, review, and maintain a paired PLAN.md and PLAN.tressoir.md for substantial work that needs human decisions or approval before implementation.
---

# Tressoir Planning

Use this workflow for substantial design or implementation that needs a human checkpoint before code changes.

A plan is a pair in one sticky upper-case folder under `IB/ARTIFACTS/`:

- `PLAN.md` — verbose agent-facing source of truth.
- `PLAN.tressoir.md` — concise human-facing projection.
- `TASK.md` — optional human-only scratchpad; do not read or edit automatically, only on explicit user request at the relevant point.
- `interactions.json` — human answers written by the artifact editor.

The human is never expected to open `PLAN.md` or any other agent-facing source; every decision, change, caveat, and result they need must appear in `PLAN.tressoir.md`.

Read the `tressoir-artifact-md` skill before authoring the projection.

The folder belongs to the broad task, not only this plan. Reuse it for explainers, research, interactive artifacts, and later user-requested subplans. Name a later pair for its step, such as `MIGRATION_PLAN.md` + `MIGRATION_PLAN.tressoir.md`, rather than creating a new artifact folder. A surface such as `NEXT_INTERACTIVE.tressoir.md` can be another sibling. Create a new folder only for a genuinely separate workstream or when the user requests it.

## Intent-first when the approach is unclear

Do not force a full milestone plan while the central approach is unresolved. First present the intent, open questions, realistic alternatives, and a recommendation. After the human selects the shape, crystallize it into the full structure below.

## Required projection structure

Put these sections first and in this order.

### 1. Executive Summary

Give the mental model in one screen:

- a one- or two-sentence goal;
- reveal items describing what changes and where;
- an architecture diagram only when the system shape genuinely needs one.

### 2. Requested Decisions

Use one `:::input` per unresolved decision with a unique key. Each question must be understandable without internal shorthand and include:

- realistic options;
- exactly one recommended option when a recommendation exists;
- the immediate effect of each choice;
- room for a pick, tweak, or question.

Show only decisions relevant to the current pass. Do not overwhelm the human with speculative second-order branches.

When all decisions are resolved, replace the inputs with a concise accepted-decisions record.

### 3. Milestones

Each milestone is a coherent chunk represented by a card:

```md
::::card{title="M2 — Name" oneliner="What this chunk delivers." state="<span class='badge warn'>Planning</span>"}
#### Planning Overview
:::item{oneliner="What changes, and where — name the file or subsystem."}
Rationale, edge cases, and boundaries.
:::

#### Planned Changes
:::item{oneliner="The concrete edit — path/to/file · symbol()."}
```diff
@@ path/to/file — symbol() @@
- before
+ after
```
:::
::::
```

Lifecycle labels:

- `TBD` — dependency unresolved; one-line overview only.
- `Planning` — detailed changes and named snippets are present.
- `Implementing` — approved work is in progress.
- `Review` — implementation is complete and awaiting human review.
- `Completed` — accepted and validated.

A milestone at `Planning` or later must include `#### Planned Changes`. Every proposed code/config edit must appear as a fenced diff or language snippet under an item naming its file and symbol. Do not narrate a code change only in prose, and do not leave orphan snippets.

When a planned edit introduces or changes a public interface or object lifecycle, also show its parameter and return types, who creates it, who owns it for how long, who consumes it, and the end-to-end request/data flow. Do not add this ceremony to an internal edit with no interface consequence.

## Progressive resolution

Detail only the milestones unlocked by current decisions. Leave a dependent milestone `TBD` rather than inventing precise changes before its prerequisite is chosen.

For a high-stakes decision, it is acceptable to show one executive branch per option. Collapse to the accepted branch immediately after the decision.

## Approval and implementation loop

1. Research enough to avoid a naive plan; keep disposable notes in `IB/TMP/`.
2. Write or update `PLAN.md`.
3. Project it into `PLAN.tressoir.md`.
4. Run `node IB/skills/tressoir-artifact-md/scripts/check_md.js <projection>` and then inspect source/projection agreement.
5. Hand back for human decisions or approval.
6. Read answers from folder-local `interactions.json` or chat.
7. Integrate decisions into both files.
8. Do not implement product code until the relevant milestone is agreed.
9. Mark the milestone `Implementing`, implement it, and validate it.
10. Move it to `Review` with a completion report.

## Completion report

At `Review` or `Completed`, lead the milestone with:

- **What landed** — the actual behavior and files.
- **Drifts, challenges, and unplanned steps** — honest differences from the forward plan.
- **Focused actual diffs** — the most useful named excerpts.
- **Validation** — commands and important observed results.

Keep the original planned changes below as reference. Update `IB/STATE.md` at milestone boundaries.
