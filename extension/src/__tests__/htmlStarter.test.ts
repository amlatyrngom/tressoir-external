// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'
import { JSDOM } from 'jsdom'

const starterDir = resolve(
  __dirname,
  '../../../share/tressoir-external/skills/tressoir-artifact-html/html_artifact_template',
)
const linearAssetsDir = resolve(__dirname, '../notebook/assets/linear')
const starterHtml = readFileSync(resolve(starterDir, 'ARTIFACT.tressoir.html'), 'utf8')
const realms: JSDOM[] = []

afterEach(() => {
  while (realms.length > 0) realms.pop()?.window.close()
})

function resourceUrls(attribute: 'href' | 'src'): string[] {
  const pattern = new RegExp(`${attribute}="([^"]+)"`, 'g')
  return Array.from(starterHtml.matchAll(pattern), (match) => match[1])
}

function evaluate(dom: JSDOM, path: string): void {
  dom.window.eval(readFileSync(resolve(linearAssetsDir, path), 'utf8'))
}

function localRuntimePath(url: string): string {
  const pathname = new URL(url).pathname
  if (pathname.endsWith('/katex.min.js')) return 'vendor/katex/katex.min.js'
  if (pathname.endsWith('/auto-render.min.js')) return 'vendor/katex/auto-render.min.js'
  const prismPart = pathname.match(/\/(components|plugins)\/(.+)$/)
  if (pathname.includes('/prismjs@') && prismPart) {
    return `vendor/prism/${prismPart[1]}/${prismPart[2]}`
  }
  if (pathname.endsWith('/codemirror.min.js')) return 'vendor/codemirror/codemirror.js'
  if (pathname.endsWith('/mode/xml/xml.min.js')) return 'vendor/codemirror/mode/xml.js'
  if (pathname.endsWith('/mode/meta.min.js')) return 'vendor/codemirror/mode/meta.js'
  if (pathname.endsWith('/mode/markdown/markdown.min.js')) {
    return 'vendor/codemirror/mode/markdown.js'
  }
  if (pathname.endsWith('/tressoir-linear.js')) return 'tressoir-linear.js'
  throw new Error(`No local test fixture for remote runtime: ${url}`)
}

describe('portable linear HTML starter', () => {
  it('references only pinned HTTPS assets and keeps feedback as the final authored block', () => {
    const hrefs = resourceUrls('href')
    const assets = [...hrefs.filter((url) => url !== './SIBLING.md'), ...resourceUrls('src')]
    expect(assets.length).toBeGreaterThan(10)
    for (const asset of assets) {
      expect(asset).toMatch(/^https:\/\//)
      expect(asset).not.toMatch(/(?:@|\/)latest(?:\/|$)/)
      expect(asset).not.toMatch(/(?:@|\/)main(?:\/|$)/)
    }
    expect(hrefs.filter((url) => !url.startsWith('https://'))).toEqual(['./SIBLING.md'])
    expect(resourceUrls('src').every((url) => url.startsWith('https://'))).toBe(true)
    expect(existsSync(resolve(starterDir, 'vendor'))).toBe(false)
    expect(existsSync(resolve(starterDir, 'tressoir-linear.css'))).toBe(false)
    expect(existsSync(resolve(starterDir, 'tressoir-linear.js'))).toBe(false)

    const dom = new JSDOM(starterHtml)
    realms.push(dom)
    const main = dom.window.document.querySelector('main.tressoir-document')
    expect(main?.lastElementChild?.matches('aside.feedback-dock')).toBe(true)
    expect(main?.lastElementChild?.querySelector('[data-tressoir-feedback]')).not.toBeNull()
    expect(dom.window.document.querySelector('details.card > summary + .card-body')).not.toBeNull()
    expect(dom.window.document.querySelector('details.card > .card-body > [data-card-collapse]')?.getAttribute('aria-label')).toBe('Collapse optional section')
    expect(dom.window.document.querySelector('details.card > .card-body > .card-content')).not.toBeNull()
    expect(dom.window.document.querySelector('.card-badge')?.textContent).toBe('Optional')
    expect(dom.window.document.querySelector('[data-feedback-panel]')?.getAttribute('role')).toBe('dialog')
    expect(dom.window.document.querySelector('[data-feedback-panel]')?.hasAttribute('hidden')).toBe(true)
    expect(dom.window.document.querySelector('.feedback-popover-header p')).toBeNull()
    expect(dom.window.document.querySelector('.feedback-popover-header')?.textContent).not.toContain('Markdown')
    expect(dom.window.document.querySelector('[data-feedback-toggle]')?.getAttribute('aria-expanded')).toBe('false')
    expect(dom.window.document.querySelector('[data-feedback-toggle] svg[data-tressoir-inline]')).not.toBeNull()
    expect(dom.window.document.querySelector('.artifact-footer, .feedback-divider, .feedback-panel')).toBeNull()
    expect(dom.window.document.querySelector('.status-line')).toBeNull()
    expect(dom.window.document.querySelector('.badge')).toBeNull()
    expect(dom.window.document.querySelectorAll('[data-tressoir-decision]')).toHaveLength(1)
    expect(dom.window.document.querySelector('[data-tressoir-decision] .decision-title')).not.toBeNull()
    expect(dom.window.document.querySelector('[data-tressoir-decision] [data-decision-indicator]')?.textContent).toBe('Unresolved')
    expect(dom.window.document.querySelectorAll('[data-tressoir-decision] input[type="checkbox"]')).toHaveLength(3)
    expect(dom.window.document.querySelector('[data-tressoir-decision] legend')?.matches('.visually-hidden')).toBe(true)
    expect(dom.window.document.querySelector('[data-tressoir-decision] legend')?.textContent).not.toContain('Choose any')
    expect(dom.window.document.querySelector('[data-tressoir-decision] .decision-feedback > label')?.textContent).toBe('Free Response')
    expect(dom.window.document.querySelector('[data-tressoir-decision] textarea')?.getAttribute('rows')).toBe('2')
    expect(dom.window.document.querySelector('[data-tressoir-decision] textarea')?.getAttribute('data-tressoir-autogrow')).toBe('2:6')
    expect(dom.window.document.querySelector('[data-tressoir-status-for]')).toBeNull()
    expect(dom.window.document.body.textContent).not.toContain('Feedback for the next pass')
    expect(dom.window.document.querySelector('.reveal')).toBeNull()
    expect(dom.window.document.querySelector('.reveal-card')).toBeNull()
    expect(dom.window.document.querySelector('div.card')).toBeNull()
  })

  it('renders math, highlights the supported language pack, persists controls, and routes local links', async () => {
    const dom = new JSDOM(starterHtml, {
      runScripts: 'outside-only',
      url: 'https://artifact.test/ARTIFACT.tressoir.html',
    })
    realms.push(dom)

    ;(dom.window.Range.prototype as any).getBoundingClientRect = () => ({
      left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0,
    })
    ;(dom.window.Range.prototype as any).getClientRects = () => []
    ;(dom.window as any).focus = () => {}

    const stored = new Map<string, unknown>([['artifact.decision.feedback', 'restored note']])
    const writes: Array<{ key: string; value: unknown; filename?: string }> = []
    const opened: string[] = []
    ;(dom.window as any).tressoirNotebook = {
      context: () => Object.freeze({
        feedbackKey: 'artifact-free_form_feedback',
        interactionsFile: 'interactions.artifact.json',
      }),
      getInteraction: (key: string) => stored.get(key),
      storeInteraction: (key: string, value: unknown, filename?: string) => {
        stored.set(key, value)
        writes.push({ key, value, filename })
      },
      openFile: (path: string) => opened.push(path),
    }

    const main = dom.window.document.querySelector('main')!
    main.insertAdjacentHTML(
      'beforeend',
      '<table id="auto-table"><caption>Wide table</caption><tbody><tr><td>x</td></tr></tbody></table>' +
      '<svg id="auto-svg" viewBox="0 0 100 20" aria-label="Wide diagram"></svg>' +
      '<svg id="inline-svg" data-tressoir-inline viewBox="0 0 10 10"></svg>',
    )

    const scripts = resourceUrls('src').map(localRuntimePath)
    for (const script of scripts) evaluate(dom, script)
    dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'))

    const supported = [
      'markup', 'css', 'javascript', 'typescript', 'jsx', 'tsx', 'json', 'yaml',
      'markdown', 'bash', 'python', 'rust', 'sql', 'diff',
    ]
    for (const language of supported) {
      expect((dom.window as any).Prism.languages[language]).toBeDefined()
    }
    expect(dom.window.document.querySelector('.katex')).not.toBeNull()
    expect(dom.window.document.querySelector('code.language-typescript .token.keyword')).not.toBeNull()
    expect(dom.window.document.querySelector('code.language-diff-typescript .token.inserted')).not.toBeNull()
    expect(dom.window.document.querySelector('code.language-diff-typescript .token.deleted')).not.toBeNull()
    expect(dom.window.document.querySelector('#auto-table')?.parentElement?.matches('.scroll-region')).toBe(true)
    expect(dom.window.document.querySelector('#auto-svg')?.parentElement?.matches('.scroll-region')).toBe(true)
    expect(dom.window.document.querySelector('#inline-svg')?.parentElement?.matches('.scroll-region')).toBe(false)

    const card = dom.window.document.querySelector('details.card') as HTMLDetailsElement
    const cardSummary = card.querySelector(':scope > summary') as HTMLElement
    const cardGutter = card.querySelector('[data-card-collapse]') as HTMLButtonElement
    card.open = true
    const cardClickAllowed = cardGutter.dispatchEvent(
      new dom.window.MouseEvent('click', { bubbles: true, cancelable: true }),
    )
    expect(cardClickAllowed).toBe(false)
    expect(card.open).toBe(false)
    expect(dom.window.document.activeElement).toBe(cardSummary)

    const decision = dom.window.document.querySelector('[data-tressoir-decision]')!
    expect(decision.getAttribute('data-decision-state')).toBe('unresolved')
    expect(decision.querySelector('[data-decision-indicator]')?.textContent).toBe('Unresolved')

    const choice = decision.querySelector('input[type="checkbox"]') as HTMLInputElement
    choice.checked = true
    choice.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    expect(decision.getAttribute('data-decision-state')).toBe('resolved')
    expect(decision.querySelector('[data-decision-indicator]')?.textContent).toBe('Resolved')

    const note = dom.window.document.querySelector('#decision-feedback') as HTMLTextAreaElement
    expect(note.value).toBe('restored note')
    let noteScrollHeight = 100
    Object.defineProperty(note, 'scrollHeight', { configurable: true, get: () => noteScrollHeight })
    note.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    expect(note.style.overflowY).toBe('hidden')
    noteScrollHeight = 220
    note.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    expect(note.style.overflowY).toBe('auto')
    expect(Number.parseFloat(note.style.height)).toBeLessThan(noteScrollHeight)

    note.value = 'new persisted note'
    note.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 350))
    expect(writes).toContainEqual({
      key: 'artifact.decision.interaction',
      value: true,
      filename: 'interactions.artifact.json',
    })
    expect(writes).toContainEqual({
      key: 'artifact.decision.feedback',
      value: 'new persisted note',
      filename: 'interactions.artifact.json',
    })

    const localLink = dom.window.document.querySelector('[data-tressoir-open-file]')!
    expect(localLink.getAttribute('href')).toBe('#')
    expect(localLink.getAttribute('data-tressoir-local-path')).toBe('./SIBLING.md')
    const clickAllowed = localLink.dispatchEvent(
      new dom.window.MouseEvent('click', { bubbles: true, cancelable: true }),
    )
    expect(clickAllowed).toBe(false)
    expect(opened).toEqual(['./SIBLING.md'])

    const feedbackEditorElement = dom.window.document.querySelector('.feedback-editor .CodeMirror') as HTMLElement & {
      CodeMirror: {
        setValue(value: string): void
        getTokenTypeAt(position: { line: number; ch: number }): string | null
      }
    }
    expect(feedbackEditorElement).not.toBeNull()

    const feedbackPanel = dom.window.document.querySelector('[data-feedback-panel]') as HTMLElement
    const feedbackToggle = dom.window.document.querySelector('[data-feedback-toggle]') as HTMLButtonElement
    expect(feedbackPanel.hidden).toBe(true)
    feedbackToggle.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true }))
    expect(feedbackPanel.hidden).toBe(false)
    expect(feedbackToggle.getAttribute('aria-expanded')).toBe('true')

    feedbackEditorElement.CodeMirror.setValue('# Keep this\n\n**Strong feedback.**')
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 350))
    expect(feedbackEditorElement.CodeMirror.getTokenTypeAt({ line: 0, ch: 2 })).toContain('header')
    expect(writes).toContainEqual({
      key: 'artifact-free_form_feedback',
      value: '# Keep this\n\n**Strong feedback.**',
      filename: 'interactions.artifact.json',
    })

    dom.window.document.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(feedbackPanel.hidden).toBe(true)
    expect(feedbackToggle.getAttribute('aria-expanded')).toBe('false')
  })

  it('leaves local links as ordinary relative links in a normal browser', () => {
    const dom = new JSDOM(starterHtml, {
      runScripts: 'outside-only',
      url: 'https://artifact.test/ARTIFACT.tressoir.html',
    })
    realms.push(dom)

    evaluate(dom, 'tressoir-linear.js')
    dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'))

    const localLink = dom.window.document.querySelector('[data-tressoir-open-file]')!
    expect(localLink.getAttribute('href')).toBe('./SIBLING.md')
    expect(localLink.hasAttribute('data-tressoir-local-path')).toBe(false)
  })
})
