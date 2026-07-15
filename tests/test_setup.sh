#!/usr/bin/env bash

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P) || exit 1
SETUP="$REPO/bin/tressoir-external"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-external-tests.XXXXXX") || exit 1
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

assert_dir() {
  [ -d "$1" ] && [ ! -L "$1" ] || {
    printf 'expected real directory: %s\n' "$1" >&2
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

make_mock_code() {
  local path
  path="$1"
  cat > "$path" <<'EOF'
#!/usr/bin/env bash
set -u
: "${MOCK_CODE_STATE:?MOCK_CODE_STATE is required}"
case "${1:-}" in
  --list-extensions)
    if [ -f "$MOCK_CODE_STATE" ]; then
      cat "$MOCK_CODE_STATE"
    fi
    ;;
  --install-extension)
    if [ "${MOCK_CODE_FAIL_INSTALL:-0}" = "1" ]; then
      echo "mock install failure" >&2
      exit 1
    fi
    [ -f "${2:-}" ] || exit 3
    printf '%s\n' 'tressoir.tressoir-artifacts@0.1.1' > "$MOCK_CODE_STATE"
    printf '%s\n' 'mock installation succeeded'
    ;;
  *)
    echo "unexpected mock code arguments: $*" >&2
    exit 4
    ;;
esac
EOF
  chmod +x "$path"
}

make_mock_vsix() {
  local path
  path="$1"
  printf '%s\n' 'mock VSIX for setup command tests' > "$path"
}

run_case() {
  local name function_name
  name="$1"
  function_name="$2"
  if "$function_name"; then
    pass "$name"
  else
    fail "$name"
  fi
}

case_fresh_all_with_extension() (
  set -e
  project="$TMP_ROOT/fresh all"
  mkdir -p "$project"
  mock="$TMP_ROOT/mock-code-all"
  state="$TMP_ROOT/mock-code-all.state"
  vsix="$TMP_ROOT/mock-all.vsix"
  make_mock_code "$mock"
  make_mock_vsix "$vsix"

  MOCK_CODE_STATE="$state" "$SETUP" setup \
    --root "$project" --claude --codex --pi \
    --vsix "$vsix" --vscode-bin "$mock"

  assert_file "$project/IB/TRESSOIR.md"
  assert_file "$project/IB/.gitignore"
  assert_file "$project/IB/TASK.md"
  assert_file "$project/IB/STATE.md"
  assert_file "$project/IB/CANON/ROOT_CANON.md"
  assert_dir "$project/IB/ARTIFACTS"
  assert_dir "$project/IB/TMP"

  for skill in \
    tressoir-artifact-md tressoir-artifact-html tressoir-plan \
    tressoir-working-area tressoir-memory tressoir-structured-review; do
    assert_file "$project/IB/skills/$skill/SKILL.md"
    assert_link "$project/.claude/skills/$skill" "../../IB/skills/$skill"
    assert_link "$project/.agents/skills/$skill" "../../IB/skills/$skill"
  done

  assert_file "$project/IB/skills/tressoir-artifact-md/scripts/check_md.js"
  assert_file "$project/IB/skills/tressoir-artifact-md/user_artifact_md_template/PLAN.tressoir.md"
  assert_file "$project/IB/skills/tressoir-artifact-md/user_artifact_md_template/INTERACTIVE.tressoir.md"
  assert_file "$project/IB/skills/tressoir-artifact-md/user_artifact_md_template/TASK.md"
  assert_file "$project/IB/skills/tressoir-artifact-md/user_artifact_md_template/interactions.json"
  assert_absent "$project/IB/skills/tressoir-artifact-md/scripts/start_artifact.sh"
  grep -Fx 'TMP/' "$project/IB/.gitignore" >/dev/null
  grep -Fx 'vendor/' "$project/IB/.gitignore" >/dev/null

  # Root guidance registration remains opt-in.
  assert_absent "$project/CLAUDE.md"
  assert_absent "$project/AGENTS.md"
  assert_absent "$project/.claude/rules"
  assert_absent "$project/.pi"
  grep -Fx 'tressoir.tressoir-artifacts@0.1.1' "$state" >/dev/null

  digest_tree "$project" > "$TMP_ROOT/fresh-before.txt"
  MOCK_CODE_STATE="$state" "$SETUP" setup \
    --root "$project" --claude --codex --pi \
    --vsix "$vsix" --vscode-bin "$mock" \
    > "$TMP_ROOT/fresh-rerun.log"
  digest_tree "$project" > "$TMP_ROOT/fresh-after.txt"
  diff -u "$TMP_ROOT/fresh-before.txt" "$TMP_ROOT/fresh-after.txt"
  grep 'already linked' "$TMP_ROOT/fresh-rerun.log" >/dev/null
  grep 'already installed: tressoir.tressoir-artifacts@0.1.1' \
    "$TMP_ROOT/fresh-rerun.log" >/dev/null
)

case_each_harness() (
  set -e
  for harness in claude codex pi; do
    project="$TMP_ROOT/only-$harness"
    mkdir -p "$project"
    "$SETUP" setup --root "$project" "--$harness" --no-vscode >/dev/null

    assert_file "$project/IB/TRESSOIR.md"
    case "$harness" in
      claude)
        assert_dir "$project/.claude/skills"
        assert_absent "$project/.agents"
        ;;
      codex|pi)
        assert_dir "$project/.agents/skills"
        assert_absent "$project/.claude"
        ;;
    esac
    assert_absent "$project/CLAUDE.md"
    assert_absent "$project/AGENTS.md"
    assert_absent "$project/.pi"
  done
)

case_dry_run() (
  set -e
  project="$TMP_ROOT/dry-run"
  mkdir -p "$project"
  "$SETUP" setup --root "$project" --claude --codex --pi --no-vscode --dry-run \
    > "$TMP_ROOT/dry-run.log"
  assert_absent "$project/IB"
  assert_absent "$project/.claude"
  assert_absent "$project/.agents"
  grep 'Dry-run complete' "$TMP_ROOT/dry-run.log" >/dev/null
)

case_opt_in_root_guidance() (
  set -e

  fresh="$TMP_ROOT/guidance fresh"
  mkdir -p "$fresh"
  "$SETUP" setup --root "$fresh" --claude --codex --pi \
    --register-guidance --no-vscode > "$TMP_ROOT/guidance-fresh.log"

  assert_file "$fresh/CLAUDE.md"
  assert_file "$fresh/AGENTS.md"
  grep -Fx '# Tressoir Guidance' "$fresh/CLAUDE.md" >/dev/null
  grep -Fx '@IB/TRESSOIR.md' "$fresh/CLAUDE.md" >/dev/null
  grep -Fx '# Tressoir Guidance' "$fresh/AGENTS.md" >/dev/null
  grep -Fx \
    'Before beginning substantial work, read and follow `IB/TRESSOIR.md`.' \
    "$fresh/AGENTS.md" >/dev/null
  assert_absent "$fresh/.claude/CLAUDE.md"
  assert_absent "$fresh/AGENTS.override.md"
  assert_absent "$fresh/.pi"

  digest_tree "$fresh" > "$TMP_ROOT/guidance-fresh-before.txt"
  "$SETUP" setup --root "$fresh" --claude --codex --pi \
    --register-guidance --no-vscode > "$TMP_ROOT/guidance-fresh-rerun.log"
  digest_tree "$fresh" > "$TMP_ROOT/guidance-fresh-after.txt"
  diff -u \
    "$TMP_ROOT/guidance-fresh-before.txt" \
    "$TMP_ROOT/guidance-fresh-after.txt"
  grep 'already registered: CLAUDE.md mentions TRESSOIR.md' \
    "$TMP_ROOT/guidance-fresh-rerun.log" >/dev/null
  grep 'already registered: AGENTS.md mentions TRESSOIR.md' \
    "$TMP_ROOT/guidance-fresh-rerun.log" >/dev/null
  [ "$(grep -c '^# Tressoir Guidance$' "$fresh/CLAUDE.md")" -eq 1 ]
  [ "$(grep -c '^# Tressoir Guidance$' "$fresh/AGENTS.md")" -eq 1 ]

  existing="$TMP_ROOT/guidance-existing"
  mkdir -p "$existing"
  printf '# Existing Claude\n\nKeep this text.\n' > "$existing/CLAUDE.md"
  printf '# Existing Agents\n\nAlready read OTHER/TRESSOIR.md.\n' \
    > "$existing/AGENTS.md"
  cp "$existing/CLAUDE.md" "$TMP_ROOT/guidance-existing-claude-before"
  cp "$existing/AGENTS.md" "$TMP_ROOT/guidance-existing-agents-before"

  "$SETUP" setup --root "$existing" --claude --codex \
    --register-guidance --no-vscode > "$TMP_ROOT/guidance-existing.log"

  sed -n '1,3p' "$existing/CLAUDE.md" |
    diff -u "$TMP_ROOT/guidance-existing-claude-before" -
  grep -Fx '# Tressoir Guidance' "$existing/CLAUDE.md" >/dev/null
  grep -Fx '@IB/TRESSOIR.md' "$existing/CLAUDE.md" >/dev/null
  cmp "$TMP_ROOT/guidance-existing-agents-before" "$existing/AGENTS.md"
  grep 'already registered: AGENTS.md mentions TRESSOIR.md' \
    "$TMP_ROOT/guidance-existing.log" >/dev/null

  claude_only="$TMP_ROOT/guidance-claude-only"
  codex_only="$TMP_ROOT/guidance-codex-only"
  pi_only="$TMP_ROOT/guidance-pi-only"
  mkdir -p "$claude_only" "$codex_only" "$pi_only"
  "$SETUP" setup --root "$claude_only" --claude \
    --register-guidance --no-vscode >/dev/null
  assert_file "$claude_only/CLAUDE.md"
  assert_absent "$claude_only/AGENTS.md"
  "$SETUP" setup --root "$codex_only" --codex \
    --register-guidance --no-vscode >/dev/null
  assert_file "$codex_only/AGENTS.md"
  assert_absent "$codex_only/CLAUDE.md"
  "$SETUP" setup --root "$pi_only" --pi \
    --register-guidance --no-vscode >/dev/null
  assert_file "$pi_only/AGENTS.md"
  assert_absent "$pi_only/CLAUDE.md"

  dry="$TMP_ROOT/guidance-dry"
  mkdir -p "$dry"
  "$SETUP" setup --root "$dry" --claude --codex \
    --register-guidance --no-vscode --dry-run \
    > "$TMP_ROOT/guidance-dry.log"
  assert_absent "$dry/IB"
  assert_absent "$dry/CLAUDE.md"
  assert_absent "$dry/AGENTS.md"
  grep 'would create root guidance file: CLAUDE.md' \
    "$TMP_ROOT/guidance-dry.log" >/dev/null
  grep 'would create root guidance file: AGENTS.md' \
    "$TMP_ROOT/guidance-dry.log" >/dev/null

  unsafe="$TMP_ROOT/guidance-unsafe"
  outside="$TMP_ROOT/guidance-outside"
  mkdir -p "$unsafe" "$outside" "$unsafe/AGENTS.md"
  printf 'OUTSIDE\n' > "$outside/CLAUDE.md"
  ln -s "$outside/CLAUDE.md" "$unsafe/CLAUDE.md"
  set +e
  "$SETUP" setup --root "$unsafe" --claude --codex \
    --register-guidance --no-vscode > "$TMP_ROOT/guidance-unsafe.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 2 ]
  grep -Fx 'OUTSIDE' "$outside/CLAUDE.md" >/dev/null
  [ -z "$(find "$unsafe/AGENTS.md" -mindepth 1 -print -quit)" ]
  grep 'refusing to edit a symlink' "$TMP_ROOT/guidance-unsafe.log" >/dev/null
  grep 'expected a regular file' "$TMP_ROOT/guidance-unsafe.log" >/dev/null

  extension_only="$TMP_ROOT/guidance-extension-only"
  mock="$TMP_ROOT/guidance-extension-only-code"
  state="$TMP_ROOT/guidance-extension-only.state"
  vsix="$TMP_ROOT/guidance-extension-only.vsix"
  mkdir -p "$extension_only"
  make_mock_code "$mock"
  make_mock_vsix "$vsix"
  set +e
  MOCK_CODE_STATE="$state" "$SETUP" setup --root "$extension_only" \
    --register-guidance --vsix "$vsix" --vscode-bin "$mock" \
    > "$TMP_ROOT/guidance-extension-only.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 1 ]
  assert_absent "$extension_only/IB"
  grep '\-\-register-guidance requires at least one selected harness' \
    "$TMP_ROOT/guidance-extension-only.log" >/dev/null
)

case_preserve_user_files_and_collisions() (
  set -e
  project="$TMP_ROOT/collisions"
  mkdir -p \
    "$project/IB/CANON" \
    "$project/IB/skills/tressoir-plan" \
    "$project/IB/skills/user-skill" \
    "$project/.claude/skills" \
    "$project/.claude/rules" \
    "$project/.agents/skills" \
    "$project/.pi"
  printf 'USER TASK\n' > "$project/IB/TASK.md"
  printf 'USER STATE\n' > "$project/IB/STATE.md"
  printf 'USER GUIDE\n' > "$project/IB/TRESSOIR.md"
  printf 'USER ROOT CANON\n' > "$project/IB/CANON/ROOT_CANON.md"
  printf 'USER IGNORE RULES\n' > "$project/IB/.gitignore"
  printf '%s\n' '---' 'name: tressoir-plan' 'description: User plan skill.' '---' \
    > "$project/IB/skills/tressoir-plan/SKILL.md"
  printf 'USER CANONICAL SKILL\n' > "$project/IB/skills/user-skill/SKILL.md"
  printf 'USER CLAUDE\n' > "$project/CLAUDE.md"
  printf 'USER NESTED CLAUDE\n' > "$project/.claude/CLAUDE.md"
  printf 'USER CLAUDE RULE\n' > "$project/.claude/rules/existing.md"
  printf 'USER AGENTS\n' > "$project/AGENTS.md"
  printf 'USER AGENTS OVERRIDE\n' > "$project/AGENTS.override.md"
  printf 'USER PI PROMPT\n' > "$project/.pi/APPEND_SYSTEM.md"
  printf 'USER PI SYSTEM\n' > "$project/.pi/SYSTEM.md"
  printf 'USER CLAUDE SKILL\n' > "$project/.claude/skills/tressoir-plan"
  printf 'USER CLAUDE EXTRA SKILL\n' > "$project/.claude/skills/user-skill"
  ln -s /tmp/foreign-target "$project/.agents/skills/tressoir-plan"
  printf 'USER AGENTS EXTRA SKILL\n' > "$project/.agents/skills/user-skill"

  # Guidance registration is omitted in this case, so all prompt files remain
  # byte-identical even though root CLAUDE.md and AGENTS.md lack TRESSOIR.md.
  for file in \
    "$project/IB/TASK.md" "$project/IB/STATE.md" "$project/IB/TRESSOIR.md" \
    "$project/IB/CANON/ROOT_CANON.md" \
    "$project/IB/.gitignore" \
    "$project/IB/skills/tressoir-plan/SKILL.md" \
    "$project/IB/skills/user-skill/SKILL.md" \
    "$project/CLAUDE.md" "$project/.claude/CLAUDE.md" \
    "$project/.claude/rules/existing.md" \
    "$project/AGENTS.md" "$project/AGENTS.override.md" \
    "$project/.pi/APPEND_SYSTEM.md" "$project/.pi/SYSTEM.md" \
    "$project/.claude/skills/tressoir-plan" \
    "$project/.claude/skills/user-skill" \
    "$project/.agents/skills/user-skill"; do
    shasum -a 256 "$file"
  done > "$TMP_ROOT/collision-before.txt"
  foreign_before=$(readlink "$project/.agents/skills/tressoir-plan")

  set +e
  "$SETUP" setup --root "$project" --claude --codex --pi --no-vscode \
    > "$TMP_ROOT/collision.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 2 ]

  for file in \
    "$project/IB/TASK.md" "$project/IB/STATE.md" "$project/IB/TRESSOIR.md" \
    "$project/IB/CANON/ROOT_CANON.md" \
    "$project/IB/.gitignore" \
    "$project/IB/skills/tressoir-plan/SKILL.md" \
    "$project/IB/skills/user-skill/SKILL.md" \
    "$project/CLAUDE.md" "$project/.claude/CLAUDE.md" \
    "$project/.claude/rules/existing.md" \
    "$project/AGENTS.md" "$project/AGENTS.override.md" \
    "$project/.pi/APPEND_SYSTEM.md" "$project/.pi/SYSTEM.md" \
    "$project/.claude/skills/tressoir-plan" \
    "$project/.claude/skills/user-skill" \
    "$project/.agents/skills/user-skill"; do
    shasum -a 256 "$file"
  done > "$TMP_ROOT/collision-after.txt"
  diff -u "$TMP_ROOT/collision-before.txt" "$TMP_ROOT/collision-after.txt"
  [ "$(readlink "$project/.agents/skills/tressoir-plan")" = "$foreign_before" ]

  assert_file "$project/.claude/rules/existing.md"
  grep 'preserved:' "$TMP_ROOT/collision.log" >/dev/null
  grep 'Setup never edits nested, override, rules, global, or Pi-specific prompt files' \
    "$TMP_ROOT/collision.log" >/dev/null
)

case_extension_failure_is_honest() (
  set -e
  project="$TMP_ROOT/extension-failure"
  mkdir -p "$project"
  mock="$TMP_ROOT/mock-code-failure"
  state="$TMP_ROOT/mock-code-failure.state"
  vsix="$TMP_ROOT/mock-failure.vsix"
  make_mock_code "$mock"
  make_mock_vsix "$vsix"

  set +e
  MOCK_CODE_STATE="$state" MOCK_CODE_FAIL_INSTALL=1 "$SETUP" setup \
    --root "$project" --claude --vsix "$vsix" --vscode-bin "$mock" \
    > "$TMP_ROOT/extension-failure.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 1 ]
  assert_file "$project/IB/TRESSOIR.md"
  grep 'extension installation failed after project setup' \
    "$TMP_ROOT/extension-failure.log" >/dev/null
)

case_reject_symlinked_managed_ancestor() (
  set -e
  project="$TMP_ROOT/symlink-ancestor"
  outside="$TMP_ROOT/outside"
  mkdir -p "$project" "$outside"
  ln -s "$outside" "$project/IB"

  set +e
  "$SETUP" setup --root "$project" --claude --no-vscode \
    > "$TMP_ROOT/symlink-ancestor.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 1 ]
  [ -z "$(find "$outside" -mindepth 1 -print -quit)" ]
  grep 'unsafe or incompatible canonical directory path' \
    "$TMP_ROOT/symlink-ancestor.log" >/dev/null
)

case_reject_unverified_payload_content() (
  set -e
  distribution="$TMP_ROOT/tampered-distribution"
  mkdir -p "$distribution"
  cp -R "$REPO/bin" "$distribution/bin"
  cp -R "$REPO/share" "$distribution/share"

  project_extra="$TMP_ROOT/payload-extra"
  mkdir -p "$project_extra"
  printf 'not checksummed\n' > \
    "$distribution/share/tressoir-external/skills/tressoir-plan/EXTRA.md"
  set +e
  "$distribution/bin/tressoir-external" setup \
    --root "$project_extra" --claude --no-vscode \
    > "$TMP_ROOT/payload-extra.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 1 ]
  assert_absent "$project_extra/IB"
  grep 'payload file set does not exactly match SHA256SUMS' \
    "$TMP_ROOT/payload-extra.log" >/dev/null

  rm "$distribution/share/tressoir-external/skills/tressoir-plan/EXTRA.md"
  project_link="$TMP_ROOT/payload-link"
  mkdir -p "$project_link"
  ln -s SKILL.md \
    "$distribution/share/tressoir-external/skills/tressoir-plan/UNVERIFIED.md"
  set +e
  "$distribution/bin/tressoir-external" setup \
    --root "$project_link" --claude --no-vscode \
    > "$TMP_ROOT/payload-link.log" 2>&1
  status=$?
  set -e
  [ "$status" -eq 1 ]
  assert_absent "$project_link/IB"
  grep 'payload must not contain symlinks' "$TMP_ROOT/payload-link.log" >/dev/null
)

run_case "fresh all-harness setup, extension install, and idempotent rerun" \
  case_fresh_all_with_extension
run_case "each harness installs only its skill adapter tree" case_each_harness
run_case "dry-run performs no mutation" case_dry_run
run_case "opt-in root guidance is contained, idempotent, and harness-specific" \
  case_opt_in_root_guidance
run_case "user files and occupied adapter paths are preserved" \
  case_preserve_user_files_and_collisions
run_case "extension failure reports committed project setup honestly" \
  case_extension_failure_is_honest
run_case "symlinked managed ancestor is rejected" \
  case_reject_symlinked_managed_ancestor
run_case "unverified payload files and symlinks are rejected" \
  case_reject_unverified_payload_content

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
