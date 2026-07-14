// Tressoir notebook webview entrypoint.
//
// Authored `.tressoir.html` content is rendered DIRECTLY into the main VS Code webview
// document (not a shadow root or child iframe). This lets authored relative includes use
// the artifact-scoped webview resource roots and lets the extension control script order.
//
// The renderer is source-editor-agnostic: it does not inject or mount Monaco. Authored
// pages render arbitrary HTML/CSS/JS; a rich text field is just authored content (e.g. a
// vendored CodeMirror field) that persists like any widget via `storeInteraction`.
//
// Consequences handled here:
//   - authored <script> nodes are re-created so they execute (recreateScripts), with the
//     per-render CSP nonce stamped on inline scripts;
//   - a <base href> resolves authored relative URLs/`fetch` to the artifact folder;
//   - any authored-content change re-renders into a fresh realm (the provider resets
//     webview.html); the reader's scroll position is restored from webview state.
import './styles.css'
import {
  notebookPaletteForTheme,
  type NotebookThemePalette,
  type NotebookThemeState,
} from '../theme'
import morphdom from 'morphdom'
import { ensureArtifactBaseHref, recreateScripts } from './scriptInjection'

declare function acquireVsCodeApi(): {
  postMessage(message: unknown): void
  getState(): unknown
  setState(state: unknown): void
}

type InteractionsSnapshot = Record<string, Record<string, unknown>>

type NotebookSourceKind = 'html' | 'md'

type NotebookStateMessage = {
  type: 'state'
  sourceHtml: string
  sourceKind?: NotebookSourceKind
  theme: NotebookThemeState
  interactions: InteractionsSnapshot
}

// Lightweight-refresh message: morph the live preview to this HTML instead of rebuilding the
// realm, so tab/disclosure/scroll/focus and runtime-upgraded widgets survive (see provider.ts).
type NotebookUpdateMessage = {
  type: 'update'
  sourceHtml: string
  sourceKind?: NotebookSourceKind
  interactions: InteractionsSnapshot
}

// The bundled, eval-free markdown projection runtime (assets/tressoir-md.js), injected as a
// classic <script> only for the `md` source kind. Projects a `.tressoir.md` source into the
// LOCKED user-artifact HTML, which then flows through the SAME morph/recreateScripts pipeline.
type TressoirMdRuntime = { project(markdown: string): string }
declare global {
  interface Window {
    TressoirMd?: TressoirMdRuntime
  }
}

type NotebookThemeMessage = {
  type: 'theme'
  theme: NotebookThemeState
}

type WebviewPersistedState = { scrollY?: number }

const DEFAULT_INTERACTIONS_FILE = 'interactions.json'

const vscodeApi = acquireVsCodeApi()

// Authored content is rendered into THIS realm, so authored interactions are persisted via the
// snapshot below (kept current as `state` messages arrive) and the `storeInteraction` bridge.
let currentInteractions: InteractionsSnapshot = {}
let currentTheme: NotebookThemeState = { kind: 'dark', flavor: 'mocha' }
// 'html' renders authored content verbatim (legacy); 'md' projects the markdown source first.
let currentSourceKind: NotebookSourceKind = 'html'
let previewHost: HTMLDivElement | null = null
// The authored-content container. Kept across `update` messages so it can be DOM-morphed in
// place (lightweight refresh) rather than rebuilt; null until the first full render.
let previewEl: HTMLDivElement | null = null
let renderGeneration = 0
let scrollPersistTimer: number | null = null

// Best-effort host hardening (NOT a security boundary): authored scripts share this realm, so
// neutralize the bridge-handle factory before any authored script runs. The captured
// `vscodeApi` lives in this module closure, not on `window`.
try {
  Object.defineProperty(window, 'acquireVsCodeApi', {
    configurable: false,
    writable: false,
    value: () => {
      throw new Error('acquireVsCodeApi is not available to authored notebook scripts.')
    },
  })
} catch {
  // Some environments make the global non-configurable; ignore.
}

function resolveInteractionsFile(filename?: unknown): string {
  return typeof filename === 'string' && filename.length > 0 ? filename : DEFAULT_INTERACTIONS_FILE
}

// Narrow, deliberate capabilities exposed to authored content (trusted-artifact model):
//   - openFile: open a sibling file INSIDE the artifact folder in the editor;
//   - storeInteraction / getInteraction: persist + read widget state in a contained JSON file.
// These cannot read/write the document content or reach the rest of the vscode API. The
// provider validates containment + filename + size for every write.
try {
  Object.defineProperty(window, 'tressoirNotebook', {
    configurable: false,
    enumerable: true,
    writable: false,
    value: Object.freeze({
      openFile(relativePath: string): void {
        if (typeof relativePath !== 'string' || relativePath.length === 0) {
          return
        }
        vscodeApi.postMessage({ type: 'openArtifactFile', path: relativePath })
      },
      storeInteraction(key: string, value: unknown, filename?: string): void {
        if (typeof key !== 'string' || key.length === 0) {
          return
        }
        const file = resolveInteractionsFile(filename)
        // Optimistic local update so a subsequent getInteraction reflects it immediately.
        const bucket = currentInteractions[file] ?? (currentInteractions[file] = {})
        bucket[key] = value
        vscodeApi.postMessage({ type: 'storeInteraction', key, value, filename: file })
      },
      getInteraction(key: string, filename?: string): unknown {
        if (typeof key !== 'string' || key.length === 0) {
          return undefined
        }
        return currentInteractions[resolveInteractionsFile(filename)]?.[key]
      },
    }),
  })
} catch {
  // Ignore if the global is locked down by the environment.
}

const app = document.getElementById('app')

if (!app) {
  throw new Error('Notebook webview root was not found.')
}

const appRoot: HTMLElement = app
const artifactBaseUri = readBodyDatasetValue('artifactBaseUri')
const cspNonce = readBodyDatasetValue('cspNonce')

function readBodyDatasetValue(name: 'artifactBaseUri' | 'cspNonce'): string {
  const value = document.body.dataset[name]
  if (!value) {
    throw new Error(`Notebook webview is missing body dataset value \`${name}\`.`)
  }
  return value
}

function readPersistedState(): WebviewPersistedState {
  const state = vscodeApi.getState()
  return state && typeof state === 'object' ? (state as WebviewPersistedState) : {}
}

// Persist the scroll offset in webview STATE (not module memory): a re-render resets
// webview.html, spawning a fresh realm where module memory is gone — but webview state
// survives the reset, so the reload can restore the reader's position.
function persistScrollSoon(): void {
  if (scrollPersistTimer != null) {
    window.clearTimeout(scrollPersistTimer)
  }
  scrollPersistTimer = window.setTimeout(() => {
    scrollPersistTimer = null
    vscodeApi.setState({ ...readPersistedState(), scrollY: window.scrollY })
  }, 150)
}

function restoreSavedScroll(): void {
  const saved = readPersistedState().scrollY
  if (typeof saved === 'number' && saved > 0) {
    window.requestAnimationFrame(() => {
      window.scrollTo(0, saved)
    })
  }
}

function applyCssVariables(target: HTMLElement, palette: NotebookThemePalette): void {
  target.style.setProperty('--nb-bg', palette.bg)
  target.style.setProperty('--nb-surface', palette.surface)
  target.style.setProperty('--nb-surface-alt', palette.surfaceAlt)
  target.style.setProperty('--nb-border', palette.border)
  target.style.setProperty('--nb-text', palette.text)
  target.style.setProperty('--nb-muted', palette.muted)
  target.style.setProperty('--nb-accent', palette.accent)
  target.style.setProperty('--nb-selection', palette.selection)
}

function applyTheme(theme: NotebookThemeState): void {
  currentTheme = theme
  const palette = notebookPaletteForTheme(theme)
  document.documentElement.dataset.themeKind = theme.kind
  document.documentElement.style.colorScheme = theme.kind
  applyCssVariables(document.documentElement, palette)
  if (previewHost) {
    applyCssVariables(previewHost, palette)
  }
}

function renderLoadingState(): void {
  appRoot.replaceChildren()
  const shell = document.createElement('div')
  shell.className = 'notebook-shell'
  appRoot.appendChild(shell)
}

// For the `md` source kind, project the markdown source into the LOCKED user-artifact HTML using
// the bundled eval-free TressoirMd runtime BEFORE it enters the morph/recreateScripts pipeline.
// The `html` kind returns authored HTML verbatim (unchanged legacy path). On any failure it
// degrades to the raw source rather than throwing, so a render still happens.
function projectSource(sourceHtml: string): string {
  if (currentSourceKind !== 'md') {
    return sourceHtml
  }
  const runtime = window.TressoirMd
  if (!runtime || typeof runtime.project !== 'function') {
    console.error('[tressoir-notebook] TressoirMd runtime missing for a .tressoir.md projection.')
    return sourceHtml
  }
  try {
    return runtime.project(sourceHtml)
  } catch (error) {
    console.error('[tressoir-notebook] Failed to project .tressoir.md source.', error)
    return sourceHtml
  }
}

// Build the authored-preview DOM in the MAIN document and execute authored scripts in order.
async function buildPreviewAndRunScripts(state: NotebookStateMessage): Promise<void> {
  appRoot.replaceChildren()

  const shell = document.createElement('div')
  shell.className = 'notebook-shell'

  const host = document.createElement('div')
  host.className = 'notebook-preview-host'
  applyCssVariables(host, notebookPaletteForTheme(currentTheme))
  shell.appendChild(host)
  previewHost = host

  // Authored content is injected into the main document (no shadow root) so authored CSS is
  // page-global and authored scripts can run.
  const preview = document.createElement('div')
  preview.className = 'tressoir-preview'
  preview.innerHTML = projectSource(state.sourceHtml)
  host.appendChild(preview)
  appRoot.appendChild(shell)
  previewEl = preview

  // Execute authored GLOBAL + relative <script> nodes in document order; external includes are
  // awaited per-node so authored globals settle deterministically.
  await recreateScripts(preview, cspNonce)
  // Notify authored content that a render completed so it can (re-)apply idempotent runtime
  // upgrades (syntax highlighting, restoring persisted picks). Fired on full renders AND morphs.
  dispatchRenderEvent('full')
}

// Tell authored content a render finished. Authored scripts that build runtime UI from the
// document (e.g. syntax-highlighting, re-applying persisted decision picks) should listen for
// `tressoir:render` and re-run idempotently — on a morph their one-time init script does NOT
// run again, so this event is the hook to refresh newly morphed-in nodes.
function dispatchRenderEvent(phase: 'full' | 'morph'): void {
  document.dispatchEvent(new CustomEvent('tressoir:render', { detail: { phase } }))
}

// Preserve runtime UI-state CSS classes (e.g. an open disclosure, the selected tab card) that
// the authored source never carries, so a morph does not collapse them back to defaults. The
// author opts in per element via `data-morph-keep-class="open selected"`.
function preserveKeepClasses(fromEl: Element, toEl: Element): void {
  const keep = fromEl.getAttribute('data-morph-keep-class')
  if (!keep) {
    return
  }
  for (const cls of keep.split(/\s+/)) {
    if (cls && fromEl.classList.contains(cls)) {
      toEl.classList.add(cls)
    }
  }
}

// Preserve the LIVE interactive state of form controls (which radio/checkbox is checked, what
// the reader typed) over the authored default, so a morph never clobbers in-progress input or
// the active CSS-radio tab. The authored value/checked is treated as a default, not an override.
function preserveFormState(fromEl: Element, toEl: Element): void {
  if (fromEl instanceof HTMLInputElement && toEl instanceof HTMLInputElement) {
    if (fromEl.type === 'radio' || fromEl.type === 'checkbox') {
      toEl.checked = fromEl.checked
      if (fromEl.checked) {
        toEl.setAttribute('checked', '')
      } else {
        toEl.removeAttribute('checked')
      }
    } else {
      toEl.setAttribute('value', fromEl.value)
      toEl.value = fromEl.value
    }
    return
  }
  if (fromEl instanceof HTMLTextAreaElement && toEl instanceof HTMLTextAreaElement) {
    toEl.value = fromEl.value
    toEl.textContent = fromEl.value
    return
  }
  if (fromEl instanceof HTMLSelectElement && toEl instanceof HTMLSelectElement) {
    toEl.value = fromEl.value
  }
}

// Lightweight refresh: morph the live preview DOM to match the new authored HTML. Preserves
// runtime state the authored source cannot express: `data-morph-skip` subtrees (a mounted
// CodeMirror field, pure user-input boxes) are left entirely alone; running authored <script>
// nodes are never disturbed (genuinely NEW scripts run afterwards); form-control live state and
// opted-in UI classes are carried over. Then re-run new scripts and fire the render event.
async function morphPreview(message: NotebookUpdateMessage): Promise<void> {
  if (!previewEl) {
    return
  }
  const target = document.createElement('div')
  target.className = 'tressoir-preview'
  target.innerHTML = projectSource(message.sourceHtml)
  morphdom(previewEl, target, {
    onBeforeElUpdated(fromEl, toEl) {
      // Never re-morph (or re-run) an already-executing authored script.
      if (fromEl.tagName === 'SCRIPT') {
        return false
      }
      // Author-marked runtime-upgraded subtree (CodeMirror, etc.) / pure user-input box.
      if (fromEl.hasAttribute('data-morph-skip')) {
        return false
      }
      preserveFormState(fromEl, toEl)
      preserveKeepClasses(fromEl, toEl)
      return true
    },
    onBeforeNodeDiscarded(node) {
      // Keep author-protected subtrees even if they are absent from the new source position.
      if (node.nodeType === 1 && (node as Element).hasAttribute('data-morph-skip')) {
        return false
      }
      return true
    },
  })
  // Execute only the genuinely-new authored scripts (recreateScripts skips already-run ones).
  await recreateScripts(previewEl, cspNonce)
  dispatchRenderEvent('morph')
}

async function renderNotebook(state: NotebookStateMessage): Promise<void> {
  const generation = ++renderGeneration
  previewHost = null
  renderLoadingState()

  await buildPreviewAndRunScripts(state)
  if (generation !== renderGeneration) {
    return
  }

  // Fresh realm after a webview.html reset (re-render / reload): the in-memory scroll is gone,
  // so restore from persisted webview state.
  restoreSavedScroll()
}

function handleStateMessage(message: NotebookStateMessage): void {
  currentInteractions = message.interactions ?? {}
  currentSourceKind = message.sourceKind ?? 'html'
  applyTheme(message.theme)
  void renderNotebook(message)
}

function handleUpdateMessage(message: NotebookUpdateMessage): void {
  currentInteractions = message.interactions ?? {}
  currentSourceKind = message.sourceKind ?? currentSourceKind
  if (!previewEl) {
    // An update arrived before the first full render established a realm: fall back to a full
    // build so the preview is initialized correctly.
    void renderNotebook({
      type: 'state',
      sourceHtml: message.sourceHtml,
      sourceKind: currentSourceKind,
      theme: currentTheme,
      interactions: currentInteractions,
    })
    return
  }
  void morphPreview(message)
}

ensureArtifactBaseHref(artifactBaseUri)

window.addEventListener(
  'message',
  (event: MessageEvent<NotebookStateMessage | NotebookUpdateMessage | NotebookThemeMessage>) => {
    const message = event.data
    if (!message || typeof message !== 'object' || !('type' in message)) {
      return
    }
    if (message.type === 'state') {
      handleStateMessage(message)
      return
    }
    if (message.type === 'update') {
      handleUpdateMessage(message)
      return
    }
    if (message.type === 'theme') {
      applyTheme(message.theme)
    }
  },
)

window.addEventListener('scroll', persistScrollSoon, { passive: true })

// Report the rendered-text selection to the extension host so the chat "reference from editor"
// action can grab the user's highlighted text from this custom editor (parity with normal text
// editors, which expose `vscode.window.activeTextEditor.selection`). The provider stores the
// latest non-empty selection as the notebook selection; an empty/collapsed selection clears it.
// Debounced to avoid spamming during drag-select.
let selectionReportTimer: ReturnType<typeof setTimeout> | undefined
function reportSelectionSoon(): void {
  if (selectionReportTimer) clearTimeout(selectionReportTimer)
  selectionReportTimer = setTimeout(() => {
    const selectedText = window.getSelection?.()?.toString() ?? ''
    vscodeApi.postMessage({ type: 'selectionChanged', selectedText })
  }, 150)
}
document.addEventListener('selectionchange', reportSelectionSoon)

renderLoadingState()
applyTheme(currentTheme)
vscodeApi.postMessage({ type: 'ready' })
