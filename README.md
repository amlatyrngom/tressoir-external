# Tressoir starter kit

A small kit for working with coding agents. It does two things:

1. **Shared memory.** State and durable knowledge live in plain files under `WORK/`, so any agent
   on any harness (Claude Code, Codex, Pi) can continue from them.
2. **One way of presenting results.** Non-trivial results come back as a briefing: a short deck of
   narrated slides in one self-contained HTML file.

It is meant for frontier models. The guide is short on purpose, and the skills are about a page each.

## Install

From the root of the project to set up:

```bash
/path/to/tressoir-external/install.sh
```

or, without a checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/amlatyrngom/tressoir-external/main/install.sh | bash
```

The installer asks nothing. It always sets up Claude and the shared agents convention together.
Running it again changes nothing. It has two options:

- `--override` refreshes the files the kit owns: the guide, the kit's skills and their scripts. It
  never touches `STATE.md`, `TASK.md`, anything in `MEMORY/` or `ARTIFACTS/`, or skills the kit
  did not ship.
- `--experimental-system-view` adds the system view, described below. Without it nothing about the
  system view is installed.

## What a project gets

```text
AGENTS.md                 three-line pointer to the guide, the state and root memory
CLAUDE.md                 the single line @AGENTS.md
.claude/skills/           a link for each skill
.agents/skills/           the same links, for the shared agents convention
WORK/
  WORK_AREA_GUIDE.md      the always-loaded guide               (kit)
  STATE.md                what is true and in progress now      (yours)
  TASK.md                 your scratchpad; agents leave it alone
  MEMORY/ROOT_MEMORY.md   what should still be known in a month (yours)
  MEMORY/EXAMPLES/        known-good files kept in their own format
  ARTIFACTS/<TASK>/       durable outputs, one folder per workstream
  TMP/                    disposable, ignored by git
  skills/                 the kit's skills, next to your own
REPOS/                    child repositories, when there are any
```

If `AGENTS.md` or `CLAUDE.md` already has content, the pointer is appended and the rest is left
alone. Any skill you add under `WORK/skills/` gets its two links the next time the installer runs.

## Skills

| Skill | For |
|---|---|
| `tressoir-memory` | consolidating state, keeping memory tidy, merges, projects inside projects |
| `tressoir-plan` | work that needs a decision before implementation; one `PLAN.html` reference page |
| `tressoir-present` | briefings: writing the slides file, building it, handing it off |
| `tressoir-migrate` | moving a project from the first kit's `IB/` layout; temporary |

Two optional extras live in `extras/`. Once a project has one, `--override` refreshes it with the
rest.

- `tressoir-structured-review`: to use it, copy its folder into the project's `WORK/skills/` and
  run the installer again, which links it.
- `tressoir-system-view`, experimental: installed with `--experimental-system-view`.

## System view (experimental)

```bash
/path/to/tressoir-external/install.sh --experimental-system-view
```

This adds the skill `tressoir-system-view` and a folder, `WORK/SYSTEM_VIEW/`, with empty starting
files that are created once and never overwritten. The skill keeps one page current,
`WORK/SYSTEM_VIEW.html`: a figure of the project's major parts with views inside the larger ones,
flows, the interface each part offers, a file view, and tabs for the last commit, the current
state, what changed between them, what changed since you last looked, and what each plan would
change.

- The architecture is written once with you, in `system.json`. For every task the agent writes
  named changes in `changes.json`. A script works out every mark from git and builds the page:

  ```bash
  uv run WORK/skills/tressoir-system-view/system_view.py
  ```

- The script needs only Python 3 and git; `python3` works in place of `uv run`.
- It is a trial. What gets in the way goes in `WORK/SYSTEM_VIEW/FEEDBACK.md`, and is applied to the
  kit from time to time.

## Briefings

An agent writes `<name>.slides.html` and builds it:

```bash
uv run WORK/skills/tressoir-present/present.py <name>.slides.html
```

The result is `<name>.html`, which plays from disk in any browser and inline in harness previews
that show HTML. Nothing has to be running.

- Needs [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`. The script says clearly what is missing.
- The default voice, George, is local (Kokoro). The first build downloads the voice model, about
  350 MB, once per machine. Narration is cached, so unchanged slides are not spoken again.
- `--voice heart` is the other local voice. `--voice harper` uses Azure speech and needs
  `AZURE_VOICE_KEY` and `AZURE_VOICE_REGION` in the environment, the project's `.env` or `WORK/.env`.
- `--mp4` also writes a video with chapters and captions, for sharing. It needs Chrome or Chromium.
- Inline previews refuse files over about 2 MB, roughly nine minutes; the script warns before that.

## Coming from the first kit

The first kit had an `IB/` folder, canon files, a VS Code extension and `.tressoir.md` /
`.tressoir.html` artifacts. None of that is here any more, and old artifacts are not converted.
The installer refuses a project that still has `IB/`; follow `skills/tressoir-migrate/SKILL.md`,
which commits and tags the old files before retiring them.

## Tests

```bash
bash tests/test_install.sh                 # installer: layout, repeat runs, --override, the system view option, migration swap
python3 tests/test_system_view.py          # system view script, on temporary git repositories
uv run skills/tressoir-present/present.py tests/fixtures/three-choices.slides.html
uv run tests/check_player.py tests/fixtures/three-choices.html    # player, headless Chrome
```

The last two build the fixture briefing and play it at two sizes on every audio route.
