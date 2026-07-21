---
name: tressoir-artifact-md
description: Author or revise a human-facing .tressoir.md artifact, including projected plans, research, decision surfaces, directives, interactions, and attention-aware presentation.
---

# Tressoir Markdown Artifacts

Use this skill when a human should review, decide on, or navigate substantial work in a rendered `.tressoir.md` surface stored in the **IB (Interpretable Blueprint)**.

A `.tressoir.md` file is trusted Markdown projected by the Tressoir Artifacts VS Code extension into a locked, attention-aware view. It supports headings, reveal-on-demand cards and rows, decision inputs, highlighted code and diffs, raw HTML/SVG, and an always-present feedback box.

## Choose the right artifact

Use `.tressoir.md` for structured plans, research, reviews, and decision surfaces. Use plain Markdown for lightweight notes. Use `.tressoir.html` only when arbitrary HTML/CSS/JavaScript is genuinely needed.

## Source of truth and projection

For non-interactive work, keep a pair in one sticky, upper-case broad-task folder under `IB/ARTIFACTS/`:

```text
FEATURE/
├── PLAN.md                 # verbose agent-facing source of truth
├── PLAN.tressoir.md        # concise human-facing projection
├── TASK.md                 # optional human-only plan scratchpad
└── interactions.json       # written by the extension
```

The same pairing applies to research, reviews, explainers, or later subplans. Re-project after every material source change and before handoff.

Interactive artifacts may be authored directly as a single `INTERACTIVE.tressoir.md` and extended over time.

A plan-local `TASK.md` is human-owned and optional. Do not read or edit it automatically; access it only when the user explicitly asks and at the relevant point. It differs from `interactions.json`, which is the expected place to collect artifact answers.

An artifact folder is the reusable workspace for the broad task, not a container for only its first plan. Keep the folder for the task's full lifetime and add siblings as the work evolves. For example:

```text
FEATURE/
├── PLAN.md
├── PLAN.tressoir.md
├── MIGRATION_PLAN.md
├── MIGRATION_PLAN.tressoir.md
├── ARCHITECTURE_EXPLAINER.tressoir.md
├── NEXT_INTERACTIVE.tressoir.md
├── DETAILS.tressoir.html
└── interactions.json
```

Create `<STEP>_PLAN.md` + `<STEP>_PLAN.tressoir.md` when the user requests a focused follow-up or subplan. Add another named interactive, research, review, or explainer artifact to the same folder when it belongs to the same broad task. Do not create a new upper-case folder merely because the work enters another phase or needs another human-facing surface. Create one only for a genuinely separate workstream or when the user requests it.

## Frontmatter

```yaml
---
title: Short title
description: One-line explanation of what this is and why it matters.
links:
  - ./theme.css
  - https://example.com/theme.css
---
```

`title` becomes the visible heading; `description` becomes its deck. `links` is optional. Local CSS/JavaScript is loaded from the artifact folder. Remote CSS can be referenced. Remote JavaScript is fetched and cached locally by the extension before loading.

## Directive syntax

Cards use four colons and may contain items or inputs:

```md
::::card{title="M1 — Name" oneliner="A useful summary." state="<span class='badge warn'>Planning</span>"}
Card body
::::
```

Items and inputs use three colons:

```md
:::item{oneliner="A complete, skimmable claim."}
Detailed rationale or evidence.
:::

:::input{key=architecture.choice}
Which option should we use?

- Option A *(recommended)* — immediate effect.
- Option B — immediate effect.

Type a pick, tweak, or question.
:::
```

Allowed lifecycle badge labels for plans are normally `TBD`, `Planning`, `Implementing`, `Review`, and `Completed`. Useful badge classes are `ok`, `warn`, `danger`, `accent`, and `muted`.

Always close directives with the matching colon fence alone on its own line. Cards may contain items; items do not contain items, and cards do not contain cards. Quote attribute values containing spaces.

## Writing rules

- Front-load the goal, approach, requested decisions, and current status.
- Make every `oneliner` meaningful without opening its body.
- Put depth behind reveal rows; do not hide the one fact the human must notice.
- Use plain names rather than unexplained acronyms, ticket codes, or internal shorthand.
- Make each decision self-contained. State its options and the immediate effect of each.
- Tie every fenced code/diff block to an item that names its file and symbol. Never leave an orphan snippet.
- Prefer a named unified diff to prose describing a proposed code change.
- Use inline SVG/HTML only when it genuinely clarifies structure.
- Keep formulas readable; use a local renderer when math is central.

## Reading human input

Each explicit input writes a value under its `key` in folder-local `interactions.json`. An answered input has a non-empty value.

The always-present free-form feedback box writes under:

```text
<artifact-stem>-free_form_feedback
```

For `PLAN.tressoir.md`, the key is `PLAN-free_form_feedback`.

The plain `free_form_feedback` key and keys ending in `-free_form_feedback` are reserved for
runtime compatibility and the automatic feedback box. Never use them as an explicit
`:::input{key=...}` key.

Read `interactions.json` directly on the next turn, integrate answers into the agent-facing source, and re-project. Do not rely on a push notification.

## Template folder and checker

The installed skill includes a starter folder modeled on the Tressoir templates:

```text
IB/skills/tressoir-artifact-md/user_artifact_md_template/
├── PLAN.tressoir.md
├── INTERACTIVE.tressoir.md
├── TASK.md
└── interactions.json
```

Copy only the relevant files into the existing broad-task folder, then rename and edit them for the requested surface. Examples:

```bash
cp IB/skills/tressoir-artifact-md/user_artifact_md_template/PLAN.tressoir.md \
  IB/ARTIFACTS/FEATURE/MIGRATION_PLAN.tressoir.md

cp IB/skills/tressoir-artifact-md/user_artifact_md_template/INTERACTIVE.tressoir.md \
  IB/ARTIFACTS/FEATURE/NEXT_INTERACTIVE.tressoir.md

node IB/skills/tressoir-artifact-md/scripts/check_md.js \
  IB/ARTIFACTS/FEATURE/MIGRATION_PLAN.tressoir.md
```

Before copying, check that the destination is absent; never overwrite an existing source, projection, `TASK.md`, or `interactions.json`. For a projected subplan or other non-interactive artifact, also create its matching agent-facing plain Markdown source. Copy `TASK.md` only when the broad-task folder does not already have one. Treat `interactions.json` as shared folder-local state: preserve an existing file and add no placeholder keys unless the artifact runtime needs them.

The checker loads the same committed projection/lint runtime shipped with this skill. It needs Node 18+ but no npm installation. Run it on every `.tressoir.md` before handoff.

## Manual validation before handoff

Without a dedicated projector checker, inspect the source directly:

1. Frontmatter opens and closes with `---`.
2. Every `::::card` closes with `::::`.
3. Every `:::item` and `:::input` closes with `:::`.
4. Every input has a unique, meaningful `key`.
5. Every card/item oneliner is informative.
6. Every snippet is fenced and named to a file/symbol.
7. The agent-facing source and human projection agree.
8. The artifact opens in the Tressoir custom editor and renders as intended.

## Trust boundary

`.tressoir.md` is executable trusted content, not a sanitized preview. Raw HTML and scripts can run, and declared remote resources can cause network access and local caching. Only open artifacts from trusted authors and workspaces.
