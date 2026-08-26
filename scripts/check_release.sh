#!/usr/bin/env bash

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
EXTENSION="$ROOT/extension"
PAYLOAD="$ROOT/share/tressoir-external"
LINEAR_SOURCE="$PAYLOAD/skills/tressoir-artifact-html/html_artifact_template"
VERSION="0.1.5"
VSIX="$EXTENSION/dist/tressoir-artifacts-$VERSION.vsix"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-release-check.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

cd "$EXTENSION"
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck
npm test
npm run package:vsix

unzip -Z1 "$VSIX" > "$TMP/archive.txt"
unzip -p "$VSIX" extension/package.json > "$TMP/package.json"
unzip -p "$VSIX" extension/LICENSE.md > "$TMP/LICENSE.md"
unzip -p "$VSIX" extension/dist/extension.js > "$TMP/extension.js"
unzip -p "$VSIX" extension/dist/assets/tressoir-md.js > "$TMP/tressoir-md.js"

cmp "$ROOT/LICENSE" "$EXTENSION/LICENSE.md"
cmp "$EXTENSION/src/notebook/assets/tressoir-md.js" \
  "$PAYLOAD/skills/tressoir-artifact-md/references/runtime/tressoir-md.js"
cmp "$EXTENSION/src/notebook/assets/tressoir-md.js" "$TMP/tressoir-md.js"

# The reviewed HTML starter is the single source for both HTML copies and Markdown's VSIX assets.
for source in "$LINEAR_SOURCE/tressoir-linear.css" "$LINEAR_SOURCE/tressoir-linear.js" \
  $(find "$LINEAR_SOURCE/vendor" -type f | LC_ALL=C sort); do
  rel=${source#"$LINEAR_SOURCE/"}
  built="$EXTENSION/dist/assets/linear/$rel"
  member="extension/dist/assets/linear/$rel"
  [ -f "$built" ] || { echo "missing built linear asset: $rel" >&2; exit 1; }
  cmp "$source" "$built"
  grep -Fx "$member" "$TMP/archive.txt" >/dev/null || {
    echo "missing VSIX linear asset: $rel" >&2
    exit 1
  }
  mkdir -p "$TMP/linear/$(dirname "$rel")"
  unzip -p "$VSIX" "$member" > "$TMP/linear/$rel"
  cmp "$source" "$TMP/linear/$rel"
done

grep -F 'KaTeX 0.18.4' "$LINEAR_SOURCE/vendor/README.md" >/dev/null
grep -F 'PrismJS 1.30.0' "$LINEAR_SOURCE/vendor/README.md" >/dev/null
grep -F 'CodeMirror 5.65.16' "$LINEAR_SOURCE/vendor/README.md" >/dev/null
grep -F 'free_form_feedback' "$TMP/extension.js" >/dev/null
grep -F 'tressoir.bridge' "$TMP/extension.js" >/dev/null

# Stable explicit-input identity must ship in both the projector and the webview morph:
# the projector emits a per-input data-morph-key, and the webview configures morphdom
# getNodeKey so answers follow their key instead of DOM position.
unzip -p "$VSIX" extension/dist/notebook-webview.js > "$TMP/notebook-webview.js"
grep -F 'data-morph-key' "$TMP/tressoir-md.js" >/dev/null
grep -F 'data-morph-key' "$TMP/notebook-webview.js" >/dev/null
grep -F 'getNodeKey' "$TMP/notebook-webview.js" >/dev/null
grep -Fx 'MIT License' "$ROOT/LICENSE" >/dev/null
grep -Fx 'MIT License' "$TMP/LICENSE.md" >/dev/null

node - "$TMP/package.json" <<'NODE'
const fs = require('fs')
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const identity = `${manifest.publisher}.${manifest.name}@${manifest.version}`
if (identity !== 'tressoir.tressoir-artifacts@0.1.5') {
  throw new Error(`unexpected packaged identity: ${identity}`)
}
if (manifest.license !== 'MIT') {
  throw new Error(`unexpected packaged license: ${manifest.license}`)
}
const editors = manifest.contributes?.customEditors ?? []
const byType = new Map(editors.map((editor) => [editor.viewType, editor]))
for (const [viewType, pattern, priority] of [
  ['tressoir.notebookHtml', '*.tressoir.html', 'default'],
  ['tressoir.genericHtml', '*.html', 'option'],
  ['tressoir.notebookMd', '*.tressoir.md', 'default'],
]) {
  const editor = byType.get(viewType)
  if (!editor) throw new Error(`missing custom editor: ${viewType}`)
  const patterns = (editor.selector ?? []).map((selector) => selector.filenamePattern)
  if (!patterns.includes(pattern)) throw new Error(`missing selector: ${pattern}`)
  if (editor.priority !== priority) throw new Error(`unexpected priority for ${viewType}: ${editor.priority}`)
}
NODE

for required in \
  extension/LICENSE.md \
  extension/THIRD_PARTY_NOTICES.md \
  extension/dist/extension.js \
  extension/dist/notebook-webview.js \
  extension/dist/notebook-webview.css \
  extension/dist/assets/artifact.css \
  extension/dist/assets/tressoir-md.js \
  extension/dist/assets/core/js-yaml.min.js \
  extension/dist/assets/core/tressoir-remark.umd.js; do
  grep -Fx "$required" "$TMP/archive.txt" >/dev/null || {
    echo "missing VSIX member: $required" >&2
    exit 1
  }
done

if grep -E '(^|/)(src|node_modules|__tests__)/|\.map$|\.vsix$' "$TMP/archive.txt"; then
  echo "VSIX contains development or nested package content" >&2
  exit 1
fi

if find "$PAYLOAD" -type f -name '*.vsix' -print -quit | grep .; then
  echo "payload contains a generated VSIX; public source builds must remain untracked" >&2
  exit 1
fi

cd "$ROOT"
for skill in "$PAYLOAD"/skills/*; do
  npx --yes skills-ref@0.1.5 validate "$skill"
done

node - "$PAYLOAD/skills/tressoir-isolation/templates/user.devcontainer.template.json" \
  "$PAYLOAD/skills/tressoir-isolation/templates/agent.devcontainer.template.json" \
  "$PAYLOAD/skills/tressoir-isolation/templates/agent-setup.template.sh" <<'NODE'
const fs = require('fs')
const { spawnSync } = require('child_process')
const [userPath, agentPath, setupPath] = process.argv.slice(2)
const user = JSON.parse(fs.readFileSync(userPath, 'utf8'))
const agent = JSON.parse(fs.readFileSync(agentPath, 'utf8'))
const setup = fs.readFileSync(setupPath, 'utf8')
const expectedImage = 'mcr.microsoft.com/devcontainers/base:ubuntu26.04'
if (user.image !== expectedImage || agent.image !== expectedImage) {
  throw new Error('isolation templates must share the validated baseline image')
}
if (user.remoteUser !== 'vscode' || user.updateRemoteUserUID !== true) {
  throw new Error('user template must use the UID-aligned non-root baseline')
}
for (const config of [user, agent]) {
  if (config.features?.['ghcr.io/devcontainers/features/node:2']?.version !== '24') {
    throw new Error('both isolation templates must use Node 24 LTS')
  }
  if (config.containerEnv?.TRESSOIR_AGENT_TARGETS !== '__TRESSOIR_AGENT_TARGETS__') {
    throw new Error('payload templates must retain the target-rendering marker')
  }
  if (JSON.stringify(config.customizations?.vscode?.extensions) !==
      JSON.stringify(['__TRESSOIR_VSCODE_EXTENSIONS__'])) {
    throw new Error('payload templates must retain the extension-rendering marker')
  }
  if (!config.customizations?.vscode?.settings?.['window.title']
      ?.includes('${localWorkspaceFolderBasename}')) {
    throw new Error('both isolation templates must retain the repository name in the window title')
  }
  for (const variable of ['XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME']) {
    if (!config.containerEnv?.[variable]?.startsWith('/home/vscode/')) {
      throw new Error(`missing development-user environment: ${variable}`)
    }
  }
}
if ('workspaceMount' in user) {
  throw new Error('user template must retain the normal read-write workspace mount')
}
const expectedUserLifecycle = ['bash', 'IB/isolation/agent-setup.sh', '--user']
if (JSON.stringify(user.postCreateCommand) !== JSON.stringify(expectedUserLifecycle)) {
  throw new Error('user lifecycle must call the readable helper in user mode')
}
if (agent.remoteUser !== 'vscode' || agent.updateRemoteUserUID !== true) {
  throw new Error('agent template must use the UID-aligned non-root baseline')
}
if (agent.workspaceFolder !== '/workspace' || !agent.workspaceMount.includes('target=/source') ||
    !agent.workspaceMount.includes('readonly')) {
  throw new Error('agent template must expose read-only source and writable scratch')
}
if (!agent.mounts.some((mount) => mount.includes('target=/workspace/IB') &&
    !mount.includes('readonly'))) {
  throw new Error('agent template must expose read-write IB')
}
const expectedLifecycle = ['bash', '/workspace/IB/isolation/agent-setup.sh', '--agent']
if (JSON.stringify(agent.postCreateCommand) !== JSON.stringify(expectedLifecycle)) {
  throw new Error('agent lifecycle must call the mounted readable setup helper')
}
for (const invariant of ["--exclude='./IB'", '/workspace/AGENTS.md',
  '/workspace/CLAUDE.md', 'TRESSOIR ISOLATION: BEGIN', 'findmnt', '/workspace/IB',
  'sudo -n true', 'sudo chown -R', '@openai/codex@latest',
  '@anthropic-ai/claude-code@latest', '@earendil-works/pi-coding-agent@latest',
  'npm install --global', 'XDG_CACHE_HOME']) {
  if (!setup.includes(invariant)) throw new Error(`missing agent setup invariant: ${invariant}`)
}
for (const guarded of ['/workspace/AGENTS.md', '/workspace/CLAUDE.md']) {
  if (!setup.includes(`if [ -f ${guarded} ]; then`)) {
    throw new Error(`guidance append must be guarded by -f: ${guarded}`)
  }
}
for (const forbidden of ['docker.sock', 'privileged', 'chmod -R 777']) {
  if (`${JSON.stringify(agent)}\n${setup}`.includes(forbidden)) {
    throw new Error(`forbidden agent baseline: ${forbidden}`)
  }
}
const syntax = spawnSync('bash', ['-n', setupPath], { encoding: 'utf8' })
if (syntax.status !== 0) throw new Error(`invalid agent lifecycle shell: ${syntax.stderr}`)
NODE

cd "$PAYLOAD"
find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort | while IFS= read -r file; do
  rel=${file#./}
  if command -v shasum >/dev/null 2>&1; then
    digest=$(shasum -a 256 "$file" | awk '{print $1}')
  else
    digest=$(sha256sum "$file" | awk '{print $1}')
  fi
  printf '%s  %s\n' "$digest" "$rel"
done > SHA256SUMS

cd "$ROOT"
bash -n bin/tressoir-external
bash -n install.sh
bash -n tests/helpers/dummy_repo/make_dummy_repo.sh
node --check "$PAYLOAD/skills/tressoir-artifact-md/scripts/check_md.js"
node "$PAYLOAD/skills/tressoir-artifact-md/scripts/check_md.js" \
  "$PAYLOAD/skills/tressoir-artifact-md/user_artifact_md_template/PLAN.tressoir.md" \
  "$PAYLOAD/skills/tressoir-artifact-md/user_artifact_md_template/INTERACTIVE.tressoir.md"
tests/test_artifact_md_checker.sh
tests/test_isolation.sh
tests/test_setup.sh
tests/test_install.sh

echo "Release checks passed: $VSIX"
