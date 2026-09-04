// @vitest-environment jsdom
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'

// Markdown projection tests exercise the real eval-free runtime against the committed parser.
// Public authoring is H1/lede Markdown plus exact shared HTML components; legacy directives remain
// positive compatibility fixtures. The core bundles are committed under
// assets/core/ (rebuilt rarely per assets/core/README.md); the existence guard is a
// belt-and-suspenders no-op for an unusual checkout missing them.
const assetsDir = resolve(__dirname, '../notebook/assets')
const remarkPath = resolve(assetsDir, 'core/tressoir-remark.umd.js')
const yamlPath = resolve(assetsDir, 'core/js-yaml.min.js')
const runtimePath = resolve(assetsDir, 'tressoir-md.js')
const artifactCssPath = resolve(assetsDir, 'artifact.css')
const linearDir = resolve(assetsDir, 'linear')
const corePresent = existsSync(remarkPath) && existsSync(yamlPath) && existsSync(runtimePath)

// Evaluate a classic/UMD script into the current jsdom global. The core bundles attach to
// `window`/`self`/`globalThis`; tressoir-md.js attaches `TressoirMd` to `window`.
function loadScript(p: string): void {
  const code = readFileSync(p, 'utf8')
  // eslint-disable-next-line @typescript-eslint/no-implied-eval, no-new-func
  const fn = new Function('window', 'self', 'globalThis', 'global', code)
  fn(globalThis, globalThis, globalThis, globalThis)
}

describe.skipIf(!corePresent)('USER_ARTIFACT_MD projection (real tressoir-md.js project())', () => {
  let project: (markdown: string) => string
  let applyBehaviors: () => void

  beforeAll(() => {
    loadScript(remarkPath)
    loadScript(yamlPath)
    loadScript(runtimePath)
    const runtime = (globalThis as unknown as {
      TressoirMd?: { project: (m: string) => string; applyBehaviors: () => void }
    }).TressoirMd
    if (!runtime) {
      throw new Error('TressoirMd runtime did not load.')
    }
    project = runtime.project
    applyBehaviors = runtime.applyBehaviors
  })

  it('keeps front-matter title/description as a presentation-neutral compatibility header', () => {
    const md = [
      '---',
      'tressoir: plan',
      'title: My Plan Title',
      'description: A one-line dek.',
      '---',
      '',
      'Intro paragraph.',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<main class="tressoir-document">')
    expect(html).toContain('<header class="document-header">')
    expect(html).toContain('<h1>My Plan Title</h1>')
    expect(html).toContain('<p class="lede">A one-line dek.</p>')
    expect(html).not.toContain('badge type')
    expect(html).toContain('<aside class="feedback-dock" data-feedback-dock>')
    expect(html).toContain('data-tressoir-feedback')
  })

  it('omits the type badge when front-matter has no `tressoir:` type', () => {
    const md = ['---', 'title: No Type', '---', '', 'Body.'].join('\n')
    const html = project(md)
    expect(html).toContain('<h1>No Type</h1>')
    expect(html).not.toContain('badge type')
  })

  it('can disable the automatic top-level feedback editor in frontmatter', () => {
    for (const value of ['disabled', 'disable', 'off', 'false']) {
      const md = ['---', 'title: Quiet Artifact', `feedback: ${value}`, '---', '', 'Body.'].join('\n')
      const html = project(md)
      expect(html).not.toContain('class="head-feedback"')
      expect(html).not.toContain('id="ff-editor"')
    }
  })

  it('projects :::item directives into morph-safe .ctx-item disclosure rows', () => {
    const md = [
      '## Executive Summary',
      '',
      ':::item{oneliner="Goal" open}',
      'Make it first-class.',
      ':::',
      '',
      ':::item{oneliner="Closed one"}',
      'Hidden by default.',
      ':::',
    ].join('\n')
    const html = project(md)
    // Section heading.
    expect(html).toContain('<section class="section"><h2>Executive Summary</h2>')
    expect(html).not.toContain('data-copy-card')
    // Consecutive items group into a single .ctx-list.
    expect(html).toContain('<div class="ctx-list">')
    // Open item carries the open class + keep-class contract; closed item does not start open.
    expect(html).toContain('<div class="ctx-item open" data-morph-keep-class="open">')
    expect(html).toContain('<div class="ctx-item" data-morph-keep-class="open">')
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('Goal')
    expect(html).toContain('Make it first-class.')
  })

  it('copies original card Markdown only when copy_button=true', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const md = [
      '---',
      'title: Copy Test',
      'feedback: disabled',
      '---',
      '',
      '## Tasks',
      '',
      '::::card{title="Copy Me" oneliner="Handoff-ready." copy_button=true}',
      'Card body.',
      '::::',
      '',
      '::::card{title="Ordinary" oneliner="No control."}',
      'Other body.',
      '::::',
      '',
    ].join('\n')
    document.body.innerHTML = project(md)
    applyBehaviors()
    const buttons = document.querySelectorAll<HTMLButtonElement>('[data-copy-card]')
    expect(buttons).toHaveLength(1)
    buttons[0].click()
    expect(writeText).toHaveBeenCalledWith([
      '::::card{title="Copy Me" oneliner="Handoff-ready." copy_button=true}',
      'Card body.',
      '::::',
    ].join('\n'))
    expect((buttons[0].closest('details.card') as HTMLDetailsElement | null)?.open).toBe(false)
    await vi.waitFor(() => expect(buttons[0].textContent).toBe('Copied'))
  })

  it('projects a legacy ::::card into the canonical native card with a raw inline state badge', () => {
    const md = [
      '## Milestones',
      '',
      '::::card{title="M1 — Core" oneliner="Wire the projector" state="<span class=\'badge ok\'>Done</span>"}',
      ':::item{oneliner="Change the renderer"}',
      'Body of the item.',
      ':::',
      '::::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<details class="card" data-tressoir-markdown>')
    expect(html).toContain('<span class="card-title">M1 — Core</span>')
    expect(html).toContain('<span class="card-oneliner">Wire the projector</span>')
    expect(html).toContain('<span class="card-badge"><span class=\'badge ok\'>Done</span></span>')
    expect(html).toContain('class="card-gutter"')
    expect(html).not.toContain('data-copy-card')
    // The legacy item remains available inside the canonical card body.
    expect(html).toContain('<div class="ctx-item" data-morph-keep-class="open">')
    expect(html).toContain('Change the renderer')
  })

  it('starts an `open` card expanded (selected + aria true)', () => {
    const md = [
      '::::card{title="Open card" open}',
      ':::item{oneliner="x"}',
      'y',
      ':::',
      '::::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<details class="card" data-tressoir-markdown open>')
  })

  it('projects legacy :::input into the canonical decision with stable derived choice keys', () => {
    const md = [
      '## Decisions',
      '',
      ':::input{key=approach.scope}',
      'Which approach should we take?',
      '',
      '- Approach A *(recommended)*',
      '- Approach B',
      '',
      'Type a pick, a tweak, or a question.',
      ':::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<article class="decision" data-tressoir-decision')
    expect(html).toContain('data-morph-key="tressoir-input:approach.scope"')
    expect(html).toContain('class="decision-title"')
    expect(html).toContain('Which approach should we take?')
    expect(html).toContain('data-tressoir-input="approach.scope.choice.1"')
    expect(html).toContain('data-tressoir-input="approach.scope.choice.2"')
    expect(html).toContain('rows="2" data-tressoir-input="approach.scope" data-tressoir-autogrow="2:6"')
  })

  it('uses an `oneliner=`/`question=` attribute as the input head when present', () => {
    const md = [
      ':::input{key=k question="Explicit question?"}',
      '- opt',
      ':::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('class="decision-title"')
    expect(html).toContain('Explicit question?')
    expect(html).toContain('<strong>opt</strong>')
  })

  it('styles markdown headings by depth (### -> h3, #### -> h4) — no hand-written sub-titles', () => {
    const md = [
      '## Section',
      '',
      '### A sub heading',
      '',
      'Prose.',
      '',
      '#### A label',
      '',
      'More prose.',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<section class="section"><h2>Section</h2>')
    expect(html).toContain('<h3>A sub heading</h3>')
    expect(html).toContain('<h4>A label</h4>')
  })

  it('uses a leading Markdown H1/lede instead of front-matter presentation fields', () => {
    const md = [
      '---',
      'title: Header title',
      'feedback: disabled',
      '---',
      '',
      '# Large body title',
      '',
      'A public lede.',
      '',
      '::::card{title="First card"}',
      'Card body.',
      '::::',
    ].join('\n')
    const style = document.createElement('style')
    style.textContent = readFileSync(artifactCssPath, 'utf8')
    document.head.append(style)
    document.body.innerHTML = project(md)

    try {
      const headerTitle = document.querySelector<HTMLElement>('.document-header h1')
      expect(headerTitle?.textContent).toBe('Large body title')
      expect(document.querySelector('.document-header .lede')?.textContent).toBe('A public lede.')
      expect(document.body.textContent).not.toContain('Header title')
      expect(document.querySelector('details.card')).not.toBeNull()
    } finally {
      style.remove()
      document.body.innerHTML = ''
    }
  })

  it('passes raw HTML / SVG through untouched (diagrams + advanced styling)', () => {
    const md = [
      '## Architecture',
      '',
      '<div class="realm-diagram">',
      '  <svg class="arch-svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>',
      '</div>',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<div class="realm-diagram">')
    expect(html).toContain('<svg class="arch-svg"')
  })

  it('keeps ordinary Markdown inside the exact marked card contract', () => {
    const md = [
      '# Card acceptance',
      '',
      'A concise lede.',
      '',
      '<details class="card" data-tressoir-markdown>',
      '  <summary>',
      '    <span class="card-title">Optional details</span>',
      '    <span class="card-oneliner">Open the section</span>',
      '    <span class="card-badge">Optional</span>',
      '  </summary>',
      '',
      '### Markdown heading inside',
      '',
      '- one',
      '- two',
      '',
      '</details>',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<details class="card" data-tressoir-markdown>')
    expect(html).toContain('<div class="card-body"><button class="card-gutter"')
    expect(html).toContain('<div class="card-content"><h3>Markdown heading inside</h3>')
    expect(html).toContain('<li>one</li>')
    expect(html.indexOf('Markdown heading inside')).toBeLessThan(html.indexOf('</details>'))
  })

  it('passes the exact raw decision component through for the shared runtime', () => {
    const md = [
      '# Decision acceptance',
      '',
      'A concise lede.',
      '',
      '<article class="decision" data-tressoir-decision data-decision-state="unresolved">',
      '<input type="checkbox" data-tressoir-input="release.accept">',
      '<textarea rows="2" data-tressoir-input="release.feedback" data-tressoir-autogrow="2:6"></textarea>',
      '</article>',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('data-tressoir-decision')
    expect(html).toContain('data-tressoir-input="release.accept"')
    expect(html).toContain('data-tressoir-autogrow="2:6"')
  })

  it('renders fenced code and diffs into the shared Prism DOM', () => {
    const md = [
      ':::item{oneliner="snippet"}',
      '```py',
      'def f():',
      '    return 1',
      '```',
      '',
      '```diff',
      '@@ x @@',
      '-old',
      '+new',
      '```',
      ':::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<pre class="code-block"><code class="language-python">')
    expect(html).toContain('<pre class="code-block diff-highlight"><code class="language-diff">')
  })

  it('renders GFM tables, strikethrough, and task lists (remark-gfm in the core bundle)', () => {
    const md = [
      '## Overview',
      '',
      '| Col A | Col B |',
      '| ----- | ----- |',
      '| one   | two   |',
      '',
      'A ~~struck~~ word.',
      '',
      '- [ ] todo item',
      '- [x] done item',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<table class="table">')
    expect(html).toContain('<th>Col A</th>')
    expect(html).toContain('<td>one</td>')
    expect(html).toContain('<del>struck</del>')
    expect(html).toContain('type="checkbox"')
    expect(html).toContain('checked')
  })

  it('emits NONE of the removed v1 constructs (no decision queue / file tabs / turns / radio tabs)', () => {
    const md = ['---', 'title: T', '---', '', '## A', 'x'].join('\n')
    const html = project(md)
    expect(html).not.toContain('alt-radio')
    expect(html).not.toContain('type="radio"')
    expect(html).not.toContain('class="dq"')
    expect(html).not.toContain('class="mtabs"')
    expect(html).not.toContain('class="turns"')
    expect(html).not.toContain('m-status')
  })

  it('enhances projected Markdown with the exact shared math, code, decision, overflow, card, and feedback runtime', () => {
    ;(Range.prototype as any).getBoundingClientRect = () => ({
      left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0,
    })
    ;(Range.prototype as any).getClientRects = () => []
    ;(window as any).focus = () => {}
    const stored = new Map<string, unknown>()
    Object.defineProperty(window, 'tressoirNotebook', {
      configurable: true,
      value: {
        context: () => ({ feedbackKey: 'acceptance-free_form_feedback', interactionsFile: 'acceptance.interactions.json' }),
        getInteraction: (key: string) => stored.get(key),
        storeInteraction: (key: string, value: unknown) => stored.set(key, value),
      },
    })

    document.body.innerHTML = project([
      '# Runtime acceptance', '', 'A concise lede.', '',
      'Inline math: \\(x^2\\).', '',
      '```typescript', 'const ready: boolean = true', '```', '',
      '<table><tr><td>wide</td></tr></table>', '',
      '<details class="card" data-tressoir-markdown>',
      '<summary><span class="card-title">Optional</span><span class="card-oneliner">Open</span><span class="card-badge">Optional</span></summary>',
      '', '### Inside', '', 'Selectable body.', '', '</details>', '',
      '<article class="decision" data-tressoir-decision data-decision-state="unresolved">',
      '<span data-decision-indicator>Unresolved</span>',
      '<input type="checkbox" data-tressoir-input="runtime.accept">',
      '</article>',
    ].join('\n'))

    for (const path of [
      'vendor/katex/katex.min.js',
      'vendor/katex/auto-render.min.js',
      'vendor/prism/components/prism-core.min.js',
      'vendor/prism/components/prism-markup.min.js',
      'vendor/prism/components/prism-clike.min.js',
      'vendor/prism/components/prism-javascript.min.js',
      'vendor/prism/components/prism-typescript.min.js',
      'vendor/prism/components/prism-diff.min.js',
      'vendor/codemirror/codemirror.js',
      'vendor/codemirror/mode/xml.js',
      'vendor/codemirror/mode/meta.js',
      'vendor/codemirror/mode/markdown.js',
      'tressoir-linear.js',
    ]) loadScript(resolve(linearDir, path))
    document.dispatchEvent(new Event('DOMContentLoaded'))
    document.dispatchEvent(new CustomEvent('tressoir:render'))

    expect(document.querySelector('.katex')).not.toBeNull()
    expect(document.querySelector('code.language-typescript .token.keyword')).not.toBeNull()
    expect(document.querySelector('table')?.parentElement?.matches('.scroll-region')).toBe(true)
    expect(document.querySelector('details.card > .card-body > [data-card-collapse]')).not.toBeNull()

    const decision = document.querySelector('[data-tressoir-decision]')!
    const choice = decision.querySelector('input') as HTMLInputElement
    choice.checked = true
    choice.dispatchEvent(new Event('input', { bubbles: true }))
    expect(decision.getAttribute('data-decision-state')).toBe('resolved')
    expect(decision.querySelector('[data-decision-indicator]')?.textContent).toBe('Resolved')

    const feedbackPanel = document.querySelector('[data-feedback-panel]') as HTMLElement
    const feedbackToggle = document.querySelector('[data-feedback-toggle]') as HTMLButtonElement
    expect(document.querySelector('.feedback-editor .CodeMirror')).not.toBeNull()
    feedbackToggle.click()
    expect(feedbackPanel.hidden).toBe(false)
  })
})

describe.skipIf(!corePresent)('USER_ARTIFACT_MD lint() (real tressoir-md.js, no DOM rendering)', () => {
  type Finding = { level: 'error' | 'warn' | 'info'; line: number; msg: string }
  let lint: (markdown: string) => Finding[]

  beforeAll(() => {
    loadScript(remarkPath)
    loadScript(yamlPath)
    loadScript(runtimePath)
    const runtime = (globalThis as unknown as { TressoirMd?: { lint: (m: string) => Finding[] } }).TressoirMd
    if (!runtime || typeof runtime.lint !== 'function') {
      throw new Error('TressoirMd.lint did not load.')
    }
    lint = runtime.lint
  })

  const levels = (fs: Finding[], level: Finding['level']) => fs.filter((f) => f.level === level)

  it('passes a well-formed v2 artifact with no errors', () => {
    const md = [
      '---',
      'tressoir: plan',
      'title: A Good Plan',
      '---',
      '',
      'Lead paragraph.',
      '',
      '## Milestones',
      '',
      '::::card{title="M1" oneliner="do the thing"}',
      ':::item{oneliner="change a thing"}',
      'detail',
      ':::',
      '::::',
      '',
      '## Decisions',
      '',
      ':::input{key=approach}',
      'Which approach?',
      '',
      '- Approach A *(recommended)*',
      '- Approach B',
      ':::',
    ].join('\n')
    const findings = lint(md)
    expect(levels(findings, 'error')).toHaveLength(0)
  })

  it('accepts the public no-frontmatter H1/lede contract', () => {
    const findings = lint('# Artifact title\n\nA concise lede.\n')
    expect(levels(findings, 'error')).toHaveLength(0)
    expect(levels(findings, 'warn').some((f) => /front-matter/.test(f.msg))).toBe(false)
  })

  it('requires either a leading H1 or a legacy frontmatter title', () => {
    const findings = lint('Just a paragraph, no heading.\n')
    expect(levels(findings, 'error').some((f) => /leading H1/.test(f.msg))).toBe(true)
  })

  it('rejects standard dependency links because the extension owns them', () => {
    const findings = lint([
      '---',
      'links:',
      '  - ./vendor/katex/katex.min.js',
      '---',
      '',
      '# Artifact title',
      '',
      'A concise lede.',
    ].join('\n'))
    expect(levels(findings, 'error').some((f) => /loads them automatically/.test(f.msg))).toBe(true)
  })

  it('rejects unclosed or nested marked cards', () => {
    const unclosed = lint('# T\n\nLede.\n\n<details class="card" data-tressoir-markdown>\n<summary>x</summary>\n')
    expect(levels(unclosed, 'error').some((f) => /no matching/.test(f.msg))).toBe(true)
    const nested = lint([
      '# T', '', 'Lede.', '',
      '<details class="card" data-tressoir-markdown>', '<summary>outer</summary>',
      '<details class="card" data-tressoir-markdown>', '<summary>inner</summary>', '</details>', '</details>',
    ].join('\n'))
    expect(levels(nested, 'error').some((f) => /cannot nest/.test(f.msg))).toBe(true)
  })

  it('warns (not errors) on an unrecognized `tressoir:` type (type is optional/cosmetic)', () => {
    const md = ['---', 'tressoir: bogus', 'title: X', '---', '', 'Body.'].join('\n')
    const findings = lint(md)
    expect(levels(findings, 'error')).toHaveLength(0)
    expect(levels(findings, 'warn').some((f) => /plan \| research \| interactive/.test(f.msg))).toBe(true)
  })

  it('errors on a :::input with no `key=` (its answer cannot be read back)', () => {
    const md = [
      '---', 'title: Decisions', '---', '',
      ':::input',
      'A question with no key.',
      ':::',
    ].join('\n')
    const errs = levels(lint(md), 'error')
    expect(errs.some((f) => /no `key=`/.test(f.msg))).toBe(true)
  })

  it('errors when :::input uses a key reserved for the automatic feedback box', () => {
    for (const key of ['free_form_feedback', 'PLAN-free_form_feedback']) {
      const md = [
        '---', 'title: Decisions', '---', '',
        `:::input{key=${key}}`,
        'A conflicting question.',
        ':::',
      ].join('\n')
      const errs = levels(lint(md), 'error')
      expect(errs.some((f) => /reserved free-form feedback key/.test(f.msg))).toBe(true)
    }
  })

  it('warns on a :::input with no question (no leading paragraph and no oneliner)', () => {
    const md = [
      '---', 'title: Decisions', '---', '',
      ':::input{key=k}',
      '- just an option, no question paragraph',
      ':::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /no question/.test(f.msg))).toBe(true)
  })

  it('warns on a card with no title= and on an unknown directive (known: card, item, input)', () => {
    const md = [
      '---', 'title: X', '---', '',
      '::::card{oneliner="no title"}',
      ':::item{oneliner="x"}',
      'y',
      ':::',
      '::::',
      '',
      ':::bogusdir',
      'content',
      ':::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /::::card has no `title=`/.test(f.msg))).toBe(true)
    expect(warns.some((f) => /unknown directive `:bogusdir`/.test(f.msg))).toBe(true)
  })

  it('produces findings sorted by line, errors before warnings on the same line', () => {
    // A keyless input with no question yields an error (key) + warn (question) on the same line.
    const md = [
      '---', 'title: Order', '---', '',
      ':::input',
      '- only an option',
      ':::',
    ].join('\n')
    const findings = lint(md)
    const inputLine = findings.find((x) => /no `key=`/.test(x.msg))!.line
    const sameLine = findings.filter((f) => f.line === inputLine)
    const errIdx = sameLine.findIndex((f) => f.level === 'error')
    const warnIdx = sameLine.findIndex((f) => f.level === 'warn')
    expect(errIdx).toBeGreaterThanOrEqual(0)
    expect(warnIdx).toBeGreaterThan(errIdx)
  })

  // ---- v2.1 advisory authoring warnings (all warn-only; never change exit status) ----

  const longText = (n: number) => 'x'.repeat(n)

  it('warns when a card title or item oneliner exceeds 200 characters (boundary check)', () => {
    const md = [
      '---', 'title: X', '---', '',
      `::::card{title="${longText(201)}" oneliner="ok"}`,
      `:::item{oneliner="${longText(201)}"}`,
      'body',
      ':::',
      '::::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /::::card title exceeds 200 characters/.test(f.msg))).toBe(true)
    expect(warns.some((f) => /:::item oneliner exceeds 200 characters/.test(f.msg))).toBe(true)
  })

  it('does not warn on a card title or item oneliner exactly at 200 characters', () => {
    const md = [
      '---', 'title: X', '---', '',
      `::::card{title="${longText(200)}" oneliner="ok"}`,
      `:::item{oneliner="${longText(200)}"}`,
      'body',
      ':::',
      '::::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /exceeds 200 characters/.test(f.msg))).toBe(false)
  })

  it("warns when an input question's first paragraph exceeds 200 characters", () => {
    const md = [
      '---', 'title: X', '---', '',
      ':::input{key=long.q}',
      longText(201),
      '',
      '- Option A',
      ':::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /:::input question first paragraph exceeds 200 characters/.test(f.msg))).toBe(true)
  })

  it('warns (not errors) when two explicit inputs reuse the same key', () => {
    const md = [
      '---', 'title: X', '---', '',
      ':::input{key=dup.key}',
      'First question?',
      ':::',
      ':::input{key=dup.key}',
      'Second question?',
      ':::',
    ].join('\n')
    const findings = lint(md)
    expect(levels(findings, 'error')).toHaveLength(0)
    expect(levels(findings, 'warn').some((f) => /used by more than one input/.test(f.msg))).toBe(true)
  })

  it('warns when a Planning/Implementing card lacks #### Planned Changes', () => {
    for (const state of ['Planning', 'Implementing']) {
      const md = [
        '---', 'title: X', '---', '',
        `::::card{title="M1" oneliner="c" state="<span class='badge warn'>${state}</span>"}`,
        '#### Planning Overview',
        ':::item{oneliner="x"}',
        'y',
        ':::',
        '::::',
      ].join('\n')
      const warns = levels(lint(md), 'warn')
      expect(warns.some((f) => /has no `#### Planned Changes`/.test(f.msg))).toBe(true)
    }
  })

  it('does not warn when a Planning card includes #### Planned Changes', () => {
    const md = [
      '---', 'title: X', '---', '',
      "::::card{title=\"M1\" oneliner=\"c\" state=\"<span class='badge warn'>Planning</span>\"}",
      '#### Planned Changes',
      ':::item{oneliner="edit"}',
      '```diff',
      '- a',
      '+ b',
      '```',
      ':::',
      '::::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /Planned Changes/.test(f.msg))).toBe(false)
  })

  it('warns when a Review/Completed card lacks a Completion Report or Planned Changes', () => {
    const md = [
      '---', 'title: X', '---', '',
      "::::card{title=\"M1\" oneliner=\"c\" state=\"<span class='badge ok'>Review</span>\"}",
      '#### Notes',
      ':::item{oneliner="x"}',
      'y',
      ':::',
      '::::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /`review`.*no `#### Completion Report`/.test(f.msg))).toBe(true)
  })

  it('warns when a TBD card already carries Planned Changes', () => {
    const md = [
      '---', 'title: X', '---', '',
      "::::card{title=\"M1\" oneliner=\"c\" state=\"<span class='badge muted'>TBD</span>\"}",
      '#### Planned Changes',
      ':::item{oneliner="edit"}',
      '```diff',
      '- a',
      '+ b',
      '```',
      ':::',
      '::::',
    ].join('\n')
    const warns = levels(lint(md), 'warn')
    expect(warns.some((f) => /`TBD` but already has `#### Planned Changes`/.test(f.msg))).toBe(true)
  })

  it('warns when a fenced snippet has no nearby file/symbol name', () => {
    const orphan = [
      '---', 'title: X', '---', '',
      '```diff',
      '- a',
      '+ b',
      '```',
    ].join('\n')
    expect(levels(lint(orphan), 'warn').some((f) => /file or symbol name/.test(f.msg))).toBe(true)
    const inside = [
      '---', 'title: X', '---', '',
      ':::item{oneliner="edit"}',
      '```diff',
      '- a',
      '+ b',
      '```',
      ':::',
    ].join('\n')
    expect(levels(lint(inside), 'warn').some((f) => /file or symbol name/.test(f.msg))).toBe(false)

    const named = ['# X', '', 'Lede.', '', '`src/app.ts · render()`', '', '```diff', '- a', '+ b', '```'].join('\n')
    expect(levels(lint(named), 'warn').some((f) => /file or symbol name/.test(f.msg))).toBe(false)
  })
})
