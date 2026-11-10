---
name: tressoir-plan
description: Plan work that needs my decision before implementation. Use for substantial design or implementation where the approach, the scope or a hard-to-undo step is mine to choose.
---

# Planning

Plan when the work is substantial and something in it is mine to decide: the approach, the scope,
a trade-off, or a step that is hard to undo. Small or obvious work needs no plan; do it and tell me.

If the central approach is still open, bring me the realistic alternatives and a recommendation
before writing a detailed plan around one of them.

## The plan page

A plan is one reference page, `PLAN.html`, in the task's folder under `WORK/ARTIFACTS/`. There is no
Markdown twin. Agents work from this page, so keep it correct and current; assume I will not open
it. In this order:

1. **Summary**: the goal, the chosen approach and its boundaries, in about a screen. Add a diagram
   when structure matters: components, a flow, a folder layout.
2. **Open decisions**, each in the decision shape: a short name, the question, two or three named
   options with what each leads to, your recommendation, and what happens if I say nothing. When I
   answer, replace it with one line recording the decision and the date.
3. **Milestones**: each with a human-readable name, what it delivers, how it will be checked, and
   a plain status: not started, in progress, or done.
4. **Detail**: whatever an agent needs to carry the work out: interfaces, files, risks, evidence.

There is no page template. Write plain HTML, laid out as the content needs. The colour variables in
`WORK/skills/tressoir-present/slides.css` can be reused so pages and briefings look related.

## The loop

1. Research enough that the plan is not naive. Disposable evidence goes in `WORK/TMP/`.
2. Write `PLAN.html`, then hand it to me as a whole briefing (`tressoir-present`). The briefing
   carries the decisions; the page is the reference behind it.
3. Do not implement a part before the decisions it depends on are agreed. Parts that depend on
   nothing open can go ahead.
4. When I answer, update the page first, then build.
5. Later hand-offs on the same plan are update briefings: what changed since the last one.
6. Record decisions and milestone changes in `WORK/STATE.md` as they happen.

## Completion report

When a milestone or the whole plan is done, the page says for each milestone:

- **What landed**: the actual behaviour and where it lives.
- **What differed** from the plan, and why.
- **How it was checked**: commands or observations with their results, and what is still unchecked.

Then give me an update briefing that says the same, briefly.
