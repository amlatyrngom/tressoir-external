---
name: tressoir-present
description: Give results back as a narrated slide briefing. Use after non-trivial work, when asked to answer or explain in a briefing, when asked to be caught up, or while briefing mode is on.
---

# Briefings

I take in results by listening to narrated slides, not by reading documents. A briefing is a short
slide deck with spoken narration, made for me at one moment. It is how I learn what happened and
what I need to decide.

## The one rule

A briefing stands alone. From it alone I must understand the situation and be able to answer every
decision it asks for. Do not send me to the plan or reference page to fill a gap the briefing
left: if a detail matters, it is in the briefing; if it does not, leave it out. Recommending that I
read something is fine when reading it is itself the advice, such as a paper worth my time.

## Level

Brief me the way an engineer briefs a manager who is an architect, or the way I would brief my
advisor. They hear what exists now and what it lets us do, how sure we are and on what evidence,
what is still at risk or not done, and what they must decide. They do not hear how the work was
done.

- Leave out the workings: file formats and the names of keys or options, the defects found and
  fixed along the way, counts of checks, attempts that were dropped, and the choices that were
  yours to make. Write those in the task's artifacts, where the next agent finds them. I will ask
  when I want more.
- Keep a detail only when it changes a decision the briefing asks for, changes what I do next,
  or would surprise me to learn later.
- Evidence is a sentence or two: what was tried, on what, and what happened.
- A choice of yours that changes what I will see or how I work, and that I could well have made
  differently, is a decision: give it a decision slide whose default is what you chose. There
  are few of these. The rest are not mentioned.
- Besides the summary, the decisions and the recap, one or two slides are usually enough.

The test for any slide or sentence: would I say this to my advisor?

## Kinds

- **Whole**: everything that matters about one subject as of now. Make one the first time a
  subject is presented, and whenever I ask to be caught up or ask for a consolidated briefing.
- **Update**: what changed since the last briefing on the subject; say which one. Give each
  important change its own slide: what it was, what it is now, why, and what follows from it. Put
  small confirmations together on one slide. Depth follows importance.
- **Answer**: a reply to a question, with or without any document behind it.

A briefing can be about a plan, a report, a code change, research, or nothing on disk at all. When
there is a reference page, keep it current and correct, because agents work from it. Assume I will
not open it.

A delivered briefing is never edited. When things change, make an update.

## When

- At a non-trivial hand-off: a plan, a finished milestone, findings, anything that would otherwise
  take me more than about a screen of reading.
- When I ask for a briefing, or ask for an answer as a briefing.
- **Briefing mode**: when I say to answer through briefings, every reply with substance is a
  briefing until I say stop. Keep these small; one or two slides is fine.

Short factual replies stay in chat.

## Labels

When you name a decision, an option, a milestone, an experiment or a file, try for a
human-readable label that is easy to remember and mostly tells me what I need to know on its own,
even several days later.

## Writing one

- Slides carry what is hard to say aloud: structure, names, numbers, comparisons, diagrams.
  Narration carries the reasoning and says what to notice. Do not read the slide aloud.
- Narration must make sense heard without the screen. Plain spoken sentences; start with the point.
- Mark a dense slide `data-hold` and say it is worth a pause.
- Be as short as the content allows: a minute or two for an update, a few minutes for a whole
  briefing. Split a long one.

## Decisions

What needs my input always looks the same, wherever it appears. The rest of the briefing is yours
to shape.

- **Open with the summary**: where things stand, with a diagram when structure matters, and how
  many decisions are waiting, by name. If nothing is needed from me, say so.
- **One decision, one slide**, in the decision shape shown below: a short name for the decision,
  the question, two or three options each with its own short name and what it leads to, your
  recommendation marked quietly, and what happens if I say nothing.
- **Put each decision where I am ready for it.** A simple one can come straight after the summary.
  One that needs background comes right after the slides that give that background, and only as
  much background as the decision needs.
- **Close with a recap slide** listing every decision by name with your recommendation, so I can
  answer in my own words or say "all recommended".

The reference page uses the same shape: summary first, then open decisions, then detail.

## Making one

Write `<date-time>-<name>.slides.html` in the task's `briefings/` folder (or `ARTIFACTS/BRIEFINGS/`
when there is no task). There is no template: lay each slide out as its content needs, with a
`<style>` block in the file's head if you need one. The shared styles give you the colour
variables, type sizes on a 960 by 540 slide, and the decision slide.

```html
<section class="slide" data-title="Chapter name" data-hold>
  ...slide content...
</section>
<aside class="say">What is spoken for this slide.</aside>
```

A decision slide adds `data-decision` and uses this shape:

```html
<section class="slide" data-title="Decision: short name" data-decision>
  <span class="ask">Decision · Short name</span>
  <h2>The question, in one line?</h2>
  <div class="options">
    <div class="opt rec"><h3>First option<span class="recmark">Recommended</span></h3><p>What it leads to.</p></div>
    <div class="opt"><h3>Second option</h3><p>What it leads to.</p></div>
  </div>
  <p class="default">If you say nothing: <b>First option</b>.</p>
</section>
```

Then build it:

```
uv run WORK/skills/tressoir-present/present.py <file>.slides.html
```

This narrates each slide (cached, so unchanged slides cost nothing) and bundles slides, audio and
the player into one self-contained `<file>.html` beside the slides file. Nothing else is needed to
view it. If it warns that the file is near 2 MB, split the briefing. The first build on a machine
downloads the voice model, about 350 MB. If the script says something is missing, tell me what.

- `--voice heart` or `--voice harper`: only when I ask for a different voice. The default is the
  local voice `george`. `harper` uses Azure; if credentials are missing, ask me for them and never
  look for them in other projects.
- `--mp4`: also write a video, for sharing with someone else.

## Handing off

In chat, say in a line or two what the briefing covers, then end with:

```
Open: <path to the .html file>
Decide: <decision names>
```

Do not repeat the briefing's content in chat. Where the harness can show an HTML file inline, show
it there; otherwise I open the file in a browser.
