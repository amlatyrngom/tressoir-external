#!/usr/bin/env bash

# Exercises the portable `.tressoir.md` checker: advisory source/projection mtime warning,
# warn-only exit status, real lint errors still failing, and extension/portable runtime parity.

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P) || exit 1
CHECKER="$REPO/share/tressoir-external/skills/tressoir-artifact-md/scripts/check_md.js"
PORTABLE_ASSETS="$REPO/share/tressoir-external/skills/tressoir-artifact-md/references/runtime"
EXTENSION_ASSETS="$REPO/extension/src/notebook/assets"
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-md-checker-tests.XXXXXX") || exit 1
PASS=0
FAIL=0

cleanup() { rm -rf "$TMP_ROOT"; }
trap cleanup EXIT

pass() { PASS=$((PASS + 1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL: %s\n' "$1" >&2; }

run_case() {
  local name="$1" status
  shift
  ( set -e; "$@" )
  status=$?
  if [ "$status" -eq 0 ]; then
    pass "$name"
  else
    fail "$name"
  fi
}

# 1. A projection whose exact same-stem source is newer emits a warning but exits 0.
case_source_newer_warns() {
  local d="$TMP_ROOT/newer"
  mkdir -p "$d"
  printf -- '---\ntitle: T\n---\n# T\n' > "$d/PLAN.tressoir.md"
  sleep 1
  printf 'newer source\n' > "$d/PLAN.md"
  local out
  out=$(node "$CHECKER" "$d/PLAN.tressoir.md"); local status=$?
  [ "$status" -eq 0 ]
  printf '%s\n' "$out" | grep -F 'is newer than this projection' >/dev/null
}

# 2. A projection with no same-stem source emits no parity warning.
case_no_sibling_no_parity_warn() {
  local d="$TMP_ROOT/nosibling"
  mkdir -p "$d"
  printf -- '---\ntitle: T\n---\n# T\n' > "$d/PLAN.tressoir.md"
  local out
  out=$(node "$CHECKER" "$d/PLAN.tressoir.md"); local status=$?
  [ "$status" -eq 0 ]
  ! printf '%s\n' "$out" | grep -F 'is newer than this projection' >/dev/null
}

# 3. A real lint error (an input with no key) still exits 1.
case_lint_error_exits_1() {
  local d="$TMP_ROOT/error"
  mkdir -p "$d"
  printf -- '---\ntitle: T\n---\n\n:::input\nA question with no key.\n:::\n' > "$d/PLAN.tressoir.md"
  set +e
  node "$CHECKER" "$d/PLAN.tressoir.md" >/dev/null 2>&1
  local status=$?
  set -e
  [ "$status" -eq 1 ]
}

# 4. Advisory warnings alone (duplicate keys, lifecycle, orphan snippet) keep exit 0.
case_advisory_warnings_exit_0() {
  local d="$TMP_ROOT/advisory"
  mkdir -p "$d"
  cat > "$d/PLAN.tressoir.md" <<'MD'
---
title: T
---

::::card{title="M1" oneliner="x" state="<span class='badge warn'>Planning</span>"}
#### Planning Overview
:::item{oneliner="x"}
y
:::
::::

```diff
orphan
```
MD
  local out
  out=$(node "$CHECKER" "$d/PLAN.tressoir.md"); local status=$?
  [ "$status" -eq 0 ]
  printf '%s\n' "$out" | grep -F 'orphan snippet' >/dev/null
  printf '%s\n' "$out" | grep -F 'has no `#### Planned Changes`' >/dev/null
}

# 5. The extension runtime and the portable runtime produce identical findings.
case_extension_portable_parity() {
  local d="$TMP_ROOT/parity"
  mkdir -p "$d"
  cat > "$d/PLAN.tressoir.md" <<'MD'
---
title: T
---

::::card{title="M1" oneliner="x" state="<span class='badge warn'>Planning</span>"}
#### Planning Overview
:::item{oneliner="x"}
y
:::
::::

:::input{key=dup}
Q1?
:::
:::input{key=dup}
Q2?
:::
MD
  local portable extension
  portable=$(node "$CHECKER" --assets="$PORTABLE_ASSETS" "$d/PLAN.tressoir.md" 2>&1)
  extension=$(node "$CHECKER" --assets="$EXTENSION_ASSETS" "$d/PLAN.tressoir.md" 2>&1)
  [ "$portable" = "$extension" ]
}

run_case "source newer than projection warns with exit 0" case_source_newer_warns
run_case "no same-stem source produces no parity warning" case_no_sibling_no_parity_warn
run_case "a real lint error still exits 1" case_lint_error_exits_1
run_case "advisory warnings alone keep exit 0" case_advisory_warnings_exit_0
run_case "extension and portable runtimes agree on findings" case_extension_portable_parity

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
