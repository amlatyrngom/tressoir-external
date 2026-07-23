// @vitest-environment jsdom
import { beforeAll, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'
import morphdom from 'morphdom'

// Proves the REAL update sequence, not just markup: the committed projector emits a stable
// `data-morph-key` on each explicit `:::input` row, and morphdom (configured exactly as
// webview/main.ts::morphPreview) matches rows by that key so typed answers follow their key
// through reorder / insert / remove / replace instead of binding by DOM position.
const assetsDir = resolve(__dirname, '../notebook/assets')
const remarkPath = resolve(assetsDir, 'core/tressoir-remark.umd.js')
const yamlPath = resolve(assetsDir, 'core/js-yaml.min.js')
const runtimePath = resolve(assetsDir, 'tressoir-md.js')
const corePresent = existsSync(remarkPath) && existsSync(yamlPath) && existsSync(runtimePath)

function loadScript(p: string): void {
  const code = readFileSync(p, 'utf8')
  // eslint-disable-next-line @typescript-eslint/no-implied-eval, no-new-func
  const fn = new Function('window', 'self', 'globalThis', 'global', code)
  fn(globalThis, globalThis, globalThis, globalThis)
}

// Faithful replica of the morphdom options in webview/main.ts::morphPreview. Keep in sync with
// that function — it is the exact identity/skip contract under test.
const morphOptions = {
  getNodeKey(node: Node) {
    const el = node.nodeType === 1 ? (node as Element) : null
    return el?.getAttribute('data-morph-key') || el?.id || undefined
  },
  onBeforeElUpdated(fromEl: HTMLElement) {
    if (fromEl.tagName === 'SCRIPT') return false
    if (fromEl.hasAttribute('data-morph-skip')) return false
    return true
  },
  onBeforeNodeDiscarded(node: Node) {
    if (node.nodeType === 1) {
      const element = node as Element
      if (
        element.hasAttribute('data-morph-skip') &&
        !element.closest('.m-input[data-morph-key]')
      ) {
        return false
      }
    }
    return true
  },
}

describe.skipIf(!corePresent)('explicit input identity during live re-projection', () => {
  let project: (markdown: string) => string

  beforeAll(() => {
    loadScript(remarkPath)
    loadScript(yamlPath)
    loadScript(runtimePath)
    const runtime = (globalThis as unknown as { TressoirMd?: { project: (m: string) => string } }).TressoirMd
    if (!runtime) {
      throw new Error('TressoirMd runtime did not load.')
    }
    project = runtime.project
  })

  const decisions = (entries: [string, string][]): string =>
    ['---', 'title: D', '---', '', '## Decisions', '']
      .concat(entries.flatMap(([k, q]) => [`:::input{key=${k}}`, q, '', '- Option', ':::', '']))
      .join('\n')

  function mount(md: string): HTMLElement {
    const host = document.createElement('div')
    host.innerHTML = project(md)
    return host
  }
  function morphTo(host: HTMLElement, md: string): void {
    const target = document.createElement('div')
    target.innerHTML = project(md)
    morphdom(host.firstElementChild as HTMLElement, target.firstElementChild as HTMLElement, morphOptions)
  }
  function box(host: HTMLElement, key: string): HTMLTextAreaElement | null {
    return host.querySelector(`textarea[data-input-key="${key}"]`)
  }

  it('keeps typed values attached to their keys after reordering', () => {
    const host = mount(decisions([['a', 'Question A?'], ['b', 'Question B?']]))
    box(host, 'a')!.value = 'answer-A'
    box(host, 'b')!.value = 'answer-B'
    morphTo(host, decisions([['b', 'Question B?'], ['a', 'Question A?']]))
    expect(box(host, 'a')!.value).toBe('answer-A')
    expect(box(host, 'b')!.value).toBe('answer-B')
  })

  it('inserts a new key blank and leaves existing answers intact', () => {
    const host = mount(decisions([['a', 'Question A?'], ['b', 'Question B?']]))
    box(host, 'a')!.value = 'answer-A'
    box(host, 'b')!.value = 'answer-B'
    morphTo(host, decisions([['a', 'Question A?'], ['c', 'Question C?'], ['b', 'Question B?']]))
    expect(box(host, 'a')!.value).toBe('answer-A')
    expect(box(host, 'b')!.value).toBe('answer-B')
    expect(box(host, 'c')!.value).toBe('')
  })

  it('removes a retired key and its skipped textarea entirely', () => {
    const host = mount(decisions([['a', 'Question A?'], ['b', 'Question B?']]))
    box(host, 'a')!.value = 'answer-A'
    box(host, 'b')!.value = 'answer-B'
    morphTo(host, decisions([['a', 'Question A?']]))
    expect(box(host, 'a')!.value).toBe('answer-A')
    expect(box(host, 'b')).toBeNull()
    expect(host.querySelector('.m-input[data-morph-key="tressoir-input:b"]')).toBeNull()
  })

  it('replaces a key without inheriting the old answer', () => {
    const host = mount(decisions([['a', 'Question A?']]))
    box(host, 'a')!.value = 'answer-A'
    morphTo(host, decisions([['d', 'Question D?']]))
    expect(box(host, 'a')).toBeNull()
    expect(box(host, 'd')!.value).toBe('')
  })

  it('still preserves an unrelated raw-HTML data-morph-skip subtree across a morph', () => {
    const host = mount(decisions([['a', 'Question A?']]))
    const widget = document.createElement('div')
    widget.id = 'runtime-widget'
    widget.setAttribute('data-morph-skip', '')
    widget.textContent = 'runtime-state'
    host.firstElementChild!.appendChild(widget)
    morphTo(host, decisions([['b', 'Question B?']]))
    const survived = host.querySelector('#runtime-widget')
    expect(survived).not.toBeNull()
    expect(survived!.textContent).toBe('runtime-state')
  })
})
