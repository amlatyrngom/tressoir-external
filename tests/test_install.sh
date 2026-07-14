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
    printf '%s\n' 'mock VSIX' > dist/tressoir-artifacts-0.1.1.vsix
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
    printf '%s\n' 'tressoir.tressoir-artifacts@0.1.1' > "$MOCK_CODE_STATE"
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
    bash > "$output"

  assert_file "$project/IB/TRESSOIR.md"
  assert_file "$project/IB/skills/tressoir-artifact-md/SKILL.md"
  for skill in \
    tressoir-artifact-md tressoir-artifact-html tressoir-plan \
    tressoir-working-area tressoir-memory tressoir-structured-review; do
    assert_link "$project/.claude/skills/$skill" "../../IB/skills/$skill"
    assert_link "$project/.agents/skills/$skill" "../../IB/skills/$skill"
  done

  grep -Fx 'tressoir.tressoir-artifacts@0.1.1' "$state" >/dev/null
  built_vsix=$(sed -n '1p' "$install_log")
  case "$built_vsix" in
    "$ephemeral"/*/source/tressoir-external-main/extension/dist/tressoir-artifacts-0.1.1.vsix)
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

  grep 'Claude Code option: add @IB/TRESSOIR.md' "$output" >/dev/null
  grep "Codex option: add 'Before work, read and follow IB/TRESSOIR.md.'" \
    "$output" >/dev/null
  grep 'pi --append-system-prompt ./IB/TRESSOIR.md' "$output" >/dev/null
  grep 'Setup did not create or edit any harness instruction or prompt file.' \
    "$output" >/dev/null
  grep 'Temporary source and build files will now be removed.' "$output" >/dev/null
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
    bash > "$output"

  [ -z "$(find "$project" -mindepth 1 -print -quit)" ]
  grep 'Nothing selected; no files were changed.' "$output" >/dev/null
)

if case_piped_source_install; then
  pass "piped bootstrap builds in temporary storage and installs all selections"
else
  fail "piped bootstrap builds in temporary storage and installs all selections"
fi

if case_nothing_selected; then
  pass "noninteractive no-selection path makes no changes"
else
  fail "noninteractive no-selection path makes no changes"
fi

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
