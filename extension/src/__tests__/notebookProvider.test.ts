import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as vscode from 'vscode'
import {
  __fireDidChangeActiveColorTheme,
  __fireDidChangeTextDocument,
  __readFile,
  __resetFs,
  __seedFile,
  ColorThemeKind,
} from './mocks/vscode'
import { TressoirNotebookEditorProvider } from '../notebook/provider'
import { clearNotebookState, getNotebookSelection } from '../notebook/state'

// The document lives at DOC_FS; the artifact folder is its parent via `Uri.joinPath(uri, '..')`.
// The vscode mock's `joinPath` concatenates without normalizing `..`, so the folder path keeps
// the literal `/..` segment — tests seed/read interaction files against that same path.
const DOC_FS = '/tmp/notebook.tressoir.html'
const FOLDER_FS = `${DOC_FS}/..`

function folderFile(name: string): string {
  return `${FOLDER_FS}/${name}`
}

function createDocument(text: string, version = 1, fileName = DOC_FS) {
  return {
    uri: {
      fsPath: DOC_FS,
      path: DOC_FS,
      toString: () => `file://${DOC_FS}`,
    },
    fileName,
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
  let messageHandler: ((message: unknown) => void | Promise<void>) | null = null
  let disposeHandler: (() => void) | null = null
  let viewStateHandler: (() => void) | null = null

  const panel = {
    visible: true,
    webview: {
      html: '',
      options: {} as Record<string, unknown>,
      cspSource: 'https://test.csp',
      asWebviewUri: vi.fn((uri: unknown) => uri),
      postMessage: vi.fn(async (_message: unknown) => true),
      onDidReceiveMessage: vi.fn((handler: (message: unknown) => void | Promise<void>) => {
        messageHandler = handler
        return { dispose: vi.fn() }
      }),
    },
    onDidDispose: vi.fn((handler: () => void) => {
      disposeHandler = handler
      return { dispose: vi.fn() }
    }),
    onDidChangeViewState: vi.fn((handler: () => void) => {
      viewStateHandler = handler
      return { dispose: vi.fn() }
    }),
    __emitMessage: async (message: unknown) => {
      await messageHandler?.(message)
    },
    __dispose: () => {
      disposeHandler?.()
    },
    __changeViewState: () => {
      viewStateHandler?.()
    },
  }

  return panel
}

function makeProvider(sourceKind: 'html' | 'md' = 'html') {
  return new TressoirNotebookEditorProvider({
    extensionUri: { fsPath: '/tmp/ext', path: '/tmp/ext' },
  } as unknown as vscode.ExtensionContext, sourceKind)
}

async function resolve(provider: ReturnType<typeof makeProvider>, document: ReturnType<typeof createDocument>) {
  const panel = createPanel()
  await provider.resolveCustomTextEditor(
    document as unknown as vscode.TextDocument,
    panel as unknown as vscode.WebviewPanel,
  )
  return panel
}

describe('notebook provider (editor-agnostic)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearNotebookState()
    __resetFs()
    ;(vscode.window as any).activeColorTheme = { kind: ColorThemeKind.Dark }
  })

  afterEach(() => {
    __resetFs()
  })

  it('posts initial state with sourceHtml, theme, and the interactions snapshot', async () => {
    __seedFile(folderFile('interactions.json'), JSON.stringify({ greeting: 'hi' }))
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    expect(panel.webview.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'state',
        sourceHtml: '<h1>Plan</h1>',
        theme: { kind: 'dark', flavor: 'mocha' },
        interactions: { 'interactions.json': { greeting: 'hi' } },
      }),
    )
  })

  it('merges multiple interactions.*.json files into the snapshot', async () => {
    __seedFile(folderFile('interactions.json'), JSON.stringify({ a: 1 }))
    __seedFile(folderFile('interactions.notes.json'), JSON.stringify({ b: 2 }))
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    expect(panel.webview.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'state',
        interactions: {
          'interactions.json': { a: 1 },
          'interactions.notes.json': { b: 2 },
        },
      }),
    )
  })

  it('gives stale Markdown runtimes only the current source feedback through the legacy key', async () => {
    __seedFile(
      folderFile('interactions.json'),
      JSON.stringify({
        free_form_feedback: 'ambiguous old shared text',
        'PLAN-free_form_feedback': 'plan only',
        'RESEARCH-free_form_feedback': 'research only',
        explicit_input: 'kept',
      }),
    )

    const plan = await resolve(
      makeProvider('md'),
      createDocument('# Plan', 1, '/tmp/PLAN.tressoir.md'),
    )
    const research = await resolve(
      makeProvider('md'),
      createDocument('# Research', 1, '/tmp/RESEARCH.tressoir.md'),
    )
    const newArtifact = await resolve(
      makeProvider('md'),
      createDocument('# New', 1, '/tmp/NEW.tressoir.md'),
    )

    const planState = vi.mocked(plan.webview.postMessage).mock.calls.at(-1)?.[0] as any
    const researchState = vi.mocked(research.webview.postMessage).mock.calls.at(-1)?.[0] as any
    const newState = vi.mocked(newArtifact.webview.postMessage).mock.calls.at(-1)?.[0] as any

    expect(planState.interactions['interactions.json']).toEqual({
      free_form_feedback: 'plan only',
      'PLAN-free_form_feedback': 'plan only',
      'RESEARCH-free_form_feedback': 'research only',
      explicit_input: 'kept',
    })
    expect(researchState.interactions['interactions.json']).toEqual({
      free_form_feedback: 'research only',
      'PLAN-free_form_feedback': 'plan only',
      'RESEARCH-free_form_feedback': 'research only',
      explicit_input: 'kept',
    })
    // An artifact without a scoped value must start empty in an old runtime rather than
    // inheriting the irrecoverably ambiguous shared value.
    expect(newState.interactions['interactions.json']).toEqual({
      'PLAN-free_form_feedback': 'plan only',
      'RESEARCH-free_form_feedback': 'research only',
      explicit_input: 'kept',
    })
  })

  it('keeps adversarial sibling basenames in distinct feedback namespaces', async () => {
    __seedFile(
      folderFile('interactions.json'),
      JSON.stringify({
        'A&B-free_form_feedback': 'literal ampersand',
        'A&amp;B-free_form_feedback': 'entity spelling',
        ' PLAN-free_form_feedback': 'leading space',
        'PLAN-free_form_feedback': 'plain plan',
        'A\\B-free_form_feedback': 'backslash',
        'B-free_form_feedback': 'plain b',
        '-free_form_feedback': 'empty stem',
        'A\rB-free_form_feedback': 'carriage return',
        'A\nB-free_form_feedback': 'line feed',
        'A\r\nB-free_form_feedback': 'carriage return and line feed',
        free_form_feedback: 'ambiguous legacy text',
      }),
    )

    const cases = [
      ['/tmp/A&B.tressoir.md', 'literal ampersand'],
      ['/tmp/A&amp;B.tressoir.md', 'entity spelling'],
      ['/tmp/ PLAN.tressoir.md', 'leading space'],
      ['/tmp/PLAN.tressoir.md', 'plain plan'],
      ['/tmp/A\\B.tressoir.md', 'backslash'],
      ['/tmp/B.tressoir.md', 'plain b'],
      ['/tmp/.tressoir.md', 'empty stem'],
      ['/tmp/A\rB.tressoir.md', 'carriage return'],
      ['/tmp/A\nB.tressoir.md', 'line feed'],
      ['/tmp/A\r\nB.tressoir.md', 'carriage return and line feed'],
    ] as const
    for (const [fileName, expected] of cases) {
      const panel = await resolve(makeProvider('md'), createDocument('# Artifact', 1, fileName))
      const state = vi.mocked(panel.webview.postMessage).mock.calls.at(-1)?.[0] as any
      expect(state.interactions['interactions.json'].free_form_feedback).toBe(expected)
    }
  })

  it('reacts to theme changes by posting a theme message', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    __fireDidChangeActiveColorTheme({ kind: ColorThemeKind.Light })

    expect(panel.webview.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'theme',
        theme: { kind: 'light', flavor: 'latte' },
      }),
    )
  })

  it('posts a lightweight-refresh update (keeping the realm) on external document changes', async () => {
    __seedFile(folderFile('interactions.json'), JSON.stringify({ k: 'v' }))
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))
    vi.mocked(panel.webview.postMessage).mockClear()
    const before = panel.webview.html

    __fireDidChangeTextDocument({ document: createDocument('<h1>Changed</h1>', 2) })
    // postUpdate is async (it reads the interactions snapshot); let the microtasks settle.
    await new Promise((r) => setTimeout(r, 0))

    // The realm is KEPT alive (webview.html is not reset). Instead an `update` message carries
    // the new authored HTML + the interactions snapshot so the webview DOM-morphs in place,
    // preserving the reader's tab / open disclosures / scroll / focus.
    expect(panel.webview.html).toBe(before)
    expect(panel.webview.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'update',
        sourceHtml: '<h1>Changed</h1>',
        interactions: { 'interactions.json': { k: 'v' } },
      }),
    )
  })

  it('ignores empty document change batches from save or dirty-state transitions', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))
    const before = panel.webview.html

    __fireDidChangeTextDocument({
      document: createDocument('<h1>Plan</h1>', 2),
      contentChanges: [],
    })

    expect(panel.webview.html).toBe(before)
  })

  it('tracks notebook selection text for bridge fallback (plumbing kept)', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({
      type: 'selectionChanged',
      cellId: 'a',
      selectedText: 'picked text',
    })

    expect(getNotebookSelection()).toEqual({
      path: DOC_FS,
      text: 'picked text',
    })
  })

  it('clears notebook selection when the webview reports an empty selection', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({ type: 'selectionChanged', cellId: 'a', selectedText: 'picked' })
    await panel.__emitMessage({ type: 'selectionChanged', cellId: 'a', selectedText: '' })

    expect(getNotebookSelection()).toBeNull()
  })

  it('does not block editor resolution on pending webview postMessage delivery', async () => {
    const provider = makeProvider()
    const document = createDocument('<h1>Plan</h1>')
    const panel = createPanel()
    vi.mocked(panel.webview.postMessage).mockImplementation(
      () => new Promise<boolean>(() => {}),
    )

    const result = await Promise.race([
      provider
        .resolveCustomTextEditor(
          document as unknown as vscode.TextDocument,
          panel as unknown as vscode.WebviewPanel,
        )
        .then(() => 'resolved'),
      new Promise<string>((resolve) => {
        setTimeout(() => resolve('timed_out'), 50)
      }),
    ])

    expect(result).toBe('resolved')
  })
})

describe('notebook provider storeInteraction (contained disk-write boundary)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearNotebookState()
    __resetFs()
    ;(vscode.window as any).activeColorTheme = { kind: ColorThemeKind.Dark }
  })

  afterEach(() => {
    __resetFs()
  })

  it('persists a valid interaction, merging into the default interactions.json', async () => {
    __seedFile(folderFile('interactions.json'), JSON.stringify({ existing: 1 }))
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({ type: 'storeInteraction', key: 'feedback', value: 'hello' })

    const written = JSON.parse(__readFile(folderFile('interactions.json'))!)
    expect(written).toEqual({ existing: 1, feedback: 'hello' })
  })

  it('rewrites a stale Markdown runtime plain feedback write to the source-scoped key', async () => {
    __seedFile(
      folderFile('interactions.json'),
      JSON.stringify({ free_form_feedback: 'ambiguous old shared text', explicit_input: 'kept' }),
    )
    const panel = await resolve(
      makeProvider('md'),
      createDocument('# Plan', 1, '/tmp/PLAN.tressoir.md'),
    )

    await panel.__emitMessage({
      type: 'storeInteraction',
      key: 'free_form_feedback',
      value: 'plan only',
    })

    const written = JSON.parse(__readFile(folderFile('interactions.json'))!)
    expect(written).toEqual({
      free_form_feedback: 'ambiguous old shared text',
      'PLAN-free_form_feedback': 'plan only',
      explicit_input: 'kept',
    })
  })

  it('persists the generated feedback key for an empty or near-limit source stem', async () => {
    for (const [fileName, expectedKey] of [
      ['/tmp/.tressoir.md', '-free_form_feedback'],
      [`/tmp/${'x'.repeat(238)}.tressoir.md`, `${'x'.repeat(238)}-free_form_feedback`],
    ]) {
      __resetFs()
      const panel = await resolve(makeProvider('md'), createDocument('# Long', 1, fileName))
      await panel.__emitMessage({
        type: 'storeInteraction',
        key: expectedKey,
        value: 'saved',
      })
      expect(JSON.parse(__readFile(folderFile('interactions.json'))!)).toEqual({
        [expectedKey]: 'saved',
      })
    }
  })

  it('serializes concurrent writes to the same file without dropping updates', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    // Fire two writes WITHOUT awaiting each (simulates a debounced flush + an immediate pick
    // both targeting interactions.json). Without per-file serialization both would read the
    // same empty base and the last write would clobber the first.
    const p1 = panel.__emitMessage({ type: 'storeInteraction', key: 'a', value: 1 })
    const p2 = panel.__emitMessage({ type: 'storeInteraction', key: 'b', value: 2 })
    await Promise.all([p1, p2])

    const written = JSON.parse(__readFile(folderFile('interactions.json'))!)
    expect(written).toEqual({ a: 1, b: 2 })
  })

  it('writes to a custom contained filename (interactions.<suffix>.json)', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({
      type: 'storeInteraction',
      key: 'note',
      value: { ok: true },
      filename: 'interactions.session.json',
    })

    const written = JSON.parse(__readFile(folderFile('interactions.session.json'))!)
    expect(written).toEqual({ note: { ok: true } })
  })

  it('rejects writes to disallowed / traversal filenames', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({ type: 'storeInteraction', key: 'k', value: 'v', filename: '../evil.json' })
    await panel.__emitMessage({ type: 'storeInteraction', key: 'k', value: 'v', filename: 'evil.json' })
    await panel.__emitMessage({ type: 'storeInteraction', key: 'k', value: 'v', filename: 'interactions.json/../x.json' })
    await panel.__emitMessage({ type: 'storeInteraction', key: 'k', value: 'v', filename: 'interactions..json' })

    expect(__readFile(folderFile('../evil.json'))).toBeUndefined()
    expect(__readFile(folderFile('evil.json'))).toBeUndefined()
    expect(__readFile(folderFile('interactions.json'))).toBeUndefined()
  })

  it('rejects empty and oversized keys', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({ type: 'storeInteraction', key: '', value: 'v' })
    await panel.__emitMessage({ type: 'storeInteraction', key: 'x'.repeat(257), value: 'v' })

    expect(__readFile(folderFile('interactions.json'))).toBeUndefined()
  })

  it('rejects a value whose serialized form exceeds the size cap', async () => {
    const panel = await resolve(makeProvider(), createDocument('<h1>Plan</h1>'))

    await panel.__emitMessage({
      type: 'storeInteraction',
      key: 'big',
      value: 'A'.repeat(600 * 1024),
    })

    expect(__readFile(folderFile('interactions.json'))).toBeUndefined()
  })
})

describe('notebook provider parseFrontmatterLinks (author-declared JS/CSS libs)', () => {
  const parse = (text: string): string[] =>
    (makeProvider() as unknown as { parseFrontmatterLinks: (t: string) => string[] }).parseFrontmatterLinks(
      text,
    )

  it('parses a block list of links from front-matter', () => {
    const md = [
      '---',
      'tressoir: plan',
      'title: T',
      'links:',
      '  - https://cdn.example.com/d3.min.js',
      '  - "https://cdn.example.com/chart.js"',
      'description: d',
      '---',
      '',
      '## A',
    ].join('\n')
    expect(parse(md)).toEqual([
      'https://cdn.example.com/d3.min.js',
      'https://cdn.example.com/chart.js',
    ])
  })

  it('parses an inline flow list', () => {
    const md = ['---', 'links: [https://a.test/x.js, "https://b.test/y.js"]', '---', ''].join('\n')
    expect(parse(md)).toEqual(['https://a.test/x.js', 'https://b.test/y.js'])
  })

  it('returns [] without front-matter/links key, and KEEPS local + remote entries in order', () => {
    expect(parse('## No front-matter\n')).toEqual([])
    expect(parse('---\ntitle: T\n---\n')).toEqual([])
    const md = ['---', 'links:', '  - ./local/relative.js', '  - https://ok.test/z.js', '---'].join('\n')
    expect(parse(md)).toEqual(['./local/relative.js', 'https://ok.test/z.js'])
  })
})
