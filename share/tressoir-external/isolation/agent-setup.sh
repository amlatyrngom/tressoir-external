#!/usr/bin/env bash

set -euo pipefail

fail() {
  printf 'Tressoir isolation: %s\n' "$1" >&2
  exit 1
}

source_options=$(findmnt -no OPTIONS --target /source) ||
  fail "cannot inspect /source"

case ",$source_options," in
  *,ro,*) ;;
  *) fail "/source is not read-only" ;;
esac

[ -w /workspace/IB ] || fail "/workspace/IB is not writable"

sudo install -d \
  -o "$(id -un)" \
  -g "$(id -gn)" \
  /workspace

tar -C /source --exclude='./IB' -cf - . |
  tar -C /workspace -xf -

append_isolation_notice() {
  local file
  file="$1"

  if grep -Fq '<!-- TRESSOIR ISOLATION: BEGIN -->' "$file"; then
    return
  fi

  cat >> "$file" <<'EOF'

<!-- TRESSOIR ISOLATION: BEGIN -->
## Tressoir isolation

You are running in an agent container.

- `/source` is the user’s read-only source repository.
- `/workspace` is your container-local working copy.
- `/workspace/IB` is shared with the user.
- Changes outside `IB` do not reach the user.
<!-- TRESSOIR ISOLATION: END -->
EOF
}

if [ -f /workspace/AGENTS.md ]; then
  append_isolation_notice /workspace/AGENTS.md
fi

if [ -f /workspace/CLAUDE.md ]; then
  append_isolation_notice /workspace/CLAUDE.md
fi
