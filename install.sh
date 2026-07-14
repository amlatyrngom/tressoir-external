#!/usr/bin/env bash

# Interactive source bootstrap for Tressoir External.
# Designed for: curl -fsSL <raw-url> | bash
# Prompts use /dev/tty because standard input contains this script.

set -euo pipefail

REPOSITORY="amlatyrngom/tressoir-external"
REF="main"
ARCHIVE_URL_DEFAULT="https://codeload.github.com/$REPOSITORY/tar.gz/refs/heads/$REF"
ARCHIVE_URL="${TRESSOIR_EXTERNAL_ARCHIVE_URL:-$ARCHIVE_URL_DEFAULT}"
TARGET_INPUT="${TRESSOIR_EXTERNAL_ROOT:-$PWD}"
VSCODE_BIN="${TRESSOIR_EXTERNAL_VSCODE_BIN:-code}"
EXTENSION_VERSION="0.1.1"
TEMP_ROOT=""
PROMPT_FD_OPEN=0
CHOICE_RESULT=0

say() {
  printf '%s\n' "$*"
}

fatal() {
  printf 'fatal: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [ -n "$TEMP_ROOT" ] && [ -d "$TEMP_ROOT" ]; then
    rm -rf "$TEMP_ROOT"
  fi
}
trap cleanup EXIT HUP INT TERM

choice_from_value() {
  case "$1" in
    1|y|Y|yes|YES|Yes|true|TRUE|True)
      CHOICE_RESULT=1
      return 0
      ;;
    0|n|N|no|NO|No|false|FALSE|False)
      CHOICE_RESULT=0
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

open_prompt_tty() {
  if [ "$PROMPT_FD_OPEN" -eq 1 ]; then
    return
  fi
  if ! exec 3<> /dev/tty; then
    fatal "interactive choices need a controlling terminal; run this command in a terminal or export TRESSOIR_EXTERNAL_VSCODE, TRESSOIR_EXTERNAL_CLAUDE, TRESSOIR_EXTERNAL_CODEX, and TRESSOIR_EXTERNAL_PI as yes/no"
  fi
  PROMPT_FD_OPEN=1
}

choose() {
  local label default supplied answer suffix
  label="$1"
  default="$2"
  supplied="$3"

  if [ -n "$supplied" ]; then
    choice_from_value "$supplied" ||
      fatal "invalid yes/no choice '$supplied' for $label"
    return
  fi

  open_prompt_tty
  if [ "$default" -eq 1 ]; then
    suffix="[Y/n]"
  else
    suffix="[y/N]"
  fi

  while :; do
    printf '%s %s ' "$label" "$suffix" >&3
    IFS= read -r answer <&3 || fatal "could not read an interactive choice"
    case "$answer" in
      "")
        CHOICE_RESULT="$default"
        return
        ;;
      *)
        if choice_from_value "$answer"; then
          return
        fi
        printf '%s\n' "Please answer yes or no." >&3
        ;;
    esac
  done
}

command_required() {
  command -v "$1" >/dev/null 2>&1 ||
    fatal "required command not found: $1"
}

say "Tressoir External"
say "  target project: $TARGET_INPUT"
say ""

choose "Install the Tressoir Artifacts VS Code extension?" 1 \
  "${TRESSOIR_EXTERNAL_VSCODE:-}"
INSTALL_VSCODE="$CHOICE_RESULT"
choose "Register skills for Claude Code?" 0 \
  "${TRESSOIR_EXTERNAL_CLAUDE:-}"
INSTALL_CLAUDE="$CHOICE_RESULT"
choose "Register skills for OpenAI Codex CLI?" 0 \
  "${TRESSOIR_EXTERNAL_CODEX:-}"
INSTALL_CODEX="$CHOICE_RESULT"
choose "Register skills for the TypeScript Pi coding agent?" 0 \
  "${TRESSOIR_EXTERNAL_PI:-}"
INSTALL_PI="$CHOICE_RESULT"

if [ "$INSTALL_VSCODE" -eq 0 ] &&
   [ "$INSTALL_CLAUDE" -eq 0 ] &&
   [ "$INSTALL_CODEX" -eq 0 ] &&
   [ "$INSTALL_PI" -eq 0 ]; then
  say ""
  say "Nothing selected; no files were changed."
  exit 0
fi

[ -d "$TARGET_INPUT" ] || fatal "target project is not a directory: $TARGET_INPUT"
TARGET_ROOT=$(CDPATH= cd -- "$TARGET_INPUT" 2>/dev/null && pwd -P) ||
  fatal "cannot resolve target project: $TARGET_INPUT"

case "$(uname -s 2>/dev/null || true)" in
  Darwin|Linux) ;;
  *) fatal "this release supports macOS and mainstream Linux only" ;;
esac

command_required curl
command_required tar
command_required mktemp

if [ "$INSTALL_VSCODE" -eq 1 ]; then
  command_required node
  command_required npm
  NODE_MAJOR=$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null) ||
    fatal "could not determine the Node.js version"
  case "$NODE_MAJOR" in
    ""|*[!0-9]*) fatal "could not determine the Node.js major version" ;;
  esac
  [ "$NODE_MAJOR" -ge 22 ] ||
    fatal "building the VS Code extension requires Node.js 22 or newer"
  command -v "$VSCODE_BIN" >/dev/null 2>&1 ||
    fatal "VS Code CLI '$VSCODE_BIN' was not found; set TRESSOIR_EXTERNAL_VSCODE_BIN or choose no"
fi

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-external-install.XXXXXX") ||
  fatal "could not create a temporary directory"
ARCHIVE="$TEMP_ROOT/source.tar.gz"
EXTRACTED="$TEMP_ROOT/source"
mkdir "$EXTRACTED"

say ""
say "Downloading public source into temporary storage..."
curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE" ||
  fatal "could not download $ARCHIVE_URL"
tar -xzf "$ARCHIVE" -C "$EXTRACTED" ||
  fatal "could not extract the downloaded source"

SOURCE_ROOT=""
for candidate in "$EXTRACTED"/*; do
  [ -d "$candidate" ] || continue
  [ -z "$SOURCE_ROOT" ] ||
    fatal "downloaded archive contains more than one top-level directory"
  SOURCE_ROOT="$candidate"
done
[ -n "$SOURCE_ROOT" ] ||
  fatal "downloaded archive does not contain a source directory"
[ -x "$SOURCE_ROOT/bin/tressoir-external" ] ||
  fatal "downloaded source is missing bin/tressoir-external"

VSIX_PATH=""
if [ "$INSTALL_VSCODE" -eq 1 ]; then
  [ -f "$SOURCE_ROOT/extension/package-lock.json" ] ||
    fatal "downloaded source is missing the extension lockfile"
  say "Building the VS Code extension in temporary storage..."
  (
    cd "$SOURCE_ROOT/extension"
    npm ci --ignore-scripts --no-audit --no-fund
    npm run package:vsix
  )
  VSIX_PATH="$SOURCE_ROOT/extension/dist/tressoir-artifacts-$EXTENSION_VERSION.vsix"
  [ -f "$VSIX_PATH" ] ||
    fatal "extension build did not produce $(basename -- "$VSIX_PATH")"
fi

SETUP_ARGS=(setup --root "$TARGET_ROOT")
if [ "$INSTALL_CLAUDE" -eq 1 ]; then
  SETUP_ARGS+=(--claude)
fi
if [ "$INSTALL_CODEX" -eq 1 ]; then
  SETUP_ARGS+=(--codex)
fi
if [ "$INSTALL_PI" -eq 1 ]; then
  SETUP_ARGS+=(--pi)
fi
if [ "$INSTALL_VSCODE" -eq 1 ]; then
  SETUP_ARGS+=(--vsix "$VSIX_PATH" --vscode-bin "$VSCODE_BIN")
else
  SETUP_ARGS+=(--no-vscode)
fi

say ""
set +e
"$SOURCE_ROOT/bin/tressoir-external" "${SETUP_ARGS[@]}"
SETUP_STATUS=$?
set -e

case "$SETUP_STATUS" in
  0)
    say ""
    say "Temporary source and build files will now be removed."
    ;;
  2)
    say ""
    say "Temporary source and build files will now be removed."
    say "Review the preserved collisions or manual adapter work reported above."
    ;;
  *)
    fatal "project setup failed"
    ;;
esac

exit "$SETUP_STATUS"
