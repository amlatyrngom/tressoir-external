# Third-Party Notices

Tressoir Artifacts bundles or redistributes the following third-party software. This file records provenance for the local MVP package; distribution must also comply with each upstream license.

## morphdom

- Project: https://github.com/patrick-steele-idem/morphdom
- Version: 2.7.8
- License: MIT
- Use: bundled into the artifact webview for state-preserving DOM morphs.

## Prism

- Project: https://prismjs.com/
- Version: 1.29.0
- License: MIT
- Use: committed syntax-highlighting runtime in `src/notebook/assets/core/prism.js`.

## CodeMirror

- Project: https://codemirror.net/5/
- Version: 5.65.16
- License: MIT
- Use: committed editor runtime, modes, addons, and CSS under `src/notebook/assets/core/`.

## js-yaml

- Project: https://github.com/nodeca/js-yaml
- Version: 4.1.0
- License: MIT
- Use: committed YAML parser runtime in `src/notebook/assets/core/js-yaml.min.js`.

## unified / remark / rehype projection bundle

- Bundle: `src/notebook/assets/core/tressoir-remark.umd.js`
- Projects: https://unifiedjs.com/ and their linked package repositories
- Declared source packages:
  - `unified` 11.x
  - `remark-parse` 11.x
  - `remark-frontmatter` 5.x
  - `remark-directive` 3.x
  - `remark-gfm` 4.x
  - `remark-rehype` 11.x
  - `rehype-raw` 7.x
  - `rehype-stringify` 10.x
- License: MIT (verify exact locked transitive notices whenever the committed bundle is regenerated).
- Use: committed Markdown parsing and HTML projection runtime.

The extension source also uses VS Code API type declarations, esbuild, TypeScript, Vitest, jsdom, and `@vscode/vsce` as development-only dependencies. Their package metadata and licenses are recorded by `package-lock.json`; they are not shipped as runtime `node_modules`.
