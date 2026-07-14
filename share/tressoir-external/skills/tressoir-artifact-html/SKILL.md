---
name: tressoir-artifact-html
description: Author or revise a raw .tressoir.html artifact with custom HTML, CSS, JavaScript, contained interactions, local resources, and live morph behavior.
---

# Tressoir HTML Artifacts

Use `.tressoir.html` when you know the exact interface you need and the structured `.tressoir.md` projection is not flexible enough.

The Tressoir Artifacts VS Code extension renders the file directly in a webview. Your HTML, CSS, and JavaScript are the page. There is no required template or enforced information architecture.

Prefer `.tressoir.md` for plans, research, standard decisions, reveal rows, and focused review surfaces.

## Folder placement

Put the artifact in the existing sticky broad-task folder under `IB/ARTIFACTS/`. Reuse that folder for related plans, subplans, explainers, interactive surfaces, sibling assets, data, and interaction files. A later HTML explainer does not need a new folder. Create a new upper-case folder only for a genuinely separate workstream or when the user requests one.

## Trusted executable content

Opening `.tressoir.html` runs authored scripts in the artifact webview. Only open artifacts from trusted authors and workspaces. This is not a safe preview for arbitrary downloaded HTML.

The webview hides the raw VS Code API and exposes a narrow helper, but authored code remains powerful within the rendered artifact and may load resources allowed by the content security policy.

## Contained helper API

Authored scripts can use:

```js
await window.tressoirNotebook?.openFile?.('./sibling.md')
await window.tressoirNotebook?.storeInteraction?.('choice', { option: 'A' })
const saved = await window.tressoirNotebook?.getInteraction?.('choice')
```

- `openFile(relativePath)` opens a sibling inside the artifact folder. Absolute paths and `..` traversal are rejected.
- `storeInteraction(key, value, filename?)` persists a JSON-serializable value.
- `getInteraction(key, filename?)` reads it back.
- The default filename is `interactions.json`.
- Alternate filenames must match `interactions.<suffix>.json`.
- Keys and serialized files are bounded by the extension.

Guard helper calls if the HTML might also be opened in a normal browser.

## Live morph behavior

External edits update the view by morphing the DOM rather than recreating the entire realm. Scroll, focused controls, open disclosures, and suitable runtime state can survive.

Use:

```html
<div data-morph-keep-class="open selected"></div>
<div data-morph-skip><!-- runtime-owned subtree --></div>
```

Listen for `tressoir:render` to reapply idempotent upgrades after both initial render and later morphs:

```js
window.addEventListener('tressoir:render', async () => {
  // Restore persisted selections or re-run safe visual enhancement.
})
```

A one-time script does not necessarily rerun after every morph.

## Styling and resources

- Inline `<style>` works.
- Relative stylesheets, scripts, images, and data files resolve from the artifact folder.
- Remote stylesheets are permitted.
- Inline scripts work because the extension applies its nonce.
- Relative local scripts work.
- Direct remote `<script src="https://…">` is blocked; vendor JavaScript into a sibling `vendor/` directory and reference it relatively.
- `eval` and `new Function` are not allowed.
- Theme variables such as `--nb-bg`, `--nb-surface`, `--nb-text`, and `--nb-accent` follow the editor theme.

Keep third-party assets inspectable and record their provenance. Decide explicitly whether a project should commit or ignore `vendor/`.

## Human-facing quality

Even though the format is unconstrained:

- lead with the user's goal and current decision;
- use plain labels and expand uncommon acronyms;
- keep important state visible;
- reveal depth progressively;
- make controls keyboard-accessible;
- respect light and dark themes;
- avoid ornamental interaction that obscures the work.

## Verification

Open the artifact in the custom editor and exercise:

1. initial rendering;
2. light/dark theme changes;
3. external source edits and morph preservation;
4. each interaction read/write;
5. sibling opening and traversal rejection;
6. local resources and offline behavior;
7. any third-party library under the actual webview content security policy.
