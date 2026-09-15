# Tressoir Artifacts for VS Code

This extension renders two trusted, text-backed artifact formats in regular desktop VS Code:

- `*.tressoir.md` — Markdown projected into an attention-aware view with cards, reveal rows, decision inputs, highlighted code/diffs, and folder-local interaction persistence.
- `*.tressoir.html` — raw HTML/CSS/JavaScript rendered directly for fully custom artifacts.
- ordinary `*.html` — available as **Reopen With → Tressoir Artifact Preview (HTML)** without taking over normal text editing.

It is the artifact-editor portion of Tressoir, extracted into a self-contained extension. It does not connect to the Tressoir daemon and does not include editor automation, the plugin host, code-server management, a Python runtime, or an SDK backend.

## Notable in this release (0.1.8)

- Live updates preserve a visible keyed element's viewport offset, with scroll coordinates as
  a fallback, in the page and scrollable panels. Stable `id` or `data-morph-key` values help
  when a report replaces elements. Sticky/fixed controls are excluded as reading anchors.
- A 1.2-second observation window repairs transient content shrinkage and late layout changes.
  Wheel, touch, pointer, or keyboard input cancels corrections immediately; newer updates also
  invalidate older corrections and render completions. This is not a persistent scroll lock.
- Reports should update atomically, keep stable identities, and avoid resetting scroll/focus in
  render hooks. Unkeyed panels that are replaced, layout work after the observation window, and
  removal of the actual reading target remain best-effort cases.

## Earlier changes

- The installed HTML skill and its starter are now genuinely compact: the template uses pinned
  HTTPS resources by default and no longer ships a duplicate `vendor/` tree or standard CSS/JS.
- Canonical offline runtime assets now live only in the extension source and packaged VSIX, where
  the Markdown renderer still requires them.

- Trusted HTML artifacts can load direct HTTPS scripts as well as HTTPS stylesheets, enabling
  compact single-file artifacts backed by pinned CDN or immutable-commit resources.
- Failed external scripts now produce a visible resource error instead of silently leaving
  runtime-built sections blank.

- Markdown and HTML now share the accepted linear light/dark theme, card and single-decision
  components, floating feedback form, local math and syntax highlighting, and contained overflow.
- This version bump deliberately distinguishes that runtime from the earlier `0.1.4` package;
  reusing the old version number allowed VS Code setup to mistake changed bytes for an installed build.
- Ordinary HTML can opt into the same trusted preview while the normal text editor remains the default.
- Raw HTML no longer sits inside an extension-owned padded rounded sheet or inherits a serif host font; authored pages render full-bleed with a restrained system fallback.
- Inert script data blocks such as `type="application/json"` remain untouched while following executable renderers run with the webview nonce, covering full-document data-plus-renderer artifacts such as generated briefings.
- Markdown level-one headings now keep normal section spacing before a following card; the compact
  frontmatter title remains unchanged.
- Markdown decision inputs keep a stable identity across live edits: an answer stays bound to its `:::input{key=...}` even when surrounding cards are reordered, inserted, removed, or renamed, so typed values no longer shift to the wrong row during re-projection.
- The Markdown projection view emits advisory authoring warnings (over-long titles/questions, duplicate input keys, lifecycle sections missing their Planned Changes / Completion Report, and stray fenced code) without blocking rendering.
- After any upgrade, reload the window (or reopen affected artifact tabs) so retained webviews pick up the new runtime JavaScript.

First-party extension code is licensed under the MIT License. Bundled third-party components retain their own licenses; see `THIRD_PARTY_NOTICES.md`.

## Runtime requirements

The installed VSIX needs only a compatible regular desktop VS Code (`^1.85.0`). Node and npm are build/release dependencies, not separate end-user runtime requirements. Core Markdown projection assets ship inside the VSIX.

## Live typography settings

Font sizes can be tuned per user, workspace, or resource without rebuilding the extension:

```json
{
  "tressoir.markdown.baseFontSize": 14,
  "tressoir.html.baseFontSize": 16
}
```

Open artifact views update when either setting changes. Markdown's standard heading hierarchy
scales from its base. HTML changes the document root size, so `rem`/`em` typography—including
headings—scales while explicit authored pixel sizes remain fixed.

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
- Authored code can use the deliberately narrow `window.tressoirNotebook` helper to open a relative file contained by the artifact folder or an open workspace, and to read/write contained interaction JSON.

Only open artifacts from authors and workspaces you trust. This MVP does not provide a sanitized or script-free preview mode.

## Artifact API

Authored scripts can call:

```js
await window.tressoirNotebook?.openFile?.('./sibling.md')
await window.tressoirNotebook?.storeInteraction?.('choice', 'A')
const value = await window.tressoirNotebook?.getInteraction?.('choice')
```

`openFile` rejects absolute paths. Parent-relative paths are accepted only when the resolved file
remains inside the artifact folder or an open workspace. Interaction writes are constrained to
`interactions.json`, `interactions.<suffix>.json`, or the generated
`<artifact-basename>.interactions.json` in the artifact folder, with bounded keys and serialized
file size.

Rendered Markdown local links and images open through the same contained `openFile` bridge. Add
`interactions: scoped` to Markdown frontmatter to store new widget values in
`<artifact-basename>.interactions.json`; the default remains the shared `interactions.json`, and
scoped artifacts fall back to legacy shared values until those values are edited.

A card declared with `copy_button=true` includes a **Copy Markdown** control that copies that
card's original Markdown, including its declaration and nested directives, for a lossless handoff.
Cards without the attribute and ordinary `##` sections have no copy control. Set `feedback:
disabled` in Markdown frontmatter when the artifact should omit the automatic top-level feedback
editor.

## Build and package

```bash
npm ci
npm run typecheck
npm test
npm run package:vsix
```

The versioned package is written to `dist/tressoir-artifacts-0.1.8.vsix`. Always inspect the newly produced archive and packaged manifest before release; do not reuse an older bridge VSIX.

Install only the extension (without running project/skill setup):

```bash
code --install-extension dist/tressoir-artifacts-0.1.8.vsix --force
```

Then run **Developer: Reload Window** in VS Code. For SSH/containers, install the VSIX in the
extension host where the report is opened, using **Extensions: Install from VSIX…** if needed.

The real-browser scroll regression gate uses the built webview bundle:

```bash
node ../scripts/test_scroll_browser.mjs
```

It defaults to macOS Chrome; set `CHROME_BIN` to another Chromium executable as needed.

## Source provenance

The initial artifact stack was extracted from the Tressoir bridge's `src/notebook/**` implementation. See `THIRD_PARTY_NOTICES.md` and `src/notebook/assets/core/README.md` for bundled runtime provenance.
