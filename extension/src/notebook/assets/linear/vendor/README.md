# Vendored runtime assets

These files are copied from the official npm distributions and run locally at artifact time.

- `katex/`: KaTeX 0.18.4 (`katex`, MIT). Includes `katex.min.js`, `katex.min.css`, auto-render,
  the complete distribution font set, and `LICENSE`.
- `prism/`: PrismJS 1.30.0 (`prismjs`, MIT). Includes core, the deliberately selected language
  components, Diff Highlight JavaScript/CSS, and `LICENSE`.
- `codemirror/`: CodeMirror 5.65.16 (`codemirror`, MIT). Includes core JavaScript/CSS, XML/meta/
  Markdown modes for the feedback editor, and `LICENSE`.

To update a dependency, replace the complete selected asset set, update both version records, and
re-run the starter's offline, syntax, math, diff, and browser/Tressoir validation gates.
