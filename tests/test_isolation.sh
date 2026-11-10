#!/usr/bin/env bash

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P) || exit 1
HELPER="$REPO/extras/tressoir-isolation/templates/agent-setup.template.sh"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-isolation-tests.XXXXXX") || exit 1
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

fail_case() {
  FAIL=$((FAIL + 1))
  printf 'FAIL: %s\n' "$1" >&2
}

make_mock_tools() {
  local tools command
  tools="$TMP_ROOT/tools"
  mkdir "$tools"

  cat > "$tools/id" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  -u) printf '%s\n' 1000 ;;
  -g) printf '%s\n' 1000 ;;
  -un) printf '%s\n' vscode ;;
  -gn) printf '%s\n' vscode ;;
  *) exit 2 ;;
esac
EOF

  cat > "$tools/sudo" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${TRESSOIR_TEST_SUDO_LOG:?}"
case "${1:-}" in
  -n) [ "${2:-}" = true ] ;;
  chown) exit 0 ;;
  *) exit 3 ;;
esac
EOF

  cat > "$tools/npm" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${TRESSOIR_TEST_NPM_LOG:?}"
EOF

  for command in node claude codex pi; do
    cat > "$tools/$command" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  done
  chmod +x "$tools"/*
}

run_user_helper() {
  local name targets expected home workspace npm_log sudo_log
  name="$1"
  targets="$2"
  expected="$3"
  home="$TMP_ROOT/home-$name"
  workspace="$TMP_ROOT/workspace-$name"
  npm_log="$TMP_ROOT/npm-$name.log"
  sudo_log="$TMP_ROOT/sudo-$name.log"
  mkdir "$home" "$workspace"

  (
    cd "$workspace" || exit 1
    HOME="$home" \
    XDG_CACHE_HOME="$home/.cache" \
    XDG_CONFIG_HOME="$home/.config" \
    XDG_DATA_HOME="$home/.local/share" \
    XDG_STATE_HOME="$home/.local/state" \
    NVM_DIR="" \
    TRESSOIR_AGENT_TARGETS="$targets" \
    TRESSOIR_TEST_NPM_LOG="$npm_log" \
    TRESSOIR_TEST_SUDO_LOG="$sudo_log" \
    PATH="$TMP_ROOT/tools:$PATH" \
      bash "$HELPER" --user > "$TMP_ROOT/$name.out"
  ) || return 1

  grep -Fx -- '-n true' "$sudo_log" >/dev/null || return 1
  grep -Fx -- "chown -R 1000:1000 $home" "$sudo_log" >/dev/null || return 1
  [ -d "$home/.cache" ] && [ -w "$home/.cache" ] || return 1
  [ -d "$home/.config" ] && [ -d "$home/.local/bin" ] || return 1
  grep -Fx -- "$expected" "$npm_log" >/dev/null || return 1
}

make_mock_tools

if run_user_helper all "claude,codex,pi" \
  'install --global --no-audit --no-fund @anthropic-ai/claude-code@latest @openai/codex@latest @earendil-works/pi-coding-agent@latest'; then
  pass "user setup repairs home and installs all selected CLIs without sudo"
else
  fail_case "user setup repairs home and installs all selected CLIs without sudo"
fi

if run_user_helper pi-only "pi" \
  'install --global --no-audit --no-fund @earendil-works/pi-coding-agent@latest'; then
  pass "user setup installs only the selected Pi CLI"
else
  fail_case "user setup installs only the selected Pi CLI"
fi

invalid_home="$TMP_ROOT/invalid-home"
invalid_workspace="$TMP_ROOT/invalid-workspace"
mkdir "$invalid_home" "$invalid_workspace"
if (
  cd "$invalid_workspace" || exit 1
  HOME="$invalid_home" PATH="$TMP_ROOT/tools:$PATH" \
    TRESSOIR_TEST_NPM_LOG="$TMP_ROOT/invalid-npm.log" \
    TRESSOIR_TEST_SUDO_LOG="$TMP_ROOT/invalid-sudo.log" \
    bash "$HELPER" --unknown >/dev/null 2>&1
); then
  fail_case "unknown helper mode fails clearly"
else
  pass "unknown helper mode fails clearly"
fi

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
