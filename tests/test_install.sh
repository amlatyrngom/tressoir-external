#!/usr/bin/env bash

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P) || exit 1
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-install-tests.XXXXXX") || exit 1
PASS=0
FAIL=0

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

pass() {
  PASS=$((PASS + 1))
  printf 'PASS: %s\n' "$1"
}

fail() {
  FAIL=$((FAIL + 1))
  printf 'FAIL: %s\n' "$1" >&2
}

assert_file() {
  [ -f "$1" ] || {
    printf 'expected file: %s\n' "$1" >&2
    return 1
  }
}

assert_link() {
  local path expected actual
  path="$1"
  expected="$2"
  [ -L "$path" ] || {
    printf 'expected symlink: %s\n' "$path" >&2
    return 1
  }
  actual=$(readlink "$path") || return 1
  [ "$actual" = "$expected" ] || {
    printf 'wrong target for %s: got %s, expected %s\n' \
      "$path" "$actual" "$expected" >&2
    return 1
  }
}

assert_absent() {
  [ ! -e "$1" ] && [ ! -L "$1" ] || {
    printf 'expected absent path: %s\n' "$1" >&2
    return 1
  }
}

digest_tree() {
  local directory
  directory="$1"
  (
    cd "$directory" || exit 1
    find . -type f -print | LC_ALL=C sort | while IFS= read -r file; do
      shasum -a 256 "$file"
    done
    find . -type l -print | LC_ALL=C sort | while IFS= read -r link; do
      printf 'link %s -> %s\n' "$link" "$(readlink "$link")"
    done
  )
}

make_source_archive() {
  local tree top archive
  tree="$TMP_ROOT/archive-tree"
  top="$tree/tressoir-external-main"
  archive="$TMP_ROOT/source.tar.gz"
  mkdir -p "$top/extension"
  cp -R "$REPO/bin" "$top/bin"
  cp -R "$REPO/share" "$top/share"
  cp "$REPO/extension/package-lock.json" "$top/extension/package-lock.json"
  tar -czf "$archive" -C "$tree" tressoir-external-main
}

make_mock_tools() {
  local tools
  tools="$TMP_ROOT/mock-tools"
  mkdir "$tools"

  cat > "$tools/npm" <<'EOF'
#!/usr/bin/env bash
set -u
case "$*" in
  "ci --ignore-scripts --no-audit --no-fund")
    printf '%s\n' 'mock npm ci'
    ;;
  "run package:vsix")
    mkdir -p dist
    printf '%s\n' 'mock VSIX' > dist/tressoir-artifacts-0.1.6.vsix
    printf '%s\n' 'mock package complete'
    ;;
  *)
    printf 'unexpected mock npm arguments: %s\n' "$*" >&2
    exit 4
    ;;
esac
EOF

  cat > "$tools/code" <<'EOF'
#!/usr/bin/env bash
set -u
: "${MOCK_CODE_STATE:?MOCK_CODE_STATE is required}"
: "${MOCK_CODE_INSTALL_LOG:?MOCK_CODE_INSTALL_LOG is required}"
case "${1:-}" in
  --list-extensions)
    if [ -f "$MOCK_CODE_STATE" ]; then
      cat "$MOCK_CODE_STATE"
    fi
    ;;
  --install-extension)
    [ -f "${2:-}" ] || exit 3
    printf '%s\n' "$2" > "$MOCK_CODE_INSTALL_LOG"
    printf '%s\n' 'tressoir.tressoir-artifacts@0.1.6' > "$MOCK_CODE_STATE"
    printf '%s\n' 'mock installation succeeded'
    ;;
  *)
    printf 'unexpected mock code arguments: %s\n' "$*" >&2
    exit 4
    ;;
esac
EOF
  chmod +x "$tools/npm" "$tools/code"
}

case_piped_source_install() (
  set -e
  make_source_archive
  make_mock_tools

  project="$TMP_ROOT/target project"
  ephemeral="$TMP_ROOT/ephemeral"
  state="$TMP_ROOT/mock-code.state"
  install_log="$TMP_ROOT/mock-code-install.log"
  output="$TMP_ROOT/bootstrap.log"
  mkdir -p "$project" "$ephemeral"
  ephemeral=$(CDPATH= cd -- "$ephemeral" && pwd -P)

  cat "$REPO/install.sh" | env \
    PATH="$TMP_ROOT/mock-tools:$PATH" \
    TMPDIR="$ephemeral" \
    MOCK_CODE_STATE="$state" \
    MOCK_CODE_INSTALL_LOG="$install_log" \
    TRESSOIR_EXTERNAL_ARCHIVE_URL="file://$TMP_ROOT/source.tar.gz" \
    TRESSOIR_EXTERNAL_ROOT="$project" \
    TRESSOIR_EXTERNAL_VSCODE=yes \
    TRESSOIR_EXTERNAL_CLAUDE=yes \
    TRESSOIR_EXTERNAL_CODEX=yes \
    TRESSOIR_EXTERNAL_PI=yes \
    TRESSOIR_EXTERNAL_GUIDANCE=yes \
    bash > "$output"

  assert_file "$project/IB/TRESSOIR.md"
  assert_file "$project/IB/skills/tressoir-artifact-md/SKILL.md"
  assert_file "$project/IB/isolation/README.md"
  assert_file "$project/IB/isolation/user.devcontainer.json"
  assert_file "$project/IB/isolation/agent.devcontainer.json"
  assert_file "$project/IB/isolation/agent-setup.sh"
  assert_file "$project/IB/skills/tressoir-isolation/templates/README.template.md"
  assert_file "$project/IB/skills/tressoir-isolation/templates/user.devcontainer.template.json"
  assert_file "$project/IB/skills/tressoir-isolation/templates/agent.devcontainer.template.json"
  assert_file "$project/IB/skills/tressoir-isolation/templates/agent-setup.template.sh"
  assert_link "$project/.devcontainer/user/devcontainer.json" \
    "../../IB/isolation/user.devcontainer.json"
  assert_link "$project/.devcontainer/agent/devcontainer.json" \
    "../../IB/isolation/agent.devcontainer.json"
  node - \
    "$project/IB/isolation/user.devcontainer.json" \
    "$project/IB/isolation/agent.devcontainer.json" <<'NODE'
const fs = require('fs')
for (const path of process.argv.slice(2)) {
  const config = JSON.parse(fs.readFileSync(path, 'utf8'))
  if (config.containerEnv.TRESSOIR_AGENT_TARGETS !== 'claude,codex,pi') process.exit(1)
  if (JSON.stringify(config.customizations.vscode.extensions) !==
      JSON.stringify(['anthropic.claude-code', 'openai.chatgpt'])) process.exit(1)
}
NODE
  assert_file "$project/IB/CANON/CANON_ARTIFACTS/README.md"
  for skill in \
    tressoir-artifact-md tressoir-artifact-html tressoir-plan \
    tressoir-working-area tressoir-canon tressoir-structured-review \
    tressoir-isolation; do
    assert_link "$project/.claude/skills/$skill" "../../IB/skills/$skill"
    assert_link "$project/.agents/skills/$skill" "../../IB/skills/$skill"
  done
  assert_absent "$project/IB/skills/tressoir-memory"
  assert_absent "$project/.claude/skills/tressoir-memory"
  assert_absent "$project/.agents/skills/tressoir-memory"
  assert_file "$project/CLAUDE.md"
  assert_file "$project/AGENTS.md"
  grep -Fx '# Tressoir Guidance' "$project/CLAUDE.md" >/dev/null
  grep -Fx \
    'Before substantial work, read and follow `IB/TRESSOIR.md`.' \
    "$project/CLAUDE.md" >/dev/null
  grep -Fx 'Read current status and open decisions in `IB/STATE.md`.' \
    "$project/CLAUDE.md" >/dev/null
  grep -Fx 'Read durable project decisions in `IB/CANON/ROOT_CANON.md`.' \
    "$project/CLAUDE.md" >/dev/null
  assert_file "$project/.claude/settings.json"
  grep -F '"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "400000"' \
    "$project/.claude/settings.json" >/dev/null
  grep -F '"autoMemoryEnabled": false' "$project/.claude/settings.json" >/dev/null
  grep -Fx '# Tressoir Guidance' "$project/AGENTS.md" >/dev/null
  grep -Fx \
    'Before substantial work, read and follow `IB/TRESSOIR.md`.' \
    "$project/AGENTS.md" >/dev/null
  assert_absent "$project/.pi"

  grep -Fx 'tressoir.tressoir-artifacts@0.1.6' "$state" >/dev/null
  built_vsix=$(sed -n '1p' "$install_log")
  case "$built_vsix" in
    "$ephemeral"/*/source/tressoir-external-main/extension/dist/tressoir-artifacts-0.1.6.vsix)
      ;;
    *)
      printf 'VSIX was not installed from temporary storage: %s\n' "$built_vsix" >&2
      exit 1
      ;;
  esac

  [ -z "$(find "$ephemeral" -mindepth 1 -print -quit)" ]
  assert_absent "$project/extension"
  assert_absent "$project/package.json"
  assert_absent "$project/node_modules"
  assert_absent "$project/tressoir-external-main"

  grep 'Claude Code target: CLAUDE.md' "$output" >/dev/null
  grep 'Codex target: AGENTS.md' "$output" >/dev/null
  grep 'Pi target: AGENTS.md (shared with Codex)' "$output" >/dev/null
  grep 'Edited, duplicated, or unrelated guidance was preserved unchanged.' \
    "$output" >/dev/null
  grep 'Setup never edits nested Claude, override, rules, global, or Pi SYSTEM.md files.' \
    "$output" >/dev/null
  grep 'Temporary source and build files will now be removed.' "$output" >/dev/null

  printf 'EDITED TASK\n' > "$project/IB/TASK.md"
  printf 'PROTECTED STATE\n' > "$project/IB/STATE.md"
  printf 'PROTECTED ROOT CANON\n' > "$project/IB/CANON/ROOT_CANON.md"
  printf 'EDITED SKILL\n' > "$project/IB/skills/tressoir-isolation/SKILL.md"
  printf 'EDITED ADAPTED ISOLATION\n' > "$project/IB/isolation/README.md"
  printf 'STALE REFERENCE\n' \
    > "$project/IB/skills/tressoir-isolation/templates/README.template.md"
  shasum -a 256 "$project/IB/STATE.md" "$project/IB/CANON/ROOT_CANON.md" \
    > "$TMP_ROOT/bootstrap-override-protected-before.txt"
  digest_tree "$project/IB/isolation" \
    > "$TMP_ROOT/bootstrap-override-isolation-before.txt"

  override_output="$TMP_ROOT/bootstrap-override.log"
  cat "$REPO/install.sh" | env \
    PATH="$TMP_ROOT/mock-tools:$PATH" \
    TMPDIR="$ephemeral" \
    MOCK_CODE_STATE="$state" \
    MOCK_CODE_INSTALL_LOG="$install_log" \
    TRESSOIR_EXTERNAL_ARCHIVE_URL="file://$TMP_ROOT/source.tar.gz" \
    TRESSOIR_EXTERNAL_ROOT="$project" \
    TRESSOIR_EXTERNAL_VSCODE=yes \
    TRESSOIR_EXTERNAL_CLAUDE=yes \
    TRESSOIR_EXTERNAL_CODEX=yes \
    TRESSOIR_EXTERNAL_PI=yes \
    TRESSOIR_EXTERNAL_GUIDANCE=yes \
    bash -s -- --override > "$override_output"

  cmp "$REPO/share/tressoir-external/seeds/TASK.md" "$project/IB/TASK.md"
  cmp "$REPO/share/tressoir-external/skills/tressoir-isolation/SKILL.md" \
    "$project/IB/skills/tressoir-isolation/SKILL.md"
  cmp "$REPO/share/tressoir-external/skills/tressoir-isolation/templates/README.template.md" \
    "$project/IB/skills/tressoir-isolation/templates/README.template.md"
  digest_tree "$project/IB/isolation" \
    > "$TMP_ROOT/bootstrap-override-isolation-after.txt"
  diff -u "$TMP_ROOT/bootstrap-override-isolation-before.txt" \
    "$TMP_ROOT/bootstrap-override-isolation-after.txt"
  shasum -a 256 "$project/IB/STATE.md" "$project/IB/CANON/ROOT_CANON.md" \
    > "$TMP_ROOT/bootstrap-override-protected-after.txt"
  diff -u "$TMP_ROOT/bootstrap-override-protected-before.txt" \
    "$TMP_ROOT/bootstrap-override-protected-after.txt"
  grep 'managed payload: override' "$override_output" >/dev/null
  grep 'reference templates refreshed under IB/skills/tressoir-isolation/templates' \
    "$override_output" >/dev/null
  grep 'installed: tressoir.tressoir-artifacts@0.1.6' "$override_output" >/dev/null
  [ -z "$(find "$ephemeral" -mindepth 1 -print -quit)" ]
)

case_nothing_selected() (
  set -e
  project="$TMP_ROOT/nothing"
  output="$TMP_ROOT/nothing.log"
  mkdir "$project"

  cat "$REPO/install.sh" | env \
    TRESSOIR_EXTERNAL_ROOT="$project" \
    TRESSOIR_EXTERNAL_VSCODE=no \
    TRESSOIR_EXTERNAL_CLAUDE=no \
    TRESSOIR_EXTERNAL_CODEX=no \
    TRESSOIR_EXTERNAL_PI=no \
    TRESSOIR_EXTERNAL_GUIDANCE=no \
    bash > "$output"

  [ -z "$(find "$project" -mindepth 1 -print -quit)" ]
  grep 'Nothing selected; no files were changed.' "$output" >/dev/null
)

case_consistent_interactive_choices() (
  set -e
  grep -F "printf '%s [y/n] '" "$REPO/install.sh" >/dev/null
  if grep -E '\[(Y/n|y/N)\]' "$REPO/install.sh" "$REPO/README.md"; then
    return 1
  fi
  grep -F 'Please answer yes or no.' "$REPO/install.sh" >/dev/null
)

case_piped_source_install
status=$?
if [ "$status" -eq 0 ]; then
  pass "piped bootstrap installs selections and forwards override safely"
else
  fail "piped bootstrap builds in temporary storage and installs all selections"
fi

case_nothing_selected
status=$?
if [ "$status" -eq 0 ]; then
  pass "noninteractive no-selection path makes no changes"
else
  fail "noninteractive no-selection path makes no changes"
fi

case_consistent_interactive_choices
status=$?
if [ "$status" -eq 0 ]; then
  pass "interactive choices use one explicit y/n contract"
else
  fail "interactive choices use one explicit y/n contract"
fi

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
