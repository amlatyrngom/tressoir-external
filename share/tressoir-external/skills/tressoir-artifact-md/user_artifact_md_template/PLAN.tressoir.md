---
title: Plan title
description: One line — what this changes and why.
---

Open with two or three sentences: the problem, the proposed direction, and what you need from the human. Replace every placeholder below.

## Executive Summary

### Goal

State what success looks like in one or two sentences.

### Approach

:::item{oneliner="A complete, skimmable claim about what changes and where."}
Put rationale, boundaries, and edge cases behind this reveal.
:::

## Requested Decisions

:::input{key=area.decision}
What immediate choice must the human make?

- Option A *(recommended)* — explain its immediate effect.
- Option B — explain its immediate effect.

Type a pick, tweak, or question.
:::

## Milestones

::::card{title="M1 — First coherent implementation chunk" oneliner="Describe the concrete result in plain language." state="<span class='badge warn'>Planning</span>"}
#### Planning Overview
:::item{oneliner="Describe what changes and where — name the file or subsystem."}
Explain rationale, boundaries, and important edge cases.
:::
#### Planned Changes
:::item{oneliner="Show the concrete edit — path/to/file · symbol()."}
```diff
@@ path/to/file — symbol() @@
- before
+ after
```
:::
::::

::::card{title="M2 — Dependent chunk" oneliner="Detail this after its prerequisite is resolved." state="<span class='badge muted'>TBD</span>"}
#### Planning Overview
:::item{oneliner="Deferred until the requested decision is resolved."}
A TBD milestone carries no Planned Changes until it is promoted to Planning.
:::
::::
