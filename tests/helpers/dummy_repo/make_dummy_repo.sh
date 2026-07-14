#!/usr/bin/env bash

# Create a disposable, intentionally collision-rich Git repository for manually
# testing Tressoir External setup. Compatible with macOS Bash 3.2+.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 1
DEFAULT_DEST="$SCRIPT_DIR/dummy_repo"
CREATED_DEST=""

usage() {
  cat <<'EOF'
Usage:
  make_dummy_repo.sh [DESTINATION]

Creates a new Git repository at DESTINATION. If omitted, DESTINATION is:
  ./dummy_repo

The repository contains user-owned IB files, harness instructions, unrelated
skills, and deliberate same-name collisions. This lets you test:

  - non-clobbering: protected bytes and symlink targets remain unchanged;
  - idempotence: a second identical setup changes nothing;
  - multi-harness setup: Claude, Codex, and Pi adapters are created together.

The destination must not already exist. This script never replaces it.
After creation, read DESTINATION/TESTING.md.
EOF
}

fatal() {
  printf 'fatal: %s\n' "$*" >&2
  exit 1
}

occupied() {
  [ -e "$1" ] || [ -L "$1" ]
}

cleanup_on_failure() {
  status=$?
  if [ "$status" -ne 0 ] && [ -n "$CREATED_DEST" ] && [ -d "$CREATED_DEST" ]; then
    rm -rf "$CREATED_DEST"
  fi
  exit "$status"
}
trap cleanup_on_failure EXIT HUP INT TERM

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    fatal "need shasum, sha256sum, or openssl"
  fi
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

[ "$#" -le 1 ] || {
  usage >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fatal "git is required"

DEST_INPUT=${1:-$DEFAULT_DEST}
case "$DEST_INPUT" in
  "") fatal "destination must not be empty" ;;
esac

PARENT_INPUT=$(dirname -- "$DEST_INPUT")
NAME=$(basename -- "$DEST_INPUT")
[ "$NAME" != "." ] && [ "$NAME" != ".." ] && [ -n "$NAME" ] ||
  fatal "invalid destination: $DEST_INPUT"
mkdir -p "$PARENT_INPUT" || fatal "could not create destination parent: $PARENT_INPUT"
PARENT=$(CDPATH= cd -- "$PARENT_INPUT" 2>/dev/null && pwd -P) ||
  fatal "could not resolve destination parent: $PARENT_INPUT"
DEST="$PARENT/$NAME"

occupied "$DEST" && fatal "destination already exists; refusing to replace it: $DEST"
mkdir "$DEST" || fatal "could not create destination: $DEST"
CREATED_DEST="$DEST"

mkdir -p \
  "$DEST/docs" \
  "$DEST/src" \
  "$DEST/IB/ARTIFACTS/EXISTING_WORK" \
  "$DEST/IB/CANON" \
  "$DEST/IB/skills/tressoir-plan" \
  "$DEST/IB/skills/acme-project-skill" \
  "$DEST/.claude/rules" \
  "$DEST/.claude/skills/acme-review" \
  "$DEST/.agents/skills/acme-review" \
  "$DEST/.pi" \
  "$DEST/foreign/plan-skill" \
  "$DEST/.dummy-test" || fatal "could not create fixture directories"

cat > "$DEST/README.md" <<'EOF'
# Dummy Existing Project

This repository intentionally predates Tressoir External setup. Its user-owned
files and deliberate collisions must survive setup byte-for-byte.
EOF

cat > "$DEST/docs/user notes.md" <<'EOF'
# Notes with a space in the path

This tests preservation and project-root/path handling.
EOF

cat > "$DEST/src/hello.txt" <<'EOF'
ordinary project source; setup must not modify this
EOF

cat > "$DEST/.gitignore" <<'EOF'
.env
build/
EOF

cat > "$DEST/CLAUDE.md" <<'EOF'
# User Claude instructions

Keep this exact text. Do not append Tressoir guidance automatically.
EOF

cat > "$DEST/.claude/CLAUDE.md" <<'EOF'
# Nested user Claude instructions

This file tests preservation of an alternate Claude instruction location.
EOF

cat > "$DEST/.claude/rules/existing.md" <<'EOF'
# Existing Claude rule

Setup must not create, replace, or edit rule files.
EOF

cat > "$DEST/AGENTS.md" <<'EOF'
# User Codex/Pi instructions

This is user-owned and must remain byte-identical.
EOF

cat > "$DEST/AGENTS.override.md" <<'EOF'
# User override instructions

Preserve this higher-precedence file exactly.
EOF

cat > "$DEST/.pi/APPEND_SYSTEM.md" <<'EOF'
# User Pi append prompt

Setup must not change this prompt.
EOF

cat > "$DEST/.pi/SYSTEM.md" <<'EOF'
# User Pi system prompt

Setup must not change this prompt.
EOF

cat > "$DEST/IB/TASK.md" <<'EOF'
# User task

This is an explicit-request-only user scratchpad. Preserve it exactly.
EOF

cat > "$DEST/IB/STATE.md" <<'EOF'
# Existing project state

- Existing decision: keep this fixture content unchanged.
EOF

cat > "$DEST/IB/TRESSOIR.md" <<'EOF'
# Existing project-specific Tressoir agreement

This deliberately differs from the payload and must not be replaced.
EOF

cat > "$DEST/IB/.gitignore" <<'EOF'
# Existing project-owned IB ignore rules
TMP/
private-notes/
EOF

cat > "$DEST/IB/CANON/ROOT_CANON.md" <<'EOF'
# Existing Root Canon

- Existing invariant: setup is non-clobbering.
EOF

cat > "$DEST/IB/ARTIFACTS/EXISTING_WORK/NOTES.md" <<'EOF'
# Existing artifact

This durable artifact must remain byte-identical.
EOF

cat > "$DEST/IB/ARTIFACTS/EXISTING_WORK/interactions.json" <<'EOF'
{
  "existing.choice": "keep-me"
}
EOF

cat > "$DEST/IB/skills/tressoir-plan/SKILL.md" <<'EOF'
---
name: tressoir-plan
description: Existing project-specific plan skill used to test canonical-skill collision preservation.
---

# Existing Project Plan Skill

This deliberately differs from the distributed skill and must be preserved.
EOF

cat > "$DEST/IB/skills/acme-project-skill/SKILL.md" <<'EOF'
---
name: acme-project-skill
description: Existing unrelated canonical project skill.
---

# ACME Project Skill

Unrelated skills must survive setup.
EOF

cat > "$DEST/.claude/skills/tressoir-plan" <<'EOF'
occupied Claude adapter path; preserve this regular file
EOF

cat > "$DEST/.claude/skills/acme-review/SKILL.md" <<'EOF'
---
name: acme-review
description: Existing unrelated Claude skill.
---

# ACME Review
EOF

cat > "$DEST/.agents/skills/acme-review/SKILL.md" <<'EOF'
---
name: acme-review
description: Existing unrelated Codex/Pi skill.
---

# ACME Review
EOF

cat > "$DEST/foreign/plan-skill/SKILL.md" <<'EOF'
---
name: foreign-plan
description: Deliberate foreign target for a wrong-target adapter collision.
---

# Foreign Plan Skill
EOF

ln -s "../../foreign/plan-skill" "$DEST/.agents/skills/tressoir-plan" ||
  fatal "could not create deliberate wrong-target symlink"

cat > "$DEST/.dummy-test/verify_preserved.sh" <<'EOF'
#!/usr/bin/env bash
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd -P) || exit 1
MANIFEST="$ROOT/.dummy-test/baseline.tsv"
FAIL=0

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    printf 'No SHA-256 tool found.\n' >&2
    exit 1
  fi
}

TAB=$(printf '\tX')
TAB=${TAB%X}
while IFS="$TAB" read -r kind expected relative || [ -n "$kind$expected$relative" ]; do
  [ -n "$kind" ] || continue
  path="$ROOT/$relative"
  case "$kind" in
    F)
      if [ ! -f "$path" ] || [ -L "$path" ]; then
        printf 'CHANGED type/missing file: %s\n' "$relative" >&2
        FAIL=1
      else
        actual=$(hash_file "$path")
        if [ "$actual" != "$expected" ]; then
          printf 'CHANGED bytes: %s\n' "$relative" >&2
          FAIL=1
        fi
      fi
      ;;
    L)
      if [ ! -L "$path" ]; then
        printf 'CHANGED type/missing symlink: %s\n' "$relative" >&2
        FAIL=1
      else
        actual=$(readlink "$path" 2>/dev/null || true)
        if [ "$actual" != "$expected" ]; then
          printf 'CHANGED symlink target: %s\n' "$relative" >&2
          FAIL=1
        fi
      fi
      ;;
    *)
      printf 'Invalid baseline record: %s\n' "$kind" >&2
      exit 1
      ;;
  esac
done < "$MANIFEST"

if [ "$FAIL" -ne 0 ]; then
  printf 'Non-clobbering verification FAILED.\n' >&2
  exit 1
fi
printf 'Non-clobbering verification passed: all protected bytes and symlink targets are unchanged.\n'
EOF
chmod +x "$DEST/.dummy-test/verify_preserved.sh"

cat > "$DEST/.dummy-test/tree_digest.sh" <<'EOF'
#!/usr/bin/env bash
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd -P) || exit 1

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    printf 'No SHA-256 tool found.\n' >&2
    exit 1
  fi
}

cd "$ROOT" || exit 1
find . -path './.git' -prune -o -type f -print | LC_ALL=C sort |
while IFS= read -r file; do
  printf 'F\t%s\t%s\n' "$(hash_file "$file")" "${file#./}"
done
find . -path './.git' -prune -o -type l -print | LC_ALL=C sort |
while IFS= read -r link; do
  printf 'L\t%s\t%s\n' "$(readlink "$link")" "${link#./}"
done
EOF
chmod +x "$DEST/.dummy-test/tree_digest.sh"

PROTECTED_FILES=(
  "README.md"
  "docs/user notes.md"
  "src/hello.txt"
  ".gitignore"
  "CLAUDE.md"
  ".claude/CLAUDE.md"
  ".claude/rules/existing.md"
  "AGENTS.md"
  "AGENTS.override.md"
  ".pi/APPEND_SYSTEM.md"
  ".pi/SYSTEM.md"
  "IB/TASK.md"
  "IB/STATE.md"
  "IB/TRESSOIR.md"
  "IB/.gitignore"
  "IB/CANON/ROOT_CANON.md"
  "IB/ARTIFACTS/EXISTING_WORK/NOTES.md"
  "IB/ARTIFACTS/EXISTING_WORK/interactions.json"
  "IB/skills/tressoir-plan/SKILL.md"
  "IB/skills/acme-project-skill/SKILL.md"
  ".claude/skills/tressoir-plan"
  ".claude/skills/acme-review/SKILL.md"
  ".agents/skills/acme-review/SKILL.md"
  "foreign/plan-skill/SKILL.md"
)

: > "$DEST/.dummy-test/baseline.tsv"
for relative in "${PROTECTED_FILES[@]}"; do
  printf 'F\t%s\t%s\n' "$(hash_file "$DEST/$relative")" "$relative" \
    >> "$DEST/.dummy-test/baseline.tsv"
done
printf 'L\t%s\t%s\n' "$(readlink "$DEST/.agents/skills/tressoir-plan")" \
  ".agents/skills/tressoir-plan" >> "$DEST/.dummy-test/baseline.tsv"

cat > "$DEST/TESTING.md" <<'EOF'
# Manual Tressoir External Setup Test

This fixture intentionally contains user-owned files and two same-name adapter
collisions. Setup should preserve them and return status **2** (safe degradation),
while installing all non-colliding skills for all three harnesses.

From this repository, point `TRESSOIR_EXTERNAL` at the distribution checkout:

```bash
export TRESSOIR_EXTERNAL=/path/to/tressoir_external
```

## 1. Run all three harnesses

```bash
set +e
"$TRESSOIR_EXTERNAL/bin/tressoir-external" setup \
  --root "$PWD" --claude --codex --pi --no-vscode
status=$?
set -e
printf 'setup status: %s (expected 2)\n' "$status"
test "$status" -eq 2
```

To test the VS Code phase too, build the extension in the distribution checkout
and replace `--no-vscode` with:

```bash
--vsix "$TRESSOIR_EXTERNAL/extension/dist/tressoir-artifacts-0.1.1.vsix"
```

## 2. Verify non-clobbering and multi-harness links

```bash
./.dummy-test/verify_preserved.sh

test -L .claude/skills/tressoir-artifact-md
test -L .agents/skills/tressoir-artifact-md
test "$(readlink .claude/skills/tressoir-artifact-md)" = \
  '../../IB/skills/tressoir-artifact-md'
test "$(readlink .agents/skills/tressoir-artifact-md)" = \
  '../../IB/skills/tressoir-artifact-md'

for skill in \
  tressoir-artifact-md tressoir-artifact-html tressoir-working-area \
  tressoir-memory tressoir-structured-review; do
  test -L ".claude/skills/$skill"
  test -L ".agents/skills/$skill"
done

# Deliberate collisions remain untouched:
test -f .claude/skills/tressoir-plan
test "$(readlink .agents/skills/tressoir-plan)" = \
  '../../foreign/plan-skill'
```

Codex and Pi intentionally share `.agents/skills/`; Claude uses
`.claude/skills/`. Setup must not create or edit harness instruction files.
`git status --short` is also useful here: it should show only newly created
Tressoir scaffold/adapter paths, never modifications to committed user files.

## 3. Verify idempotence

Capture the complete post-setup tree, rerun the identical command, then compare:

```bash
before=$(mktemp)
after=$(mktemp)
./.dummy-test/tree_digest.sh > "$before"

set +e
"$TRESSOIR_EXTERNAL/bin/tressoir-external" setup \
  --root "$PWD" --claude --codex --pi --no-vscode
status=$?
set -e
test "$status" -eq 2

./.dummy-test/tree_digest.sh > "$after"
diff -u "$before" "$after"
rm -f "$before" "$after"
```

No diff means the second run changed no project file bytes or symlink targets.
Status 2 remains expected because the deliberate collisions are still safely
preserved and still require manual resolution.

## Reset

Delete this entire dummy repository and rerun `make_dummy_repo.sh`. The creator
refuses to replace an existing destination.
EOF

(
  cd "$DEST" || exit 1
  git init -q
  git add -A
  git -c user.name='Tressoir Dummy Fixture' \
      -c user.email='dummy@example.invalid' \
      commit -q -m 'Create pre-Tressoir dummy project'
) || fatal "could not initialize and commit the dummy repository"

trap - EXIT HUP INT TERM
CREATED_DEST=""
printf 'Created dummy test repository: %s\n' "$DEST"
printf 'Next: cd %q && cat TESTING.md\n' "$DEST"
