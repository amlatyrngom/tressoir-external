import * as vscode from 'vscode'
import * as fs from 'fs'
import * as http from 'http'
import * as https from 'https'
import * as crypto from 'crypto'
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
      // Narrow, contained navigation: open a sibling file INSIDE the artifact folder in the editor.
      type: 'openArtifactFile'
      path: string
    }
  | {
      // Persist an authored-content interaction (e.g. a CodeMirror feedback field, a decision
      // pick) to a contained JSON file in the artifact folder. The ONLY authored disk-write
      // capability; strictly validated (contained basename, JSON-only, size-capped).
      type: 'storeInteraction'
      key: string
      value: unknown
      filename?: string
    }

// Contained-basename allowlist: `interactions.json` or `interactions.<suffix>.json`. The pattern
// forbids path separators and `..`, so a matching name is always a basename inside the folder.
const INTERACTIONS_FILE_RE = /^interactions(\.[A-Za-z0-9_-]+)?\.json$/
const MAX_INTERACTION_KEY_LEN = 256
const MAX_INTERACTIONS_BYTES = 512 * 1024

export const NOTEBOOK_VIEW_TYPE = 'tressoir.notebookHtml'
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
        sourceNameFromPath(currentDocument.fileName),
      )
    }
    renderWebviewHtml()

    setActiveNotebookDocument(currentDocument.fileName)

    const postMessage = (
      message: NotebookStateMessage | NotebookUpdateMessage | NotebookThemeMessage,
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
      const interactions = await this.readInteractions(artifactFolder)
      postMessage(
        {
          type: 'state',
          sourceHtml: currentDocument.getText(),
          sourceKind: this.sourceKind,
          theme: this.currentTheme(),
          interactions,
        },
        'state',
      )
    }

    const postUpdate = async (): Promise<void> => {
      const interactions = await this.readInteractions(artifactFolder)
      postMessage(
        {
          type: 'update',
          sourceHtml: currentDocument.getText(),
          sourceKind: this.sourceKind,
          interactions,
        },
        'update',
      )
    }

    const postTheme = (): void => {
      postMessage({ type: 'theme', theme: this.currentTheme() }, 'theme')
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
            // Reject absolute paths and any traversal; only open files within the artifact folder.
            if (typeof rel !== 'string' || rel.length === 0 || rel.startsWith('/') || rel.includes('..')) {
              return
            }
            const target = vscode.Uri.joinPath(artifactFolder, rel)
            const baseFs = artifactFolder.fsPath.endsWith('/')
              ? artifactFolder.fsPath
              : `${artifactFolder.fsPath}/`
            if (target.fsPath !== artifactFolder.fsPath && !target.fsPath.startsWith(baseFs)) {
              return
            }
            void vscode.commands.executeCommand('vscode.open', target)
            return
          }
          case 'storeInteraction':
            await this.handleStoreInteraction(artifactFolder, message)
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
      receiveDisposable.dispose()
      viewStateDisposable.dispose()
    }

    webviewPanel.onDidDispose(disposeAll)

    await postState()
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
  ): Promise<void> {
    const filename =
      typeof message.filename === 'string' && message.filename.length > 0
        ? message.filename
        : 'interactions.json'
    if (!INTERACTIONS_FILE_RE.test(filename)) {
      console.warn(`[tressoir-notebook] Rejected storeInteraction for invalid filename: ${filename}`)
      return
    }
    if (
      typeof message.key !== 'string' ||
      message.key.length === 0 ||
      message.key.length > MAX_INTERACTION_KEY_LEN
    ) {
      return
    }
    const target = vscode.Uri.joinPath(artifactFolder, filename)
    const chainKey = target.fsPath
    const previous = this.interactionWriteChains.get(chainKey) ?? Promise.resolve()
    const next = previous.then(() =>
      this.mergeAndWriteInteraction(target, message.key, message.value),
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
      if (type !== vscode.FileType.File || !INTERACTIONS_FILE_RE.test(name)) {
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

  private currentTheme(): NotebookThemeState {
    return notebookThemeFromColorKind(vscode.window.activeColorTheme.kind)
  }

  // Committed extension-core UMD runtime load order for the md projection (mirrors the SHIM
  // preview_md.py + assets/core/README.md): the remark/yaml/prism/CodeMirror stack, the `simple`
  // addon (rust mode needs defineSimpleMode) + placeholder addon, then CM modes in dependency
  // order (meta before markdown), then the TressoirMd projection runtime LAST. These are the
  // always-needed shared libs shipped INSIDE the extension under dist/assets/core (NOT a
  // per-artifact vendor download). All eval-free classic scripts loaded under the
  // `${webview.cspSource}` host-source (no nonce needed for src scripts).
  private static readonly MD_CORE_PREFIX: readonly string[] = [
    'core/tressoir-remark.umd.js',
    'core/js-yaml.min.js',
    'core/prism.js',
    'core/codemirror.js',
    'core/cm-addon/simple.js',
    'core/cm-addon/placeholder.js',
  ]

  // CodeMirror language modes are injected DYNAMICALLY from core/cm-mode/*.js so adding a
  // language is a SINGLE knob: drop the CodeMirror mode + Prism component into assets/core/ per
  // assets/core/README.md and rebuild — no bridge edit needed. meta.js MUST load first (it
  // provides the alias/extension resolution used by markdown fenced highlighting); order among the
  // remaining modes is irrelevant because they are resolved lazily at tokenize time.
  private cmModeScripts(assetsDir: vscode.Uri): string[] {
    try {
      const dir = vscode.Uri.joinPath(assetsDir, 'core', 'cm-mode').fsPath
      return fs
        .readdirSync(dir)
        .filter((f) => f.endsWith('.js'))
        .sort((a, b) => (a === 'meta.js' ? -1 : b === 'meta.js' ? 1 : a.localeCompare(b)))
        .map((f) => `core/cm-mode/${f}`)
    } catch {
      return []
    }
  }

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
    // Locked CSS first, then author-declared `links:` stylesheets (so an author can layer on top).
    const styleLinks = [
      ...['core/codemirror.css', 'artifact.css']
        .filter(exists)
        .map((rel) => `<link rel="stylesheet" href="${assetUri(rel)}" />`),
      ...userLinks.styleTags,
    ].join('\n    ')
    const orderedScripts = [
      ...TressoirNotebookEditorProvider.MD_CORE_PREFIX,
      ...this.cmModeScripts(assetsDir),
    ]
    // Core libs first, then author-declared `links:` scripts (local or vendor-cached remote),
    // then the projection runtime LAST so it can consume them.
    const coreTags = orderedScripts
      .filter(exists)
      .map((rel) => `<script src="${assetUri(rel)}"></script>`)
    const runtimeTags = ['tressoir-md.js']
      .filter(exists)
      .map((rel) => `<script src="${assetUri(rel)}"></script>`)
    const scriptTags = [...coreTags, ...userLinks.scriptTags, ...runtimeTags].join('\n    ')
    return { styles: styleLinks, scripts: scriptTags }
  }

  private buildWebviewHtml(
    webview: vscode.Webview,
    artifactFolder: vscode.Uri,
    userLinks: { styleTags: string[]; scriptTags: string[] } = { styleTags: [], scriptTags: [] },
    sourceName = '',
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
    // ${webview.cspSource} host-source. No 'unsafe-inline'/'unsafe-eval'/'strict-dynamic'.
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
      `script-src ${webview.cspSource} 'nonce-${nonce}'`,
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
    data-source-name="${sourceName.replace(/"/g, '&quot;')}"
  >
    <div id="app"></div>
    ${mdAssets.scripts}
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`
  }
}

// Derive a stable per-source key namespace from the document path: the basename with the
// `.tressoir.md` / `.tressoir.html` suffix stripped (e.g. `PLAN.tressoir.md` -> `PLAN`). Used so
// projected interaction keys (e.g. the free-form feedback box) don't collide across sibling
// artifacts that share one folder's interactions.json.
function sourceNameFromPath(p: string): string {
  const base = (p.split(/[\\/]/).pop() ?? '').trim()
  return base.replace(/\.tressoir\.(md|html)$/i, '')
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
