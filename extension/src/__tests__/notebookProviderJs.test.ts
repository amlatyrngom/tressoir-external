import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as vscode from 'vscode'
import { JSDOM } from 'jsdom'
import { ColorThemeKind } from './mocks/vscode'
import { TressoirNotebookEditorProvider, fetchRemote } from '../notebook/provider'
import { clearNotebookState } from '../notebook/state'
function createDocument(text: string, version = 1) {
  return {
    uri: { fsPath: '/tmp/notebook.tressoir.html', path: '/tmp/notebook.tressoir.html', toString: () => 'file:///tmp/notebook.tressoir.html' },
    fileName: '/tmp/notebook.tressoir.html',
    version,
    getText: () => text,
    positionAt: (offset: number) => {
      const lines = text.slice(0, offset).split('\n')
      return new vscode.Position(lines.length - 1, lines[lines.length - 1]?.length ?? 0)
    },
    isDirty: false,
  }
}

function createPanel() {
  const panel = {
    visible: true,
    webview: {
      html: '',
      options: {} as Record<string, unknown>,
      cspSource: 'https://test.csp',
      asWebviewUri: vi.fn((uri: any) => uri),
      postMessage: vi.fn(async () => true),
      onDidReceiveMessage: vi.fn(() => ({ dispose: vi.fn() })),
    },
    onDidDispose: vi.fn(() => ({ dispose: vi.fn() })),
    onDidChangeViewState: vi.fn(() => ({ dispose: vi.fn() })),
  }
  return panel
}

describe('notebook provider JS support (CSP / base / resource roots)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearNotebookState()
    ;(vscode.window as any).activeColorTheme = { kind: ColorThemeKind.Dark }
  })

  async function buildHtml(fileName = '/tmp/notebook.tressoir.html') {
    const provider = new TressoirNotebookEditorProvider({
      extensionUri: { fsPath: '/tmp/ext', path: '/tmp/ext' },
    } as unknown as vscode.ExtensionContext)
    const document = {
      ...createDocument('<tressoir-editor-cell data-tressoir-cell="a">hi</tressoir-editor-cell>'),
      fileName,
    }
    const panel = createPanel()
    await provider.resolveCustomTextEditor(
      document as unknown as vscode.TextDocument,
      panel as unknown as vscode.WebviewPanel,
    )
    return panel
  }

  it('emits a per-render nonce in the CSP and stamps it on the webview bundle script', async () => {
    const panel = await buildHtml()
    const html = panel.webview.html
    const nonceMatch = html.match(/script-src https:\/\/test\.csp 'nonce-([A-Za-z0-9]+)'/)
    expect(nonceMatch).not.toBeNull()
    const nonce = nonceMatch![1]
    // The webview's own bundle script must carry the same nonce.
    expect(html).toContain(`<script nonce="${nonce}" src=`)
    // body dataset exposes the nonce for stamping re-created inline authored scripts.
    expect(html).toContain(`data-csp-nonce="${nonce}"`)
  })

  it('uses a hardened CSP: no unsafe-eval, no strict-dynamic, with connect-src for authored fetch', async () => {
    const panel = await buildHtml()
    const html = panel.webview.html
    expect(html).not.toContain("'unsafe-eval'")
    expect(html).not.toContain("'strict-dynamic'")
    expect(html).toContain('connect-src https://test.csp')
    expect(html).toContain("default-src 'none'")
  })

  it('emits no Monaco wiring (no data-monaco-* body attributes)', async () => {
    const panel = await buildHtml()
    const html = panel.webview.html
    expect(html).not.toContain('data-monaco')
    expect(html.toLowerCase()).not.toContain('monaco')
  })

  it('injects an artifact <base> dataset with a trailing slash for relative includes', async () => {
    const panel = await buildHtml()
    const html = panel.webview.html
    const baseMatch = html.match(/data-artifact-base-uri="([^"]+)"/)
    expect(baseMatch).not.toBeNull()
    expect(baseMatch![1].endsWith('/')).toBe(true)
  })

  it('stamps a data-source-name (basename with .tressoir.* stripped) for per-file interaction-key namespacing', async () => {
    const panel = await buildHtml()
    const html = panel.webview.html
    // Document is /tmp/notebook.tressoir.html -> stem `notebook`.
    expect(html).toContain('data-source-name="notebook"')
    expect(html).toContain('data-feedback-key="notebook-free_form_feedback"')
  })

  it('encodes adversarial source names injectively before browser transport', async () => {
    const expected = new Map([
      ['/tmp/A&B.tressoir.md', 'A&B'],
      ['/tmp/A&amp;B.tressoir.md', 'A&amp;B'],
      ['/tmp/ PLAN.tressoir.md', ' PLAN'],
      ['/tmp/A\\B.tressoir.md', 'A\\B'],
      ['/tmp/.tressoir.md', ''],
      ['/tmp/A\rB.tressoir.md', 'A\rB'],
      ['/tmp/A\nB.tressoir.md', 'A\nB'],
      ['/tmp/A\r\nB.tressoir.md', 'A\r\nB'],
    ])
    for (const [fileName, namespace] of expected) {
      const panel = await buildHtml(fileName)
      // Parse the actual provider-generated document: substring checks alone miss HTML's
      // CR/CRLF input normalization at the provider-to-browser boundary.
      const dom = new JSDOM(panel.webview.html)
      expect(dom.window.document.body.dataset.sourceName).toBe(namespace)
      expect(dom.window.document.body.dataset.feedbackKey).toBe(
        `${namespace}-free_form_feedback`,
      )
      dom.window.close()
    }
  })

  it('widens localResourceRoots to the artifact folder (and keeps the extension dist root)', async () => {
    const panel = await buildHtml()
    const roots = (panel.webview.options as any).localResourceRoots as any[]
    expect(Array.isArray(roots)).toBe(true)
    expect(roots.length).toBe(2)
    const paths = roots.map((r) => r.fsPath || r.path)
    expect(paths.some((p: string) => p.includes('/tmp/ext') && p.includes('dist'))).toBe(true)
    // Artifact folder is the document's parent directory.
    expect(paths.some((p: string) => p.includes('/tmp/notebook.tressoir.html/..') || p === '/tmp')).toBe(true)
  })
})

describe('notebook provider openArtifactFile (contained sibling open)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearNotebookState()
    ;(vscode.window as any).activeColorTheme = { kind: ColorThemeKind.Dark }
  })

  async function resolveAndGetHandler() {
    const provider = new TressoirNotebookEditorProvider({
      extensionUri: { fsPath: '/tmp/ext', path: '/tmp/ext' },
    } as unknown as vscode.ExtensionContext)
    const document = createDocument('<tressoir-editor-cell data-tressoir-cell="a">hi</tressoir-editor-cell>')
    const panel = createPanel()
    await provider.resolveCustomTextEditor(
      document as unknown as vscode.TextDocument,
      panel as unknown as vscode.WebviewPanel,
    )
    const handler = (panel.webview.onDidReceiveMessage as any).mock.calls[0][0]
    // Ignore any executeCommand calls made during resolve.
    ;(vscode.commands.executeCommand as any).mockClear()
    return { handler }
  }

  it('opens a sibling file inside the artifact folder via vscode.open', async () => {
    const { handler } = await resolveAndGetHandler()
    await handler({ type: 'openArtifactFile', path: 'PLAN.md' })
    expect(vscode.commands.executeCommand).toHaveBeenCalledTimes(1)
    const [cmd, uri] = (vscode.commands.executeCommand as any).mock.calls[0]
    expect(cmd).toBe('vscode.open')
    expect((uri as any).fsPath).toContain('PLAN.md')
  })

  it('rejects path traversal, absolute paths, and empty paths', async () => {
    const { handler } = await resolveAndGetHandler()
    await handler({ type: 'openArtifactFile', path: '../secret.txt' })
    await handler({ type: 'openArtifactFile', path: 'a/../../escape.txt' })
    await handler({ type: 'openArtifactFile', path: '/etc/passwd' })
    await handler({ type: 'openArtifactFile', path: '' })
    expect(vscode.commands.executeCommand).not.toHaveBeenCalled()
  })
})

function makeProvider() {
  return new TressoirNotebookEditorProvider({
    extensionUri: { fsPath: '/tmp/ext', path: '/tmp/ext' },
  } as unknown as vscode.ExtensionContext)
}

describe('notebook provider front-matter `links:` parsing', () => {
  it('parses a YAML block list keeping local + remote entries in order', () => {
    const md = [
      '---',
      'title: Demo',
      'links:',
      '  - https://cdn.example.com/d3.js',
      '  - ./local/theme.css',
      '  - ./vendor/util.js',
      'state: planning',
      '---',
      '# Body',
    ].join('\n')
    const entries = (makeProvider() as any).parseFrontmatterLinks(md)
    expect(entries).toEqual([
      'https://cdn.example.com/d3.js',
      './local/theme.css',
      './vendor/util.js',
    ])
  })

  it('parses an inline flow list with quotes', () => {
    const md = '---\nlinks: ["https://a.example/x.js", \'./y.css\']\n---\nhi'
    const entries = (makeProvider() as any).parseFrontmatterLinks(md)
    expect(entries).toEqual(['https://a.example/x.js', './y.css'])
  })

  it('returns [] when there is no front-matter or no links key', () => {
    expect((makeProvider() as any).parseFrontmatterLinks('# No front-matter')).toEqual([])
    expect((makeProvider() as any).parseFrontmatterLinks('---\ntitle: x\n---\nbody')).toEqual([])
  })

  it('ends the links block at a sibling key (does not swallow later list items)', () => {
    const md = '---\nlinks:\n  - https://a.example/x.js\nother:\n  - not-a-link\n---\nbody'
    const entries = (makeProvider() as any).parseFrontmatterLinks(md)
    expect(entries).toEqual(['https://a.example/x.js'])
  })
})

describe('notebook provider cacheFilenameForUrl', () => {
  it('is stable, .js-suffixed, fs-safe, and collision-resistant', () => {
    const p = makeProvider() as any
    const a = p.cacheFilenameForUrl('https://cdn.example.com/path/d3.min.js?v=7')
    expect(a).toMatch(/^[0-9a-f]{10}-d3\.min\.js$/)
    // Stable across calls.
    expect(p.cacheFilenameForUrl('https://cdn.example.com/path/d3.min.js?v=7')).toBe(a)
    // Different URL -> different hash prefix (no collision).
    const b = p.cacheFilenameForUrl('https://cdn.example.com/path/d3.min.js?v=8')
    expect(b).not.toBe(a)
    // A URL without a .js basename still gets a .js suffix and sanitized base.
    expect(p.cacheFilenameForUrl('https://cdn.example.com/lib/')).toMatch(/^[0-9a-f]{10}-lib\.js$/)
  })
})

describe('fetchRemote (extension-host provisioning fetch)', () => {
  it('rejects non-http(s) targets without attempting a network call', async () => {
    await expect(fetchRemote('file:///etc/passwd')).rejects.toThrow(/non-http\(s\)/)
    await expect(fetchRemote('ftp://example.com/x.js')).rejects.toThrow(/non-http\(s\)/)
  })

  it('rejects a malformed URL', async () => {
    await expect(fetchRemote('not a url')).rejects.toThrow(/invalid URL/)
  })
})
