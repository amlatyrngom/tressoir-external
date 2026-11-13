#!/usr/bin/env bash

# Tests for install.sh. Each case runs in its own empty folder under a temporary directory.
#   bash tests/test_install.sh

set -u

KIT=$(cd "$(dirname "$0")/.." && pwd -P)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-install-tests.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

ok() { PASS=$((PASS + 1)); printf 'PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL: %s\n' "$1" >&2; }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }   # check <name> <condition>
project() { mkdir -p "$TMP/$1"; cd "$TMP/$1" || exit 1; }
install() { bash "$KIT/install.sh" "$@" > "$TMP/out.txt" 2>&1; }
# Every file and link under the project with its content hash or link target.
snapshot() {
  find . \( -type f -o -type l \) | LC_ALL=C sort | while read -r path; do
    if [ -L "$path" ]; then printf '%s -> %s\n' "$path" "$(readlink "$path")"
    else printf '%s %s\n' "$path" "$(shasum -a 256 < "$path" | cut -c1-16)"; fi
  done
}

# 1. A fresh install produces the layout.
project fresh
install; check "fresh install succeeds" '[ $? -eq 0 ]'
for path in WORK/WORK_AREA_GUIDE.md WORK/STATE.md WORK/TASK.md WORK/.gitignore WORK/MEMORY/ROOT_MEMORY.md \
            WORK/MEMORY/EXAMPLES/README.md WORK/skills/tressoir-memory/SKILL.md WORK/skills/tressoir-plan/SKILL.md \
            WORK/skills/tressoir-migrate/SKILL.md WORK/skills/tressoir-present/SKILL.md WORK/skills/tressoir-present/present.py \
            WORK/skills/tressoir-present/slides.css WORK/skills/tressoir-present/player/player.js \
            WORK/skills/tressoir-present/player/player.css AGENTS.md CLAUDE.md .claude/settings.json; do
  check "fresh install has $path" '[ -f "$path" ]'
done
check "fresh install has WORK/ARTIFACTS and WORK/TMP" '[ -d WORK/ARTIFACTS ] && [ -d WORK/TMP ]'
for name in tressoir-memory tressoir-plan tressoir-present tressoir-migrate; do
  check "$name is linked for Claude and for agents" \
    '[ -f ".claude/skills/$name/SKILL.md" ] && [ -f ".agents/skills/$name/SKILL.md" ] && [ "$(readlink .claude/skills/$name)" = "../../WORK/skills/$name" ]'
done
check "the guide is the kit's guide" 'cmp -s WORK/WORK_AREA_GUIDE.md "$KIT/guide/WORK_AREA_GUIDE.md"'
check "AGENTS.md is the three-line pointer" '[ "$(wc -l < AGENTS.md | tr -d " ")" = 3 ] && grep -q "WORK/WORK_AREA_GUIDE.md" AGENTS.md && grep -q "WORK/STATE.md" AGENTS.md && grep -q "WORK/MEMORY/ROOT_MEMORY.md" AGENTS.md'
check "CLAUDE.md is the single line @AGENTS.md" '[ "$(cat CLAUDE.md)" = "@AGENTS.md" ]'
check "the optional extra is not installed" '[ ! -e WORK/skills/tressoir-structured-review ]'
check "without its option nothing of the system view is installed" '[ ! -e WORK/skills/tressoir-system-view ] && [ ! -e WORK/SYSTEM_VIEW ] && [ ! -e .claude/skills/tressoir-system-view ] && ! grep -qi "system view" "$TMP/out.txt"'
check "nothing from the first kit is installed" '! find . -name "*.tressoir.*" -o -name "interactions.json" -o -name "TRESSOIR.md" | grep -q .'

# 2. A second run changes nothing, with or without --override.
snapshot > "$TMP/before.txt"
install; snapshot > "$TMP/after.txt"
check "second run changes nothing" 'cmp -s "$TMP/before.txt" "$TMP/after.txt" && grep -q "nothing to do" "$TMP/out.txt"'
install --override; snapshot > "$TMP/after.txt"
check "--override on an untouched install changes nothing" 'cmp -s "$TMP/before.txt" "$TMP/after.txt" && grep -q "nothing to do" "$TMP/out.txt"'

# 3. --override refreshes what the kit owns and leaves the rest alone.
echo "my state" >> WORK/STATE.md; echo "my task" >> WORK/TASK.md; echo "my memory" >> WORK/MEMORY/ROOT_MEMORY.md
echo "subject" > WORK/MEMORY/BUILD_MEMORY.md; mkdir -p WORK/ARTIFACTS/THING; echo "result" > WORK/ARTIFACTS/THING/report.md
mkdir -p WORK/skills/my-skill; printf -- '---\nname: my-skill\n---\nmine\n' > WORK/skills/my-skill/SKILL.md
echo "my ignore" >> WORK/.gitignore; echo "# my notes" >> AGENTS.md
echo "edited" >> WORK/WORK_AREA_GUIDE.md; echo "edited" >> WORK/skills/tressoir-memory/SKILL.md
rm WORK/skills/tressoir-present/present.py; echo "stray" > WORK/skills/tressoir-present/old-file.txt
snapshot | grep -E 'STATE.md|TASK.md|MEMORY/|ARTIFACTS/|my-skill/|WORK/.gitignore|AGENTS.md' > "$TMP/mine-before.txt"
install
check "without --override, edited kit files are kept and reported" 'grep -q "edited" WORK/WORK_AREA_GUIDE.md && grep -q "kept WORK/WORK_AREA_GUIDE.md" "$TMP/out.txt" && [ ! -e WORK/skills/tressoir-present/present.py ]'
check "a skill of mine gets its links" '[ -f .claude/skills/my-skill/SKILL.md ] && [ -f .agents/skills/my-skill/SKILL.md ]'
install --override
check "--override refreshes the guide" 'cmp -s WORK/WORK_AREA_GUIDE.md "$KIT/guide/WORK_AREA_GUIDE.md"'
check "--override refreshes the kit's skills and scripts" 'diff -rq "$KIT/skills/tressoir-memory" WORK/skills/tressoir-memory >/dev/null && diff -rq "$KIT/skills/tressoir-present" WORK/skills/tressoir-present >/dev/null'
snapshot | grep -E 'STATE.md|TASK.md|MEMORY/|ARTIFACTS/|my-skill/|WORK/.gitignore|AGENTS.md' > "$TMP/mine-after.txt"
check "--override leaves state, task, memory, artifacts, my skill and my notes untouched" 'cmp -s "$TMP/mine-before.txt" "$TMP/mine-after.txt"'

# 4. Existing root guidance is appended to, once.
project guidance
printf '# House rules\n\nBe kind.\n' > AGENTS.md; printf '# Claude notes\n\nUse tabs.\n' > CLAUDE.md
mkdir -p .claude; printf '{ "model": "x" }\n' > .claude/settings.json
install; install
check "AGENTS.md keeps its content and gains one pointer" 'grep -q "Be kind." AGENTS.md && [ "$(grep -c "WORK/WORK_AREA_GUIDE.md" AGENTS.md)" = 1 ]'
check "CLAUDE.md keeps its content and gains one @AGENTS.md" 'grep -q "Use tabs." CLAUDE.md && [ "$(grep -cx "@AGENTS.md" CLAUDE.md)" = 1 ]'
check "an existing Claude settings file is left alone, with a note" '[ "$(cat .claude/settings.json)" = "{ \"model\": \"x\" }" ] && grep -q "autoMemoryEnabled" "$TMP/out.txt"'

# 5. A project still on the first kit's layout is refused, untouched.
project old-layout
mkdir -p IB/skills; echo state > IB/STATE.md
snapshot > "$TMP/before.txt"
install; status=$?; snapshot > "$TMP/after.txt"
check "an IB/ project is refused and pointed at the migration skill" '[ $status -ne 0 ] && grep -q "tressoir-migrate" "$TMP/out.txt" && cmp -s "$TMP/before.txt" "$TMP/after.txt"'

# 6. After the rename, --override swaps the first kit's skills and pointer.
project renamed
OLD_POINTER=$(printf '# Tressoir Guidance\n\nBefore substantial work, read and follow `IB/TRESSOIR.md`.\nRead current status and open decisions in `IB/STATE.md`.\nRead durable project decisions in `IB/CANON/ROOT_CANON.md`.')
printf '%s\n' "$OLD_POINTER" > CLAUDE.md; printf '# Mine\n\nKeep this.\n\n%s\n' "$OLD_POINTER" > AGENTS.md
mkdir -p WORK/MEMORY .claude/skills .agents/skills; echo kept > WORK/STATE.md; echo kept > WORK/MEMORY/ROOT_MEMORY.md
for name in tressoir-working-area tressoir-canon tressoir-artifact-md tressoir-artifact-html tressoir-isolation tressoir-plan tressoir-structured-review slidev; do
  mkdir -p "WORK/skills/$name"; echo "old $name" > "WORK/skills/$name/SKILL.md"
  ln -s "../../IB/skills/$name" ".claude/skills/$name"; ln -s "../../WORK/skills/$name" ".agents/skills/$name"
done
install --override
check "retired skills and their links are removed" '! ls WORK/skills .claude/skills .agents/skills | grep -qE "working-area|canon|artifact|isolation"'
check "the plan skill is replaced by the current one" 'cmp -s WORK/skills/tressoir-plan/SKILL.md "$KIT/skills/tressoir-plan/SKILL.md"'
check "an extra the project already had is refreshed" 'cmp -s WORK/skills/tressoir-structured-review/SKILL.md "$KIT/extras/tressoir-structured-review/SKILL.md"'
check "kit links pointing into IB/ are re-pointed" '[ "$(readlink .claude/skills/tressoir-plan)" = "../../WORK/skills/tressoir-plan" ]'
check "my own skill and its link are left as they were" '[ "$(cat WORK/skills/slidev/SKILL.md)" = "old slidev" ] && [ "$(readlink .claude/skills/slidev)" = "../../IB/skills/slidev" ] && grep -q "kept .claude/skills/slidev" "$TMP/out.txt"'
check "the old pointer is gone from AGENTS.md, my text stays, the new pointer is added" '! grep -q "IB/" AGENTS.md && grep -q "Keep this." AGENTS.md && grep -q "WORK/WORK_AREA_GUIDE.md" AGENTS.md'
check "CLAUDE.md becomes the single line @AGENTS.md" '[ "$(cat CLAUDE.md)" = "@AGENTS.md" ]'
check "existing state and memory are untouched, and no seed is added to MEMORY/" '[ "$(cat WORK/STATE.md)" = kept ] && [ "$(cat WORK/MEMORY/ROOT_MEMORY.md)" = kept ] && [ ! -e WORK/MEMORY/EXAMPLES ]'

# 7. The piped form downloads the kit and gives the same result as a checkout.
tar -czf "$TMP/kit.tar.gz" -C "$(dirname "$KIT")" --exclude .git "$(basename "$KIT")"
project piped
TRESSOIR_ARCHIVE_URL="file://$TMP/kit.tar.gz" bash -s < "$KIT/install.sh" > "$TMP/out.txt" 2>&1
check "the piped form installs from a download" '[ $? -eq 0 ] && diff -rq "$TMP/fresh/WORK/skills/tressoir-present" WORK/skills/tressoir-present >/dev/null && [ -f AGENTS.md ]'

# 8. Options.
project options
install --claude; check "an unknown option is refused" '[ $? -ne 0 ] && [ ! -e WORK ]'

# 9. The system view, an experimental extra added only with its option.
project system-view
install --experimental-system-view; check "the system view option installs" '[ $? -eq 0 ]'
for path in WORK/skills/tressoir-system-view/SKILL.md WORK/skills/tressoir-system-view/system_view.py \
            WORK/skills/tressoir-system-view/view/page.html WORK/skills/tressoir-system-view/examples/tally/system.json \
            WORK/SYSTEM_VIEW/system.json WORK/SYSTEM_VIEW/changes.json WORK/SYSTEM_VIEW/FEEDBACK.md WORK/STATE.md AGENTS.md; do
  check "with the option there is $path" '[ -f "$path" ]'
done
check "the system view skill is linked for Claude and for agents" \
  '[ -f .claude/skills/tressoir-system-view/SKILL.md ] && [ "$(readlink .agents/skills/tressoir-system-view)" = "../../WORK/skills/tressoir-system-view" ]'
check "it says in three lines that this is experimental and where feedback goes" \
  '[ "$(tail -n 4 "$TMP/out.txt" | head -n 3)" = "The system view is experimental.
Feedback goes in WORK/SYSTEM_VIEW/FEEDBACK.md.
It is applied to the kit from time to time." ]'
check "the starting files are the kit's seeds" 'diff -q "$KIT/extras/tressoir-system-view/seeds/system.json" WORK/SYSTEM_VIEW/system.json >/dev/null && [ "$(cat WORK/SYSTEM_VIEW/changes.json)" = "[]" ]'
snapshot > "$TMP/before.txt"
install --experimental-system-view; snapshot > "$TMP/after.txt"
check "a second run with the option changes nothing" 'cmp -s "$TMP/before.txt" "$TMP/after.txt" && grep -q "nothing to do" "$TMP/out.txt"'
install; snapshot > "$TMP/after.txt"
check "a run without the option leaves the system view in place" 'cmp -s "$TMP/before.txt" "$TMP/after.txt" && ! grep -qi "experimental" "$TMP/out.txt"'
echo '{ "name": "Mine" }' > WORK/SYSTEM_VIEW/system.json; echo "2026-01-01 a remark" >> WORK/SYSTEM_VIEW/FEEDBACK.md
rm WORK/SYSTEM_VIEW/changes.json; echo "edited" >> WORK/skills/tressoir-system-view/system_view.py
install --experimental-system-view
check "files that exist in WORK/SYSTEM_VIEW/ are never overwritten, and a missing one is created again" \
  '[ "$(cat WORK/SYSTEM_VIEW/system.json)" = "{ \"name\": \"Mine\" }" ] && grep -q "a remark" WORK/SYSTEM_VIEW/FEEDBACK.md && [ "$(cat WORK/SYSTEM_VIEW/changes.json)" = "[]" ]'
check "without --override an edited script is kept and reported" 'grep -q "edited" WORK/skills/tressoir-system-view/system_view.py && grep -q "kept WORK/skills/tressoir-system-view" "$TMP/out.txt"'
install --override
check "--override refreshes the system view skill and leaves its data alone" \
  'diff -rq "$KIT/extras/tressoir-system-view" WORK/skills/tressoir-system-view >/dev/null && [ "$(cat WORK/SYSTEM_VIEW/system.json)" = "{ \"name\": \"Mine\" }" ] && grep -q "a remark" WORK/SYSTEM_VIEW/FEEDBACK.md'
if command -v python3 >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  cp "$KIT/extras/tressoir-system-view/seeds/system.json" WORK/SYSTEM_VIEW/system.json
  python3 WORK/skills/tressoir-system-view/system_view.py > "$TMP/out.txt" 2>&1
  check "the installed script builds the page from the starting files" '[ $? -eq 0 ] && [ -f WORK/SYSTEM_VIEW.html ] && grep -q "No boxes yet" WORK/SYSTEM_VIEW.html'
fi

printf '\nResult: %s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
