import * as vscode from 'vscode'
import * as fs from 'fs'
import * as http from 'http'
import * as https from 'https'
import * as crypto from 'crypto'
import * as path from 'path'
import {
  clearNotebookStateForPath,
  setActiveNotebookDocument,
  setNotebookSelection,
} from './state'
import {
  notebookThemeFromColorKind,
  type NotebookThemeState,
} from './theme'

// Map of `<filename>` -> parsed interactions object. Authored content reads this snapshot via
// `window.tressoirNotebook.getInteraction(key, filename)` and persists via `storeInteraction`.
type InteractionsSnapshot = Record<string, Record<string, unknown>>

type NotebookStateMessage = {
  type: 'state'
  sourceHtml: string
  sourceKind: NotebookSourceKind
  theme: NotebookThemeState
  interactions: InteractionsSnapshot
  baseFontSize: number
}

// Sent on an authored-content change while the webview realm is alive. The webview DOM-morphs
// the live preview to match `sourceHtml` (a "lightweight refresh") instead of the provider
// tearing down and rebuilding `webview.html`, so the reader's active tab, open disclosures,
// scroll, focus, and any runtime-upgraded widgets (the CodeMirror field) survive the update.
type NotebookUpdateMessage = {
  type: 'update'
  sourceHtml: string
  sourceKind: NotebookSourceKind
  interactions: InteractionsSnapshot
  baseFontSize: number
}

type NotebookTypographyMessage = {
  type: 'typography'
  sourceKind: NotebookSourceKind
  baseFontSize: number
}

type NotebookThemeMessage = {
  type: 'theme'
  theme: NotebookThemeState
}

type NotebookInboundMessage =
  | { type: 'ready' }
  | {
      type: 'selectionChanged'
      // cellId is legacy (the editor-agnostic webview has no Monaco cells); kept optional for
      // backwards-compatible message shape. The selection is the rendered-text selection.
      cellId?: string
      selectedText: string
    }
  | { type: 'openRawText' }
  | {
      // Narrow navigation: open a relative file contained by the artifact folder or workspace.
      type: 'openArtifactFile'
      path: string
    }
  | {
      // Persist an authored-content interaction (e.g. a CodeMirror feedback field, a decision
      // pick) to a contained JSON file in the artifact folder. The ONLY authored disk-write
      // capability; strictly validated (contained interaction basename, JSON-only, size-capped).
      type: 'storeInteraction'
      key: string
      value: unknown
      filename?: string
    }

const BUNDLED_HTML_ASSETS = new Map<string, string>([
  ['https://cdn.jsdelivr.net/npm/katex@0.18.4/dist/katex.min.css', 'linear/vendor/katex/katex.min.css'],
  ['https://cdn.jsdelivr.net/npm/katex@0.18.4/dist/katex.min.js', 'linear/vendor/katex/katex.min.js'],
  ['https://cdn.jsdelivr.net/npm/katex@0.18.4/dist/contrib/auto-render.min.js', 'linear/vendor/katex/auto-render.min.js'],
  ['https://cdn.jsdelivr.net/npm/prismjs@1.30.0/plugins/diff-highlight/prism-diff-highlight.min.css', 'linear/vendor/prism/plugins/diff-highlight/prism-diff-highlight.min.css'],
  ['https://cdn.jsdelivr.net/npm/prismjs@1.30.0/plugins/diff-highlight/prism-diff-highlight.min.js', 'linear/vendor/prism/plugins/diff-highlight/prism-diff-highlight.min.js'],
  ['https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css', 'linear/vendor/codemirror/codemirror.css'],
  ['https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js', 'linear/vendor/codemirror/codemirror.js'],
  ['https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/xml/xml.min.js', 'linear/vendor/codemirror/mode/xml.js'],
  ['https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/meta.min.js', 'linear/vendor/codemirror/mode/meta.js'],
  ['https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/markdown/markdown.min.js', 'linear/vendor/codemirror/mode/markdown.js'],
  ['https://cdn.jsdelivr.net/gh/amlatyrngom/tressoir-external@v0.1.7/extension/src/notebook/assets/linear/tressoir-linear.css', 'linear/tressoir-linear.css'],
  ['https://cdn.jsdelivr.net/gh/amlatyrngom/tressoir-external@v0.1.7/extension/src/notebook/assets/linear/tressoir-linear.js', 'linear/tressoir-linear.js'],
  ...[
    'prism-core.min.js',
    'prism-markup.min.js',
    'prism-css.min.js',
    'prism-clike.min.js',
    'prism-javascript.min.js',
    'prism-typescript.min.js',
    'prism-jsx.min.js',
    'prism-tsx.min.js',
    'prism-json.min.js',
    'prism-yaml.min.js',
    'prism-markdown.min.js',
    'prism-bash.min.js',
    'prism-python.min.js',
    'prism-rust.min.js',
    'prism-sql.min.js',
    'prism-diff.min.js',
  ].map((filename): [string, string] => [
    `https://cdn.jsdelivr.net/npm/prismjs@1.30.0/components/${filename}`,
    `linear/vendor/prism/components/${filename}`,
  ]),
])

export function bundledHtmlAssetPath(url: string): string | undefined {
  return BUNDLED_HTML_ASSETS.get(url)
}

// Contained-basename allowlist. Keep both legacy forms and accept the opt-in
// `<source>.interactions.json` form. The latter may contain ordinary basename dots but never
// traversal, separators, or a leading dot.
const LEGACY_INTERACTIONS_FILE_RE = /^interactions(\.[A-Za-z0-9_-]+)?\.json$/
const SCOPED_INTERACTIONS_FILE_RE = /^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._-]*\.interactions\.json$/
const MAX_INTERACTION_KEY_LEN = 256
// A supported macOS/Linux filename component can contain up to 255 bytes, so 512 accommodates
// every exact source stem plus the automatic suffix. Arbitrary authored keys retain the tighter
// generic cap above.
const MAX_AUTOMATIC_INTERACTION_KEY_LEN = 512
const MAX_INTERACTIONS_BYTES = 512 * 1024
const LEGACY_FREE_FORM_FEEDBACK_KEY = 'free_form_feedback'

export const NOTEBOOK_VIEW_TYPE = 'tressoir.notebookHtml'
// Optional renderer for ordinary `*.html`: available through Reopen With without replacing the
// normal text editor. A distinct view type is required because custom-editor priority applies to
// the whole contribution, while `*.tressoir.html` must remain a default renderer.
export const GENERIC_HTML_VIEW_TYPE = 'tressoir.genericHtml'
// USER_ARTIFACT_MD: a SECOND custom editor for `*.tressoir.md`. Same provider class, but the
// `md` source kind projects the markdown source -> the LOCKED user-artifact HTML in the webview
// (via the bundled eval-free TressoirMd runtime) BEFORE feeding the existing morph pipeline. A
// distinct viewType keeps md-vs-html dispatch clean (no content sniffing).
export const NOTEBOOK_MD_VIEW_TYPE = 'tressoir.notebookMd'

// 'html' = legacy authored `.tressoir.html` (rendered verbatim). 'md' = `.tressoir.md` projected
// client-side by the bundled TressoirMd runtime.
export type NotebookSourceKind = 'html' | 'md'

const SHARED_EDITOR_OPTIONS = {
  // Keep the webview realm alive when the editor tab is hidden so switching away and back
  // does NOT tear down + rebuild the page (which would reset runtime DOM state — open
  // disclosures, the selected milestone, in-progress typing — leaving only the persisted
  // scroll restored). The morph "lightweight refresh" only covers document-change updates,
  // not visibility reloads, so this is the correct fix for the tab-switch state loss.
  webviewOptions: { retainContextWhenHidden: true },
  supportsMultipleEditorsPerDocument: false,
} as const

export function registerTressoirNotebookEditor(
  context: vscode.ExtensionContext,
): vscode.Disposable {
  return vscode.window.registerCustomEditorProvider(
    NOTEBOOK_VIEW_TYPE,
    new TressoirNotebookEditorProvider(context, 'html'),
    SHARED_EDITOR_OPTIONS,
  )
}

export function registerGenericHtmlEditor(
  context: vscode.ExtensionContext,
): vscode.Disposable {
  return vscode.window.registerCustomEditorProvider(
    GENERIC_HTML_VIEW_TYPE,
    new TressoirNotebookEditorProvider(context, 'html'),
    SHARED_EDITOR_OPTIONS,
  )
}

export function registerTressoirNotebookMdEditor(
  context: vscode.ExtensionContext,
): vscode.Disposable {
  return vscode.window.registerCustomEditorProvider(
    NOTEBOOK_MD_VIEW_TYPE,
    new TressoirNotebookEditorProvider(context, 'md'),
    SHARED_EDITOR_OPTIONS,
  )
}

export class TressoirNotebookEditorProvider implements vscode.CustomTextEditorProvider {
  // Per-file promise chains that serialize read-modify-write of each interactions.*.json file
  // (keyed by target fsPath) so concurrent storeInteraction calls cannot drop updates.
  private readonly interactionWriteChains = new Map<string, Promise<unknown>>()

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly sourceKind: NotebookSourceKind = 'html',
  ) {}

  async resolveCustomTextEditor(
    document: vscode.TextDocument,
    webviewPanel: vscode.WebviewPanel,
  ): Promise<void> {
    let currentDocument = document
    // A custom-editor instance is bound to this source document. Keep its interaction namespace
    // in the provider as well as the webview dataset so even an older/stale webview runtime that
    // still asks for plain `free_form_feedback` cannot read or write a sibling artifact's value.
    const sourceNamespace = sourceNamespaceFromPath(currentDocument.fileName)
    const feedbackKey = freeFormFeedbackKey(sourceNamespace)
    const interactionsFilename =
      this.sourceKind === 'md' && this.parseFrontmatterInteractions(currentDocument.getText()) !== 'shared'
        ? scopedInteractionsFilename(sourceNamespace)
        : 'interactions.json'

    // Widen localResourceRoots to the artifact's own folder so authored relative includes
    // (e.g. an author's own ./vendor/d3.js or ./data.json) are served as webview resources. Scope
    // it to that directory only — do not expose the whole workspace.
    const artifactFolder = vscode.Uri.joinPath(currentDocument.uri, '..')
    webviewPanel.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this.context.extensionUri, 'dist'),
        artifactFolder,
      ],
    }

    // Build the webview document ONCE to establish the realm. Authored-content changes do NOT
    // rebuild this (that would tear down the realm and lose the reader's active tab / open
    // disclosures); instead a doc change posts an `update` and the webview DOM-morphs in place
    // (see `postUpdate` / webview/main.ts). A full rebuild only recurs on genuine realm loss
    // (the webview reloads and re-posts `ready`); the reader's scroll is restored from webview
    // state on such a reload (see webview/main.ts).
    // Provision author-declared third-party libraries (md only) BEFORE the realm is built so their
    // <script src> tags are part of the one-time webview document. Editing the `links:` list later
    // requires reopening the artifact (the realm is built once; content edits only morph). Network
    // failures are best-effort (logged + skipped) and never block the render.
    let userLinks: { styleTags: string[]; scriptTags: string[] } = { styleTags: [], scriptTags: [] }
    if (this.sourceKind === 'md') {
      try {
        userLinks = await this.provisionUserLinks(
          this.parseFrontmatterLinks(currentDocument.getText()),
          artifactFolder,
          webviewPanel.webview,
        )
      } catch (err) {
        console.warn('[tressoir-notebook] Author-link provisioning failed:', err)
      }
    }

    const renderWebviewHtml = (): void => {
      webviewPanel.webview.html = this.buildWebviewHtml(
        webviewPanel.webview,
        artifactFolder,
        userLinks,
        sourceNamespace,
        feedbackKey,
        interactionsFilename,
      )
    }

    setActiveNotebookDocument(currentDocument.fileName)

    const postMessage = (
      message: NotebookStateMessage | NotebookUpdateMessage | NotebookThemeMessage | NotebookTypographyMessage,
      label: string,
    ): void => {
      void webviewPanel.webview.postMessage(message).then(
        (delivered) => {
          if (!delivered) {
            console.warn(`[tressoir-notebook] Webview dropped ${label} message.`)
          }
        },
        (error) => {
          console.error(`[tressoir-notebook] Failed to post ${label} message.`, error)
        },
      )
    }

    const postState = async (): Promise<void> => {
      const interactions = this.scopeLegacyFreeFormFeedback(
        await this.readInteractions(artifactFolder),
        feedbackKey,
      )
      postMessage(
        {
          type: 'state',
          sourceHtml: this.sourceHtmlForWebview(currentDocument.getText(), webviewPanel.webview),
          sourceKind: this.sourceKind,
          theme: this.currentTheme(),
          interactions,
          baseFontSize: this.currentBaseFontSize(currentDocument),
        },
        'state',
      )
    }

    const postUpdate = async (): Promise<void> => {
      const interactions = this.scopeLegacyFreeFormFeedback(
        await this.readInteractions(artifactFolder),
        feedbackKey,
      )
      postMessage(
        {
          type: 'update',
          sourceHtml: this.sourceHtmlForWebview(currentDocument.getText(), webviewPanel.webview),
          sourceKind: this.sourceKind,
          interactions,
          baseFontSize: this.currentBaseFontSize(currentDocument),
        },
        'update',
      )
    }

    const postTheme = (): void => {
      postMessage({ type: 'theme', theme: this.currentTheme() }, 'theme')
    }

    const postTypography = (): void => {
      postMessage(
        {
          type: 'typography',
          sourceKind: this.sourceKind,
          baseFontSize: this.currentBaseFontSize(currentDocument),
        },
        'typography',
      )
    }

    const documentChangeDisposable = vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.uri.toString() !== currentDocument.uri.toString()) {
        return
      }
      currentDocument = event.document
      setActiveNotebookDocument(currentDocument.fileName)
      // Save/dirty-state transitions can emit empty change batches; avoid rerendering for those.
      if (Array.isArray(event.contentChanges) && event.contentChanges.length === 0) {
        return
      }
      setNotebookSelection(null)
      // No bridge-owned editors anymore. Rather than tear down and rebuild `webview.html`
      // (which resets the realm and loses the active tab / open disclosures / focus), keep the
      // realm alive and post an `update`: the webview DOM-morphs the live preview to match the
      // new authored HTML (lightweight refresh). A full `webview.html` reset only happens on the
      // initial render / realm loss (a fresh load posts `ready`, re-hydrated via postState).
      void postUpdate()
    })

    const themeChangeDisposable = vscode.window.onDidChangeActiveColorTheme(() => {
      postTheme()
    })

    const typographySetting =
      this.sourceKind === 'md'
        ? 'tressoir.markdown.baseFontSize'
        : 'tressoir.html.baseFontSize'
    const configurationChangeDisposable = vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration(typographySetting, currentDocument.uri)) {
        postTypography()
      }
    })

    const receiveDisposable = webviewPanel.webview.onDidReceiveMessage(
      async (message: NotebookInboundMessage) => {
        switch (message.type) {
          case 'ready':
            await postState()
            return
          case 'selectionChanged':
            setActiveNotebookDocument(currentDocument.fileName)
            setNotebookSelection(
              message.selectedText.length > 0
                ? { path: currentDocument.fileName, text: message.selectedText }
                : null,
            )
            return
          case 'openArtifactFile': {
            const rel = message.path
            // Relative links may traverse upward when the resolved target remains inside either
            // the artifact folder or an open workspace folder. This supports links from
            // IB/ARTIFACTS/... to project files without granting arbitrary filesystem access.
            if (
              typeof rel !== 'string' ||
              rel.length === 0 ||
              rel.includes('\0') ||
              path.isAbsolute(rel) ||
              /^[A-Za-z][A-Za-z0-9+.-]*:/.test(rel)
            ) {
              return
            }
            const targetFs = path.resolve(artifactFolder.fsPath, rel)
            const allowedRoots = [
              artifactFolder.fsPath,
              ...(vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath),
            ]
            const contained = allowedRoots.some((root) => {
              const relative = path.relative(path.resolve(root), targetFs)
              return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
            })
            if (!contained) {
              return
            }
            const target = vscode.Uri.file(targetFs)
            void vscode.commands.executeCommand('vscode.open', target)
            return
          }
          case 'storeInteraction':
            await this.handleStoreInteraction(
              artifactFolder,
              message,
              feedbackKey,
              interactionsFilename,
            )
            return
          case 'openRawText':
            return
        }
      },
    )

    const viewStateDisposable = webviewPanel.onDidChangeViewState(() => {
      if (webviewPanel.visible) {
        setActiveNotebookDocument(currentDocument.fileName)
      } else {
        clearNotebookStateForPath(currentDocument.fileName)
      }
    })

    const disposeAll = (): void => {
      clearNotebookStateForPath(currentDocument.fileName)
      documentChangeDisposable.dispose()
      themeChangeDisposable.dispose()
      configurationChangeDisposable.dispose()
      receiveDisposable.dispose()
      viewStateDisposable.dispose()
    }

    webviewPanel.onDidDispose(disposeAll)

    // Install the message listener before creating the webview realm. The webview's `ready`
    // message is the single initialization handshake; proactively posting state here as well can
    // race with `ready` and execute authored top-level declarations twice in the same realm.
    renderWebviewHtml()
  }

  private currentBaseFontSize(document: vscode.TextDocument): number {
    const key = this.sourceKind === 'md' ? 'markdown.baseFontSize' : 'html.baseFontSize'
    const fallback = this.sourceKind === 'md' ? 14 : 16
    const configured = vscode.workspace
      .getConfiguration('tressoir', document.uri)
      .get<number>(key, fallback)
    return Number.isFinite(configured) ? Math.min(28, Math.max(10, configured)) : fallback
  }

  // Validate + merge + persist a single interaction into a contained JSON file. This is the
  // ONLY disk-write reachable from authored content; the validation here is the security
  // boundary (basename allowlist, key/size caps, JSON-only). Writes to the SAME file are
  // serialized through a per-file promise chain so a debounced editor flush and an immediate
  // discrete pick (both targeting interactions.json) cannot interleave read-modify-write and
  // silently drop an update.
  private async handleStoreInteraction(
    artifactFolder: vscode.Uri,
    message: { key: string; value: unknown; filename?: string },
    feedbackKey: string,
    defaultInteractionsFilename = 'interactions.json',
  ): Promise<void> {
    const filename =
      typeof message.filename === 'string' && message.filename.length > 0
        ? message.filename
        : defaultInteractionsFilename
    if (!isInteractionsFilename(filename)) {
      console.warn(`[tressoir-notebook] Rejected storeInteraction for invalid filename: ${filename}`)
      return
    }
    if (typeof message.key !== 'string' || message.key.length === 0) {
      return
    }
    // Compatibility containment: pre-namespacing Markdown runtimes use the shared plain key.
    // Scope that reserved automatic-widget key at the provider boundary. HTML keys are left
    // alone. Markdown authors must not use this reserved key for an explicit :::input; the
    // projector lint and skill both enforce that contract because a stale runtime cannot attach
    // enough provenance for the provider to distinguish those two uses.
    const key =
      this.sourceKind === 'md' &&
      message.key === LEGACY_FREE_FORM_FEEDBACK_KEY &&
      feedbackKey.length > 0
        ? feedbackKey
        : message.key
    const maxKeyLength =
      this.sourceKind === 'md' && key === feedbackKey
        ? MAX_AUTOMATIC_INTERACTION_KEY_LEN
        : MAX_INTERACTION_KEY_LEN
    if (key.length > maxKeyLength) {
      return
    }
    const target = vscode.Uri.joinPath(artifactFolder, filename)
    const chainKey = target.fsPath
    const previous = this.interactionWriteChains.get(chainKey) ?? Promise.resolve()
    const next = previous.then(() =>
      this.mergeAndWriteInteraction(target, key, message.value),
    )
    // Swallow rejection on the stored chain so a single failed write doesn't poison the queue;
    // the awaited `next` below still surfaces nothing (writes are best-effort/logged).
    this.interactionWriteChains.set(
      chainKey,
      next.catch(() => undefined),
    )
    await next.catch(() => undefined)
  }

  // Read-modify-write a single interaction file (called serially per file via the chain above).
  private async mergeAndWriteInteraction(
    target: vscode.Uri,
    key: string,
    value: unknown,
  ): Promise<void> {
    let current: Record<string, unknown> = {}
    try {
      const bytes = await vscode.workspace.fs.readFile(target)
      const parsed = JSON.parse(new TextDecoder().decode(bytes))
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        current = parsed as Record<string, unknown>
      }
    } catch {
      // New or unreadable file: start fresh.
    }
    current[key] = value
    let serialized: string
    try {
      serialized = JSON.stringify(current, null, 2)
    } catch {
      // Non-serializable value (cycle / BigInt / etc): reject rather than corrupt the file.
      return
    }
    // Cap on the actual UTF-8 byte size that will be written (not UTF-16 code-unit length).
    const encoded = new TextEncoder().encode(serialized)
    if (encoded.length > MAX_INTERACTIONS_BYTES) {
      console.warn('[tressoir-notebook] Rejected storeInteraction: serialized size over cap.')
      return
    }
    await vscode.workspace.fs.writeFile(target, encoded)
  }

  // Read all contained interactions.*.json files in the artifact folder into a snapshot the
  // webview injects so authored content can restore prior user input on (re)render.
  private async readInteractions(artifactFolder: vscode.Uri): Promise<InteractionsSnapshot> {
    const snapshot: InteractionsSnapshot = {}
    let entries: [string, vscode.FileType][]
    try {
      entries = await vscode.workspace.fs.readDirectory(artifactFolder)
    } catch {
      return snapshot
    }
    for (const [name, type] of entries) {
      if (type !== vscode.FileType.File || !isInteractionsFilename(name)) {
        continue
      }
      try {
        const bytes = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(artifactFolder, name))
        const parsed = JSON.parse(new TextDecoder().decode(bytes))
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          snapshot[name] = parsed as Record<string, unknown>
        }
      } catch {
        // Skip corrupt/unreadable interaction files.
      }
    }
    return snapshot
  }

  // Present the reserved plain key as a document-local compatibility alias to stale Markdown
  // webviews. The ambiguous old shared value is deliberately hidden: if this document has no
  // scoped value yet, an old runtime must start empty rather than inheriting a sibling's text.
  // The snapshot is copied only for the webview; interactions.json on disk is not migrated or
  // destructively edited.
  private scopeLegacyFreeFormFeedback(
    snapshot: InteractionsSnapshot,
    feedbackKey: string,
  ): InteractionsSnapshot {
    if (this.sourceKind !== 'md') {
      return snapshot
    }
    const bucket = snapshot['interactions.json']
    if (!bucket) {
      return snapshot
    }
    const scopedBucket = { ...bucket }
    const scopedValue = bucket[feedbackKey]
    if (scopedValue === undefined) {
      delete scopedBucket[LEGACY_FREE_FORM_FEEDBACK_KEY]
    } else {
      scopedBucket[LEGACY_FREE_FORM_FEEDBACK_KEY] = scopedValue
    }
    return { ...snapshot, 'interactions.json': scopedBucket }
  }

  private currentTheme(): NotebookThemeState {
    return notebookThemeFromColorKind(vscode.window.activeColorTheme.kind)
  }

  // Projection parser followed by the exact tracked linear vendor/runtime bundle. The same bytes
  // are copied beside new HTML artifacts and into dist/assets/linear for Markdown.
  private static readonly MD_CORE_PREFIX: readonly string[] = [
    'core/tressoir-remark.umd.js',
    'core/js-yaml.min.js',
    'linear/vendor/katex/katex.min.js',
    'linear/vendor/katex/auto-render.min.js',
    'linear/vendor/prism/components/prism-core.min.js',
    'linear/vendor/prism/components/prism-markup.min.js',
    'linear/vendor/prism/components/prism-css.min.js',
    'linear/vendor/prism/components/prism-clike.min.js',
    'linear/vendor/prism/components/prism-javascript.min.js',
    'linear/vendor/prism/components/prism-typescript.min.js',
    'linear/vendor/prism/components/prism-jsx.min.js',
    'linear/vendor/prism/components/prism-tsx.min.js',
    'linear/vendor/prism/components/prism-json.min.js',
    'linear/vendor/prism/components/prism-yaml.min.js',
    'linear/vendor/prism/components/prism-markdown.min.js',
    'linear/vendor/prism/components/prism-bash.min.js',
    'linear/vendor/prism/components/prism-python.min.js',
    'linear/vendor/prism/components/prism-rust.min.js',
    'linear/vendor/prism/components/prism-sql.min.js',
    'linear/vendor/prism/components/prism-diff.min.js',
    'linear/vendor/prism/plugins/diff-highlight/prism-diff-highlight.min.js',
    'linear/vendor/codemirror/codemirror.js',
    'linear/vendor/codemirror/mode/xml.js',
    'linear/vendor/codemirror/mode/meta.js',
    'linear/vendor/codemirror/mode/markdown.js',
  ]

  // Parse the front-matter `links:` string list (dependency-free; the extension host has no
  // js-yaml). Supports a block list (`links:` then `  - <entry>` lines) and an inline flow list
  // (`links: [a, b]`). Each entry is a JS or CSS library, LOCAL (artifact-relative `./x.js`) or
  // REMOTE (http(s) URL) — the runtime classifies them on provisioning (see below). Order is
  // preserved; entries are returned verbatim (trimmed/unquoted).
  private parseFrontmatterLinks(text: string): string[] {
    const fmMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)
    if (!fmMatch) {
      return []
    }
    const lines = fmMatch[1].split(/\r?\n/)
    const entries: string[] = []
    let inLinks = false
    let linksIndent = -1
    const unquote = (s: string): string => s.trim().replace(/^['"]|['"]$/g, '').trim()
    for (const line of lines) {
      const keyMatch = /^(\s*)links\s*:\s*(.*)$/.exec(line)
      if (keyMatch) {
        linksIndent = keyMatch[1].length
        const inline = keyMatch[2].trim()
        if (inline.startsWith('[')) {
          inline
            .replace(/^\[|\]$/g, '')
            .split(',')
            .forEach((part) => {
              const v = unquote(part)
              if (v) entries.push(v)
            })
          inLinks = false
        } else {
          inLinks = true
        }
        continue
      }
      if (inLinks) {
        const itemMatch = /^(\s*)-\s+(.*)$/.exec(line)
        if (itemMatch && itemMatch[1].length > linksIndent) {
          const v = unquote(itemMatch[2])
          if (v) entries.push(v)
          continue
        }
        // A sibling/parent key (same or lower indent) ends the links block.
        if (/^\s*\S+\s*:/.test(line)) {
          const otherIndent = /^(\s*)/.exec(line)?.[1].length ?? 0
          if (otherIndent <= linksIndent) inLinks = false
        }
      }
    }
    return entries.filter((e) => e.length > 0)
  }

  // Markdown interactions are artifact-scoped by default. `interactions: shared` is the explicit
  // compatibility override; `interactions: scoped` remains accepted.
  private parseFrontmatterInteractions(text: string): 'shared' | 'scoped' {
    const fmMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)
    if (!fmMatch) {
      return 'scoped'
    }
    for (const line of fmMatch[1].split(/\r?\n/)) {
      const match = /^\s*interactions\s*:\s*(.*?)\s*$/.exec(line)
      if (!match) continue
      const value = match[1].replace(/^['"]|['"]$/g, '').trim().toLowerCase()
      return value === 'shared' ? 'shared' : 'scoped'
    }
    return 'scoped'
  }

  // Stable, filesystem-safe cache name for a declared script URL: a short content hash of the URL
  // (so two different URLs never collide) prefixed to a sanitized basename (for human legibility).
  private cacheFilenameForUrl(url: string): string {
    const hash = crypto.createHash('sha256').update(url).digest('hex').slice(0, 10)
    let base = (url.split('?')[0].split('#')[0].split('/').pop() || 'lib').replace(
      /[^A-Za-z0-9._-]/g,
      '_',
    )
    if (!/\.js$/i.test(base)) base += '.js'
    return `${hash}-${base}`
  }

  // Provision author-declared `links:` (JS + CSS, local or remote) into ready <link>/<script>
  // tag strings, classified by extension and locality. The CSP makes the rules:
  //   - remote `.css`  -> `<link href=REMOTE>`            (style-src allows `https:`)
  //   - local  `.css`  -> `<link>` via asWebviewUri        (style-src ${cspSource})
  //   - remote `.js`   -> fetch+cache into the gitignored artifact-adjacent `vendor/`, then
  //                       `<script src>` via asWebviewUri   (script-src has NO remote host, only
  //                                                          ${cspSource}+nonce — so it MUST be local)
  //   - local  `.js`   -> `<script src>` via asWebviewUri   (script-src ${cspSource})
  // Anything without a `.css` extension is treated as a script. Failures (e.g. a network blip
  // fetching a remote lib) are logged and skipped (best-effort) so they never block the render.
  // Runs in the Node extension host (no CSP); local files resolve because artifactFolder is in
  // localResourceRoots.
  private async provisionUserLinks(
    entries: string[],
    artifactFolder: vscode.Uri,
    webview: vscode.Webview,
  ): Promise<{ styleTags: string[]; scriptTags: string[] }> {
    const styleTags: string[] = []
    const scriptTags: string[] = []
    if (entries.length === 0) {
      return { styleTags, scriptTags }
    }
    const vendorDir = vscode.Uri.joinPath(artifactFolder, 'vendor')
    const escAttr = (s: string): string => s.replace(/"/g, '&quot;')
    const localUri = (rel: string): vscode.Uri =>
      vscode.Uri.joinPath(artifactFolder, ...rel.replace(/^\.\//, '').split('/'))
    for (const entry of entries) {
      const isRemote = /^https?:\/\//i.test(entry)
      const lower = entry.split('?')[0].split('#')[0].toLowerCase()
      const isCss = lower.endsWith('.css')
      try {
        if (isCss) {
          const href = isRemote ? entry : webview.asWebviewUri(localUri(entry)).toString()
          styleTags.push(`<link rel="stylesheet" href="${escAttr(href)}" />`)
        } else if (isRemote) {
          const dest = vscode.Uri.joinPath(vendorDir, this.cacheFilenameForUrl(entry))
          if (!fs.existsSync(dest.fsPath)) {
            const data = await fetchRemote(entry)
            fs.mkdirSync(vendorDir.fsPath, { recursive: true })
            fs.writeFileSync(dest.fsPath, data)
            console.log(`[tressoir-notebook] Provisioned author link ${entry} -> ${dest.fsPath}`)
          }
          scriptTags.push(`<script src="${escAttr(webview.asWebviewUri(dest).toString())}"></script>`)
        } else {
          scriptTags.push(`<script src="${escAttr(webview.asWebviewUri(localUri(entry)).toString())}"></script>`)
        }
      } catch (err) {
        console.warn(`[tressoir-notebook] Failed to provision author link ${entry}:`, err)
      }
    }
    return { styleTags, scriptTags }
  }

  // Build the <link>/<script> tags that load the committed extension-core md projection runtime +
  // locked CSS from the extension's dist/assets (copied there at build time from
  // src/notebook/assets/core). Returns absolute asWebviewUri(...) references (NOT an author <base
  // href>) so they resolve regardless of the artifact folder. Missing files are skipped
  // (best-effort), but core/ is committed so a normal checkout always has them.
  private buildMdAssetTags(
    webview: vscode.Webview,
    userLinks: { styleTags: string[]; scriptTags: string[] } = { styleTags: [], scriptTags: [] },
  ): { styles: string; scripts: string } {
    const assetsDir = vscode.Uri.joinPath(this.context.extensionUri, 'dist', 'assets')
    const assetUri = (rel: string): string =>
      webview.asWebviewUri(vscode.Uri.joinPath(assetsDir, ...rel.split('/'))).toString()
    const exists = (rel: string): boolean => {
      try {
        return fs.existsSync(vscode.Uri.joinPath(assetsDir, ...rel.split('/')).fsPath)
      } catch {
        return false
      }
    }
    // Canonical linear styles first, then the narrow Markdown adapter and author overrides.
    const styleLinks = [
      ...[
        'linear/vendor/katex/katex.min.css',
        'linear/vendor/prism/plugins/diff-highlight/prism-diff-highlight.min.css',
        'linear/vendor/codemirror/codemirror.css',
        'linear/tressoir-linear.css',
        'artifact.css',
      ]
        .filter(exists)
        .map((rel) => `<link rel="stylesheet" href="${assetUri(rel)}" />`),
      ...userLinks.styleTags,
    ].join('\n    ')
    const orderedScripts = [
      ...TressoirNotebookEditorProvider.MD_CORE_PREFIX,
    ]
    // Core libs first, then author-declared `links:` scripts (local or vendor-cached remote),
    // then the projection runtime LAST so it can consume them.
    const coreTags = orderedScripts
      .filter(exists)
      .map((rel) => `<script src="${assetUri(rel)}"></script>`)
    const runtimeTags = ['tressoir-md.js', 'linear/tressoir-linear.js']
      .filter(exists)
      .map((rel) => `<script src="${assetUri(rel)}"></script>`)
    const scriptTags = [...coreTags, ...userLinks.scriptTags, ...runtimeTags].join('\n    ')
    return { styles: styleLinks, scripts: scriptTags }
  }

  // The portable HTML starter names stable public resources so the file works in a normal
  // browser. Inside Tressoir, substitute the byte-identical assets already shipped in the VSIX.
  // If a package is incomplete, leave the HTTPS URL untouched as a network fallback rather than
  // manufacturing a broken local URI. Only exact, version-pinned URLs are eligible.
  private sourceHtmlForWebview(sourceHtml: string, webview: vscode.Webview): string {
    if (this.sourceKind !== 'html') {
      return sourceHtml
    }
    const assetsDir = vscode.Uri.joinPath(this.context.extensionUri, 'dist', 'assets')
    return sourceHtml.replace(
      /\b(src|href)(\s*=\s*)(["'])(https:\/\/[^"']+)\3/gi,
      (full, attribute: string, separator: string, quote: string, url: string) => {
        const relative = bundledHtmlAssetPath(url)
        if (!relative) {
          return full
        }
        const local = vscode.Uri.joinPath(assetsDir, ...relative.split('/'))
        if (!fs.existsSync(local.fsPath)) {
          return full
        }
        return `${attribute}${separator}${quote}${webview.asWebviewUri(local)}${quote}`
      },
    )
  }

  private buildWebviewHtml(
    webview: vscode.Webview,
    artifactFolder: vscode.Uri,
    userLinks: { styleTags: string[]; scriptTags: string[] } = { styleTags: [], scriptTags: [] },
    sourceNamespace = '',
    feedbackKey = freeFormFeedbackKey(sourceNamespace),
    interactionsFilename = 'interactions.json',
  ): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, 'dist', 'notebook-webview.js'),
    )
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, 'dist', 'notebook-webview.css'),
    )
    // Base for authored relative includes (./vendor/x.js, ./data.json). The trailing slash is
    // REQUIRED so the document base resolves child paths against the artifact folder.
    const artifactBaseUri = `${webview.asWebviewUri(artifactFolder)}/`

    // Per-render CSP nonce. Authored content is rendered into the main webview document, so
    // re-created INLINE authored scripts are stamped with this nonce (see scriptInjection.ts);
    // relative authored `<script src>` and the webview's own bundle stay covered by the
    // ${webview.cspSource} host-source. Direct HTTPS scripts are deliberately allowed for this
    // trusted-artifact renderer so a compact HTML file can use pinned CDN/GitHub dependencies.
    // No 'unsafe-inline'/'unsafe-eval'/'strict-dynamic', and insecure HTTP scripts stay blocked.
    // connect-src ${webview.cspSource} is REQUIRED for authored fetch('./...').
    const nonce = getNonce()
    const mdAssets =
      this.sourceKind === 'md'
        ? this.buildMdAssetTags(webview, userLinks)
        : { styles: '', scripts: '' }
    const csp = [
      "default-src 'none'",
      `img-src ${webview.cspSource} data: https: http: blob:`,
      `style-src ${webview.cspSource} 'unsafe-inline' https:`,
      `font-src ${webview.cspSource} data: https:`,
      `script-src ${webview.cspSource} https: 'nonce-${nonce}'`,
      `worker-src ${webview.cspSource} blob:`,
      `connect-src ${webview.cspSource}`,
      `frame-src ${webview.cspSource} blob: data:`,
    ].join('; ')

    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="${csp}" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="stylesheet" href="${styleUri}" />
    ${mdAssets.styles}
    <title>Tressoir Notebook</title>
  </head>
  <body
    data-artifact-base-uri="${artifactBaseUri}"
    data-csp-nonce="${nonce}"
    data-source-name="${escapeHtmlAttribute(sourceNamespace)}"
    data-feedback-key="${escapeHtmlAttribute(feedbackKey)}"
    data-interactions-file="${escapeHtmlAttribute(interactionsFilename)}"
    data-source-kind="${this.sourceKind}"
  >
    <div id="app"></div>
    ${mdAssets.scripts}
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`
  }
}

// Derive one injective, bounded browser/storage namespace from the exact supported POSIX
// basename. Do not trim or treat backslash as a POSIX separator: both would collapse valid
// sibling names. The complete key is HTML-escaped only for transport, so the browser recovers
// this same exact stem, including whitespace, entities, quotes, and Unicode. Exact lowercase
// artifact suffixes are the supported selectors; an unexpected suffix is retained rather than
// normalized into another basename.
function sourceNamespaceFromPath(p: string): string {
  const slash = p.lastIndexOf('/')
  const base = slash >= 0 ? p.slice(slash + 1) : p
  let stem = base
  for (const suffix of ['.tressoir.md', '.tressoir.html', '.html']) {
    if (base.endsWith(suffix)) {
      stem = base.slice(0, -suffix.length)
      break
    }
  }
  return stem
}

function freeFormFeedbackKey(sourceName: string): string {
  return `${sourceName}-free_form_feedback`
}

function scopedInteractionsFilename(sourceName: string): string {
  // Preserve ordinary human-readable basenames exactly. For unusual source names, retain a
  // readable sanitized stem plus a short hash so distinct artifacts cannot collapse together.
  if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$/.test(sourceName) && !sourceName.includes('..')) {
    return `${sourceName}.interactions.json`
  }
  const readable = sourceName.replace(/[^A-Za-z0-9._-]/g, '_').replace(/^\.+/, '').slice(0, 120)
  const hash = crypto.createHash('sha256').update(sourceName).digest('hex').slice(0, 10)
  return `${readable || 'artifact'}-${hash}.interactions.json`
}

function isInteractionsFilename(filename: string): boolean {
  return (
    filename.length <= 255 &&
    (LEGACY_INTERACTIONS_FILE_RE.test(filename) || SCOPED_INTERACTIONS_FILE_RE.test(filename))
  )
}

function escapeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // HTML input preprocessing normalizes literal CR and CRLF to LF before attribute parsing.
    // Numeric references are decoded afterwards, preserving distinct POSIX basenames exactly.
    .replace(/\r/g, '&#13;')
    .replace(/\n/g, '&#10;')
}

function getNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let text = ''
  for (let i = 0; i < 32; i += 1) {
    text += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return text
}

// Fetch a remote URL in the extension host (Node — no webview CSP applies here) following a
// bounded number of redirects. Used ONLY to provision author-declared third-party libraries
// (front-matter `links:`) into the artifact-adjacent `vendor/` cache on first open; the cached
// file is then served back to the webview under CSP via asWebviewUri. Rejects non-200 and
// non-http(s) targets, and aborts a response that exceeds `maxBytes` (defense-in-depth so a
// runaway/huge download never blocks opening the artifact).
export const FETCH_REMOTE_MAX_BYTES = 16 * 1024 * 1024
export function fetchRemote(url: string, redirectsLeft = 5, maxBytes = FETCH_REMOTE_MAX_BYTES): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    let parsed: URL
    try {
      parsed = new URL(url)
    } catch {
      reject(new Error(`invalid URL: ${url}`))
      return
    }
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      reject(new Error(`refusing non-http(s) URL: ${url}`))
      return
    }
    const lib = parsed.protocol === 'https:' ? https : http
    const req = lib.get(url, (res) => {
      const status = res.statusCode ?? 0
      if (status >= 300 && status < 400 && res.headers.location && redirectsLeft > 0) {
        res.resume()
        const next = new URL(res.headers.location, url).toString()
        fetchRemote(next, redirectsLeft - 1, maxBytes).then(resolve, reject)
        return
      }
      if (status !== 200) {
        res.resume()
        reject(new Error(`HTTP ${status} fetching ${url}`))
        return
      }
      const chunks: Buffer[] = []
      let received = 0
      res.on('data', (c: Buffer) => {
        received += c.length
        if (received > maxBytes) {
          res.destroy()
          reject(new Error(`response exceeds ${maxBytes} bytes fetching ${url}`))
          return
        }
        chunks.push(c)
      })
      res.on('end', () => resolve(Buffer.concat(chunks)))
      res.on('error', reject)
    })
    req.on('error', reject)
    req.setTimeout(20000, () => req.destroy(new Error(`timeout fetching ${url}`)))
  })
}
