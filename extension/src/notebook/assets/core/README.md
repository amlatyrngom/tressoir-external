# `.tressoir.md` core runtime (committed)

This directory retains the Markdown parser inputs and the previous Prism/CodeMirror payload for
source compatibility. New Markdown rendering loads `js-yaml.min.js` and
`tressoir-remark.umd.js` from here, then uses the exact tracked linear KaTeX/Prism/CodeMirror bundle
copied from the HTML starter into `dist/assets/linear/`.

They are committed build inputs. A normal extension build performs no download.

## Contents

- `prism.js`, `codemirror.js`, `codemirror.css`, `cm-mode/*.js`, `cm-addon/*.js` — retained previous
  renderer assets; not loaded by the new linear Markdown path.
- `js-yaml.min.js` — js-yaml 4.1.0 for directive/frontmatter data parsing.
- `tressoir-remark.umd.js` — a single classic IIFE exposing the unified/remark/rehype projection stack as `window.TressoirRemark`.

Standard presentation dependencies are automatic and offline. A `.tressoir.md` file may declare a
`links:` frontmatter list only for genuinely extra CSS/JavaScript. Local files load from the
artifact folder; remote CSS is referenced directly; remote JavaScript is cached locally by the
extension host. Only open trusted artifacts.

## Rebuilding the remark bundle

The committed js-yaml file originates from its upstream distribution. The remark/rehype packages
are ESM npm modules and are bundled into one browser IIFE. To regenerate it in a temporary directory:

```bash
mkdir -p /tmp/tressoir-remark-build
cd /tmp/tressoir-remark-build
cat > package.json <<'JSON'
{
  "name": "tressoir-remark-build",
  "private": true,
  "dependencies": {
    "unified": "^11.0.5",
    "remark-parse": "^11.0.0",
    "remark-frontmatter": "^5.0.0",
    "remark-directive": "^3.0.0",
    "remark-gfm": "^4.0.0",
    "remark-rehype": "^11.1.0",
    "rehype-raw": "^7.0.0",
    "rehype-stringify": "^10.0.0"
  }
}
JSON
npm install --no-audit --no-fund
cat > entry.mjs <<'JS'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkFrontmatter from 'remark-frontmatter'
import remarkDirective from 'remark-directive'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeRaw from 'rehype-raw'
import rehypeStringify from 'rehype-stringify'

window.TressoirRemark = {
  unified,
  remarkParse,
  remarkFrontmatter,
  remarkDirective,
  remarkGfm,
  remarkRehype,
  rehypeRaw,
  rehypeStringify,
}
JS
npx esbuild entry.mjs --bundle --format=iife --platform=browser --target=es2020 \
  --outfile="<repo>/extension/src/notebook/assets/core/tressoir-remark.umd.js"
```

Then run the extension typecheck, focused tests, clean package build, archive inspection, and isolated VS Code installation. Record exact refreshed versions and licenses in `THIRD_PARTY_NOTICES.md`.
