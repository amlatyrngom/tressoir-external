# Tressoir Artifacts for VS Code

This extension renders two trusted, text-backed artifact formats in regular desktop VS Code:

- `*.tressoir.md` — Markdown projected into an attention-aware view with cards, reveal rows, decision inputs, highlighted code/diffs, and folder-local interaction persistence.
- `*.tressoir.html` — raw HTML/CSS/JavaScript rendered directly for fully custom artifacts.

It is the artifact-editor portion of Tressoir, extracted into a self-contained extension. It does not connect to the Tressoir daemon and does not include editor automation, the plugin host, code-server management, a Python runtime, or an SDK backend.

First-party extension code is licensed under the MIT License. Bundled third-party components retain their own licenses; see `THIRD_PARTY_NOTICES.md`.

## Runtime requirements

The installed VSIX needs only a compatible regular desktop VS Code (`^1.85.0`). Node and npm are build/release dependencies, not separate end-user runtime requirements. Core Markdown projection assets ship inside the VSIX.

The standalone extension cannot be enabled at the same time as the older
`tressoir.bridge` extension because both own the same artifact editor view
types. Disable or uninstall the legacy bridge and reload VS Code before using
this extension. After any Tressoir Artifacts upgrade, reload the window (or
close and reopen affected artifact tabs) so retained webviews do not keep old
runtime JavaScript.

## Security: artifacts are executable, trusted content

Opening either artifact format is **not** equivalent to opening an inert Markdown preview.

- Authored inline and relative scripts can execute in the VS Code webview.
- Markdown permits raw HTML and scripts.
- A Markdown `links:` frontmatter list can load local CSS/JavaScript and remote CSS. Remote JavaScript is fetched by the extension host, cached in the artifact folder's `vendor/` directory, and then loaded locally.
- Authored code can use the deliberately narrow `window.tressoirNotebook` helper to open a contained sibling file and read/write contained interaction JSON.

Only open artifacts from authors and workspaces you trust. This MVP does not provide a sanitized or script-free preview mode.

## Artifact API

Authored scripts can call:

```js
await window.tressoirNotebook?.openFile?.('./sibling.md')
await window.tressoirNotebook?.storeInteraction?.('choice', 'A')
const value = await window.tressoirNotebook?.getInteraction?.('choice')
```

`openFile` rejects absolute paths and `..` traversal. Interaction writes are constrained to `interactions.json` or `interactions.<suffix>.json` in the artifact folder, with bounded keys and serialized file size.

## Build and package

```bash
npm ci
npm run typecheck
npm test
npm run package:vsix
```

The versioned package is written to `dist/tressoir-artifacts-0.1.2.vsix`. Always inspect the newly produced archive and packaged manifest before release; do not reuse an older bridge VSIX.

## Source provenance

The initial artifact stack was extracted from the Tressoir bridge's `src/notebook/**` implementation. See `THIRD_PARTY_NOTICES.md` and `src/notebook/assets/core/README.md` for bundled runtime provenance.
