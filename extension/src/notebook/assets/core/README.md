# `.tressoir.md` core runtime (committed)

These files are the always-needed runtime for the `*.tressoir.md` projection. They ship inside the standalone Tressoir Artifacts extension under `dist/assets/core/` and are loaded through VS Code webview URIs.

They are committed build inputs. A normal extension build performs no download.

## Contents

- `prism.js` — Prism 1.29.0 core and language grammars for read-only highlighting.
- `codemirror.js`, `codemirror.css`, `cm-mode/*.js`, `cm-addon/*.js` — CodeMirror 5.65.16 for the free-form feedback editor.
- `js-yaml.min.js` — js-yaml 4.1.0 for directive/frontmatter data parsing.
- `tressoir-remark.umd.js` — a single classic IIFE exposing the unified/remark/rehype projection stack as `window.TressoirRemark`.

Per-artifact dependencies are separate. A `.tressoir.md` file may declare a `links:` frontmatter list. Local CSS/JavaScript is loaded from the artifact folder; remote CSS is referenced directly; remote JavaScript is fetched by the extension host into the artifact-local `vendor/` cache and loaded locally. Only open trusted artifacts.

## Rebuilding the remark bundle

The committed Prism, CodeMirror, and js-yaml files originate from their upstream distributions. The remark/rehype packages are ESM npm modules and are bundled into one browser IIFE. To regenerate it in a temporary directory:

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
