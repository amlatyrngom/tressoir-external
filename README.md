# Tressoir External

Tressoir External is a small, portable approximation of the Tressoir workflow for ordinary coding-agent harnesses. It provides:

- a self-contained regular VS Code extension for trusted `.tressoir.md` and `.tressoir.html` artifacts;
- a project-local **IB (Interpretable Blueprint)** working area;
- six portable Agent Skills;
- lightweight Markdown canon/memory;
- non-overwriting skill adapters for Claude Code, OpenAI Codex CLI, and the TypeScript Pi coding agent; and
- a macOS/Linux Bash setup command.

It does **not** install the Tressoir daemon, SDK, code-server, supervisor, frontend, Python runtime, ontologies, or subagent framework.

## MVP status and platform

The MVP targets:

- macOS and mainstream Linux;
- Bash 3.2 or newer;
- local project filesystems;
- regular desktop VS Code through an explicitly selected CLI (`code` by default);
- Claude Code project skills;
- Codex CLI project skills;
- TypeScript Pi `0.80.6`-compatible `.agents/skills` discovery after project trust.

Native Windows, VS Code web, VSCodium/Open VSX, remote extension hosts, marketplace or npm-package publication, and automatic uninstall are not currently claimed.

## Prerequisites

For the interactive source installer:

- macOS or mainstream Linux with Bash 3.2+;
- `curl`, `tar`, and a standard `mktemp`;
- Node.js 22+ and npm when building/installing the VS Code extension;
- regular desktop VS Code 1.85+ with its `code` CLI available when installing the extension.

Node and npm are not required when you decline the extension. The installed
Markdown artifact checker requires Node.js 18+ if you choose to run it later.

## Interactive install from GitHub

Open a terminal in the project you want to configure, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/amlatyrngom/tressoir-external/main/install.sh | bash
```

The installer asks separately whether to:

- install the Tressoir Artifacts VS Code extension;
- register skills for Claude Code;
- register skills for OpenAI Codex CLI; and
- register skills for the TypeScript Pi coding agent.

When at least one agent harness is selected, it also asks:

```text
Register root guidance in system prompts? [y/N]
```

If accepted, Claude uses root `CLAUDE.md` with `@IB/TRESSOIR.md`; Codex uses
root `AGENTS.md`; Pi-only setup uses `.pi/APPEND_SYSTEM.md`. Codex and Pi
selected together share `AGENTS.md`, avoiding duplicate guidance. Missing files
are created. Existing regular files receive a `# Tressoir Guidance` section
only when they do not already mention `TRESSOIR.md`.

The current directory is the target project. The installer downloads the public
source archive into a temporary directory, builds the VSIX there when selected,
runs the verified setup command, and removes the downloaded source and build
output on exit. It does not leave extension source, `node_modules`, package
output, or a Tressoir External checkout in the target project.

Prompts are read from `/dev/tty`, so they work even though Bash is reading the
script from the curl pipeline. For a different project or VS Code CLI:

```bash
TRESSOIR_EXTERNAL_ROOT=/path/to/project \
TRESSOIR_EXTERNAL_VSCODE_BIN=code-insiders \
  bash -c 'curl -fsSL https://raw.githubusercontent.com/amlatyrngom/tressoir-external/main/install.sh | bash'
```

For unattended use, set all five choices to `yes` or `no`:

```bash
TRESSOIR_EXTERNAL_VSCODE=yes \
TRESSOIR_EXTERNAL_CLAUDE=yes \
TRESSOIR_EXTERNAL_CODEX=yes \
TRESSOIR_EXTERNAL_PI=yes \
TRESSOIR_EXTERNAL_GUIDANCE=yes \
  bash -c 'curl -fsSL https://raw.githubusercontent.com/amlatyrngom/tressoir-external/main/install.sh | bash'
```

Accepted choice values are `yes`/`no`, `y`/`n`, `true`/`false`, or `1`/`0`.

## Install from a local source checkout

Keep `bin/` and `share/` together. To set up harness skills without installing
the extension:

```bash
/path/to/tressoir-external/bin/tressoir-external setup \
  --root "$PWD" --claude --codex --pi --register-guidance --no-vscode
```

To build and install the extension from the checkout:

```bash
cd /path/to/tressoir-external/extension
npm ci
npm run package:vsix

../bin/tressoir-external setup \
  --root /path/to/project \
  --claude --codex --pi --register-guidance \
  --vsix "$PWD/dist/tressoir-artifacts-0.1.1.vsix"
```

Useful setup options:

```text
--root PATH        Target another project; default is exactly the current directory
--register-guidance
                   Create/append selected harness prompt guidance
--vsix PATH        Install the supplied Tressoir Artifacts VSIX
--vscode-bin PATH  Use code-insiders or an absolute VS Code CLI path
--no-vscode        Skip extension installation
--dry-run          Print the plan without changing the project or VS Code
```

Setup verifies the source payload checksums before writing. It creates only
absent canonical files and collision-checked relative skill links. A second
identical run is a no-op.

## Created project layout

```text
IB/
├── TRESSOIR.md
├── .gitignore
├── TASK.md
├── STATE.md
├── ARTIFACTS/
├── TMP/
├── CANON/
│   └── ROOT_CANON.md
└── skills/
    ├── tressoir-artifact-md/
    ├── tressoir-artifact-html/
    ├── tressoir-plan/
    ├── tressoir-working-area/
    ├── tressoir-memory/
    └── tressoir-structured-review/
```

Claude receives per-skill relative links under `.claude/skills/`. Codex and Pi share per-skill links under `.agents/skills/`.

## Optional root guidance registration

Canonical guidance is installed as `IB/TRESSOIR.md`. The interactive installer
can register it in root harness instruction files when you answer yes to:

```text
Register root guidance in system prompts? [y/N]
```

The equivalent direct setup option is `--register-guidance`.

For selected Claude setup, the managed section in root `CLAUDE.md` is:

```md
# Tressoir Guidance

@IB/TRESSOIR.md
```

For selected Codex setup, the managed section in root `AGENTS.md` is:

```md
# Tressoir Guidance

Before beginning substantial work, read and follow `IB/TRESSOIR.md`.
```

For Pi-only setup, that same prose section is written to
`.pi/APPEND_SYSTEM.md`. When Codex and Pi are both selected, root `AGENTS.md`
serves both and `.pi/APPEND_SYSTEM.md` is not created.

Registration is intentionally narrow:

- If the target file already contains `TRESSOIR.md`, setup leaves it unchanged.
- If the root target is absent, setup creates it.
- If it is an existing regular file without a mention, setup appends one section.
- Reruns do not duplicate the section.
- Symlinks, directories, and other incompatible targets are preserved and
  reported as safe degradation.
- Setup never edits `.claude/CLAUDE.md`, `AGENTS.override.md`,
  `.claude/rules/*`, `.pi/SYSTEM.md`, global instructions, or settings.

Declining the prompt preserves the earlier behavior: setup prints manual
Claude, Codex, and Pi inclusion options and makes no instruction-file change.
Existing instruction precedence remains under user control.

## Working-area behavior

`IB` means **Interpretable Blueprint**: a human-inspectable workspace shared across agents and sessions.

- `TASK.md` is user-owned and is **not** read or edited automatically. Agents access it only on explicit user request and at the relevant point.
- `STATE.md` is agent-maintained. Keep it current; around 16,000 characters, proactively condense it toward 8,000.
- `ARTIFACTS/` stores durable plans, research, explainers, reviews, and reusable helpers. Reuse one upper-case folder for the full lifetime of a broad task.
- `TMP/` stores disposable logs, dumps, downloads, screenshots, and experiments.
- `CANON/ROOT_CANON.md` indexes small, focused subsystem canon files.

The installed `TRESSOIR.md` points to the exact skill to use for planning, artifacts, memory/upkeep, and structured review.

Setup also seeds `IB/.gitignore` on a create-only basis. Its narrow defaults ignore disposable `TMP/` contents, artifact-local `vendor/` caches, `.env`, and `.DS_Store`; it does not hide `TASK.md`, `STATE.md`, canon, skills, artifacts, or interaction records. An existing `IB/.gitignore` is always preserved.

## Artifact template folder and checker

After setup:

```text
IB/skills/tressoir-artifact-md/user_artifact_md_template/
├── PLAN.tressoir.md
├── INTERACTIVE.tressoir.md
├── TASK.md
└── interactions.json
```

Copy the relevant template into an existing broad-task folder without overwriting. The folder is intentionally reusable: an initial plan, user-requested `<STEP>_PLAN.md` + `<STEP>_PLAN.tressoir.md` pair, explainers, research, raw HTML, and `NEXT_INTERACTIVE.tressoir.md` may all live together. Create another upper-case folder only for a genuinely separate workstream or when the user requests one.

For example:

```bash
cp IB/skills/tressoir-artifact-md/user_artifact_md_template/PLAN.tressoir.md \
  IB/ARTIFACTS/FEATURE_X/MIGRATION_PLAN.tressoir.md
```

Check first that the destination is absent. Preserve an existing folder-local `TASK.md` and `interactions.json`; for a projected artifact, create the matching plain Markdown source as well.

Check projected Markdown using the exact committed lint runtime:

```bash
node IB/skills/tressoir-artifact-md/scripts/check_md.js \
  IB/ARTIFACTS/FEATURE_X/PLAN.tressoir.md
```

The checker requires Node 18+ but no npm install. Node is not required to render the installed VS Code extension; it is needed only for this optional authoring check and for extension development.

## VS Code extension

The VSIX is built from self-contained source under `extension/` and contains only the artifact stack:

- `.tressoir.md` and `.tressoir.html` custom editors;
- projection and webview runtime;
- interaction persistence and sibling opening;
- theme/morph behavior;
- committed Markdown runtime assets.

It contains no backend bridge, agent editor commands, plugin host, daemon connection, supervisor, code-server, or Python runtime.

### Trusted-artifact warning

Both artifact formats are executable trusted content, not inert previews.

- Raw HTML and authored inline/relative scripts can execute.
- Markdown permits raw HTML and scripts.
- Declared remote resources may cause network access and local caching.
- Authored code receives a narrow contained interaction/open-file helper.

Only open artifacts from authors and workspaces you trust. The MVP has no sanitized safe-preview mode.

## Collision behavior and result codes

The command never force-replaces an existing file, directory, or symlink.

- `0` — requested setup is complete or already correct.
- `2` — setup completed safely but preserved one or more adapter/canonical-skill collisions; manual work may remain.
- `1` — validation or extension installation failed.

Seed files and canonical guidance are create-only. Existing user versions are preserved. Existing canonical skill trees are preserved when they differ from the payload.

VS Code installation happens after project setup. If it fails, project setup remains in place and a rerun retries the extension phase.

## Development and release verification

Extension-only:

```bash
cd extension
npm ci
npm run typecheck
npm test
npm run package:vsix
```

Complete direct release gate:

```bash
scripts/check_release.sh
```

For a disposable, committed project containing deliberate collisions and
existing Claude/Codex/Pi files:

```bash
tests/helpers/dummy_repo/make_dummy_repo.sh "/tmp/tressoir dummy repo"
```

The generated repository includes its own `TESTING.md` and verification helpers
for non-clobbering, all-harness setup, and an idempotent rerun.

The release gate:

- runs 62 focused extension tests;
- builds from a clean `dist/`;
- inspects the packaged manifest and archive;
- requires both artifact editors and all runtime assets;
- rejects source, tests, source maps, `node_modules`, and nested VSIX files;
- validates all six Agent Skills;
- checks both distributed Markdown templates with the bundled checker;
- regenerates payload checksums; and
- runs filesystem setup fixtures for combinations, idempotence, dry-run,
  collisions, root-guidance creation/append/mention detection, path spaces,
  extension failure, and symlink containment;
- runs an offline piped-bootstrap fixture that builds in temporary storage,
  installs all selected integrations, registers opt-in root guidance, and
  cleans up; and
- rejects generated VSIX files in the public source payload.

`extension/dist/`, `extension/node_modules/`, and npm debug logs are ignored.
Release checks build transient output locally; no npm package is published.

For a final desktop smoke, install the built VSIX into isolated VS Code directories and confirm:

```text
tressoir.tressoir-artifacts@0.1.1
```

## Licensing

First-party Tressoir External and Tressoir Artifacts code is licensed under the MIT License; see `LICENSE` and `extension/LICENSE.md`. `extension/THIRD_PARTY_NOTICES.md` records bundled runtime provenance and third-party licenses.
