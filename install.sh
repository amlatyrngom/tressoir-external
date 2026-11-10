#!/usr/bin/env bash

# Installs the Tressoir starter kit into a project. It asks nothing.
#
#   From a checkout:   /path/to/tressoir-external/install.sh [--override]
#   Without one:       curl -fsSL <raw address of this file> | bash -s -- [--override]
#
# The project is the current directory, or TRESSOIR_ROOT when set.
#
# It always sets up Claude and the shared agents convention together:
#   WORK/WORK_AREA_GUIDE.md and WORK/skills/tressoir-*     owned by the kit
#   WORK/STATE.md, TASK.md, MEMORY/, ARTIFACTS/, TMP/      created once, then never touched
#   .claude/skills/ and .agents/skills/                    a link for each skill
#   AGENTS.md (three-line pointer) and CLAUDE.md (@AGENTS.md)
#
# --override refreshes what the kit owns: the guide, the kit's skills and their scripts. It never
# touches STATE.md, TASK.md, anything in MEMORY/ or ARTIFACTS/, or skills the kit did not ship.

set -euo pipefail

REPOSITORY="amlatyrngom/tressoir-external"
ARCHIVE_URL="${TRESSOIR_ARCHIVE_URL:-https://codeload.github.com/$REPOSITORY/tar.gz/refs/heads/main}"
CORE_SKILLS="tressoir-memory tressoir-plan tressoir-present tressoir-migrate"
EXTRA_SKILLS="tressoir-structured-review tressoir-isolation"
# Skills of the first kit. --override removes them; they stay in the project's git history.
RETIRED_SKILLS="tressoir-working-area tressoir-canon tressoir-artifact-md tressoir-artifact-html"
OVERRIDE=0
TEMP=""
CHANGED=0

say() { printf '%s\n' "$*"; }
did() { CHANGED=$((CHANGED + 1)); printf '  %s\n' "$*"; }
fatal() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }
cleanup() { if [ -n "$TEMP" ]; then rm -rf "$TEMP"; fi; }
trap cleanup EXIT

for arg in "$@"; do
  case "$arg" in
    --override) OVERRIDE=1 ;;
    -h|--help) sed -n '3,17p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fatal "unknown option: $arg (the only option is --override)" ;;
  esac
done

ROOT="${TRESSOIR_ROOT:-$PWD}"
[ -d "$ROOT" ] || fatal "the project folder does not exist: $ROOT"
ROOT=$(cd "$ROOT" && pwd -P)

# The kit: the checkout this script sits in, or a download when it is piped in.
KIT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
  if [ -f "$HERE/guide/WORK_AREA_GUIDE.md" ] && [ -d "$HERE/skills" ]; then KIT="$HERE"; fi
fi
if [ -z "$KIT" ]; then
  for tool in curl tar; do
    command -v "$tool" >/dev/null 2>&1 || fatal "$tool is needed to download the kit"
  done
  TEMP=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-kit.XXXXXX")
  curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$TEMP" || fatal "could not download $ARCHIVE_URL"
  KIT=$(find "$TEMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  [ -f "$KIT/guide/WORK_AREA_GUIDE.md" ] || fatal "the download does not look like the kit"
fi
[ "$KIT" != "$ROOT" ] || fatal "run this from the project to set up, not from the kit itself"

if [ ! -e "$ROOT/WORK" ] && [ -d "$ROOT/IB" ]; then
  fatal "this project still has the first kit's IB/ folder. Migrate it first: follow $KIT/skills/tressoir-migrate/SKILL.md"
fi

say "Tressoir starter kit -> $ROOT"
cd "$ROOT"

# Created once. A file or folder that already exists is the project's and is left alone.
seed() {  # seed <kit file> <project path>
  if [ ! -e "$2" ] && [ ! -L "$2" ]; then
    mkdir -p "$(dirname "$2")"; cp "$KIT/$1" "$2"; did "created $2"
  fi
}
mkdir -p WORK/skills WORK/ARTIFACTS WORK/TMP
seed seeds/STATE.md WORK/STATE.md
seed seeds/TASK.md WORK/TASK.md
seed seeds/WORK.gitignore WORK/.gitignore
if [ ! -e WORK/MEMORY ]; then
  seed seeds/ROOT_MEMORY.md WORK/MEMORY/ROOT_MEMORY.md
  seed seeds/EXAMPLES_README.md WORK/MEMORY/EXAMPLES/README.md
fi

# Owned by the kit: installed when missing, refreshed only with --override.
same() { diff -rq "$1" "$2" >/dev/null 2>&1; }
own() {  # own <kit path> <project path>, for a file or a folder
  if [ ! -e "$2" ]; then
    cp -R "$KIT/$1" "$2"; did "installed $2"
  elif same "$KIT/$1" "$2"; then
    :
  elif [ "$OVERRIDE" -eq 1 ]; then
    rm -rf "$2.incoming"; cp -R "$KIT/$1" "$2.incoming"; rm -rf "$2"; mv "$2.incoming" "$2"; did "refreshed $2"
  else
    say "  kept $2 (it differs from the kit; --override refreshes it)"
  fi
}
own guide/WORK_AREA_GUIDE.md WORK/WORK_AREA_GUIDE.md
for skill in $CORE_SKILLS; do own "skills/$skill" "WORK/skills/$skill"; done
# Optional extras are refreshed where a project already has them, never added.
for skill in $EXTRA_SKILLS; do
  if [ -d "WORK/skills/$skill" ]; then own "extras/$skill" "WORK/skills/$skill"; fi
done

# What the first kit left behind. Part of migrating; delete this block with tressoir-migrate.
if [ "$OVERRIDE" -eq 1 ]; then
  for skill in $RETIRED_SKILLS; do
    if [ -d "WORK/skills/$skill" ]; then rm -rf "WORK/skills/$skill"; did "removed retired skill WORK/skills/$skill"; fi
    for links in .claude/skills .agents/skills; do
      if [ -L "$links/$skill" ]; then rm "$links/$skill"; did "removed link $links/$skill"; fi
    done
  done
  OLD_POINTER='# Tressoir Guidance

Before substantial work, read and follow `IB/TRESSOIR.md`.
Read current status and open decisions in `IB/STATE.md`.
Read durable project decisions in `IB/CANON/ROOT_CANON.md`.'
  for file in AGENTS.md CLAUDE.md; do
    if [ -f "$file" ] && [ ! -L "$file" ]; then
      text=$(cat "$file")
      case "$text" in *"$OLD_POINTER"*)
        text=${text/"$OLD_POINTER"/}
        printf '%s\n' "$text" | sed -e '/./,$!d' > "$file.incoming"; mv "$file.incoming" "$file"
        did "removed the first kit's pointer from $file" ;;
      esac
    fi
  done
fi

# A link for every skill in WORK/skills/, in both places harnesses look.
for links in .claude/skills .agents/skills; do
  mkdir -p "$links"
  for folder in WORK/skills/*/; do
    [ -f "${folder}SKILL.md" ] || continue
    name=$(basename "$folder"); target="../../WORK/skills/$name"
    if [ -L "$links/$name" ]; then
      [ "$(readlink "$links/$name")" = "$target" ] && continue
      case " $CORE_SKILLS $EXTRA_SKILLS " in
        *" $name "*) rm "$links/$name"; ln -s "$target" "$links/$name"; did "re-pointed $links/$name" ;;
        *) say "  kept $links/$name (it points to $(readlink "$links/$name"))" ;;
      esac
    elif [ -e "$links/$name" ]; then
      say "  kept $links/$name (not a link)"
    else
      ln -s "$target" "$links/$name"; did "linked $links/$name"
    fi
  done
done

# Root guidance: add the pointer, leave everything else in the file.
if [ ! -e AGENTS.md ] || [ ! -s AGENTS.md ]; then
  cp "$KIT/seeds/AGENTS.md" AGENTS.md; did "created AGENTS.md"
elif ! grep -qF 'WORK/WORK_AREA_GUIDE.md' AGENTS.md; then
  { printf '\n'; cat "$KIT/seeds/AGENTS.md"; } >> AGENTS.md; did "added the pointer to AGENTS.md"
fi
if [ -L CLAUDE.md ]; then
  say "  kept CLAUDE.md (it is a link)"
elif [ ! -e CLAUDE.md ] || [ ! -s CLAUDE.md ]; then
  printf '@AGENTS.md\n' > CLAUDE.md; did "created CLAUDE.md"
elif ! grep -qxF '@AGENTS.md' CLAUDE.md; then
  printf '\n@AGENTS.md\n' >> CLAUDE.md; did "added @AGENTS.md to CLAUDE.md"
fi

# The files are the only memory, so Claude's private memory is switched off.
if [ ! -e .claude/settings.json ]; then
  printf '{\n  "autoMemoryEnabled": false\n}\n' > .claude/settings.json; did "created .claude/settings.json"
elif ! grep -q '"autoMemoryEnabled"' .claude/settings.json; then
  say "  note: add \"autoMemoryEnabled\": false to .claude/settings.json to keep Claude's private memory off"
fi

if [ "$CHANGED" -eq 0 ]; then say "  nothing to do"; fi
say "Done. Agents start from AGENTS.md; the guide is WORK/WORK_AREA_GUIDE.md."
