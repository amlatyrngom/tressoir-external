#!/usr/bin/env bash

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
EXTENSION="$ROOT/extension"
PAYLOAD="$ROOT/share/tressoir-external"
VERSION="0.1.1"
VSIX="$EXTENSION/dist/tressoir-artifacts-$VERSION.vsix"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/tressoir-release-check.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

cd "$EXTENSION"
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck
npm test
npm run package:vsix

unzip -Z1 "$VSIX" > "$TMP/archive.txt"
unzip -p "$VSIX" extension/package.json > "$TMP/package.json"
unzip -p "$VSIX" extension/LICENSE.md > "$TMP/LICENSE.md"

cmp "$ROOT/LICENSE" "$EXTENSION/LICENSE.md"
grep -Fx 'MIT License' "$ROOT/LICENSE" >/dev/null
grep -Fx 'MIT License' "$TMP/LICENSE.md" >/dev/null

node - "$TMP/package.json" <<'NODE'
const fs = require('fs')
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const identity = `${manifest.publisher}.${manifest.name}@${manifest.version}`
if (identity !== 'tressoir.tressoir-artifacts@0.1.1') {
  throw new Error(`unexpected packaged identity: ${identity}`)
}
if (manifest.license !== 'MIT') {
  throw new Error(`unexpected packaged license: ${manifest.license}`)
}
const editors = manifest.contributes?.customEditors ?? []
const byType = new Map(editors.map((editor) => [editor.viewType, editor]))
for (const [viewType, pattern] of [
  ['tressoir.notebookHtml', '*.tressoir.html'],
  ['tressoir.notebookMd', '*.tressoir.md'],
]) {
  const editor = byType.get(viewType)
  if (!editor) throw new Error(`missing custom editor: ${viewType}`)
  const patterns = (editor.selector ?? []).map((selector) => selector.filenamePattern)
  if (!patterns.includes(pattern)) throw new Error(`missing selector: ${pattern}`)
}
NODE

for required in \
  extension/LICENSE.md \
  extension/THIRD_PARTY_NOTICES.md \
  extension/dist/extension.js \
  extension/dist/notebook-webview.js \
  extension/dist/notebook-webview.css \
  extension/dist/assets/artifact.css \
  extension/dist/assets/tressoir-md.js \
  extension/dist/assets/core/js-yaml.min.js \
  extension/dist/assets/core/tressoir-remark.umd.js; do
  grep -Fx "$required" "$TMP/archive.txt" >/dev/null || {
    echo "missing VSIX member: $required" >&2
    exit 1
  }
done

if grep -E '(^|/)(src|node_modules|__tests__)/|\.map$|\.vsix$' "$TMP/archive.txt"; then
  echo "VSIX contains development or nested package content" >&2
  exit 1
fi

if find "$PAYLOAD" -type f -name '*.vsix' -print -quit | grep .; then
  echo "payload contains a generated VSIX; public source builds must remain untracked" >&2
  exit 1
fi

cd "$ROOT"
for skill in "$PAYLOAD"/skills/*; do
  npx --yes skills-ref@0.1.5 validate "$skill"
done

cd "$PAYLOAD"
find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort | while IFS= read -r file; do
  rel=${file#./}
  if command -v shasum >/dev/null 2>&1; then
    digest=$(shasum -a 256 "$file" | awk '{print $1}')
  else
    digest=$(sha256sum "$file" | awk '{print $1}')
  fi
  printf '%s  %s\n' "$digest" "$rel"
done > SHA256SUMS

cd "$ROOT"
bash -n bin/tressoir-external
bash -n install.sh
bash -n tests/helpers/dummy_repo/make_dummy_repo.sh
node --check "$PAYLOAD/skills/tressoir-artifact-md/scripts/check_md.js"
node "$PAYLOAD/skills/tressoir-artifact-md/scripts/check_md.js" \
  "$PAYLOAD/skills/tressoir-artifact-md/user_artifact_md_template/PLAN.tressoir.md" \
  "$PAYLOAD/skills/tressoir-artifact-md/user_artifact_md_template/INTERACTIVE.tressoir.md"
tests/test_setup.sh
tests/test_install.sh

echo "Release checks passed: $VSIX"
