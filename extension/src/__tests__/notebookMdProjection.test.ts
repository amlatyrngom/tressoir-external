// @vitest-environment jsdom
import { beforeAll, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'

// USER_ARTIFACT_MD projection tests. These exercise the REAL eval-free runtime
// (src/notebook/assets/tressoir-md.js) against the REAL committed extension-core remark + js-yaml
// UMD bundles, so they prove the actual v2 directive->markup behavior the webview ships — not a
// reimplementation. The v2 surface is front-matter + depth-styled headings + THREE directives
// (::::card / :::item / :::input) + plain markdown. The core bundles are COMMITTED under
// assets/core/ (rebuilt rarely per assets/core/README.md); the existence guard is a
// belt-and-suspenders no-op for an unusual checkout missing them.
const assetsDir = resolve(__dirname, '../notebook/assets')
const remarkPath = resolve(assetsDir, 'core/tressoir-remark.umd.js')
const yamlPath = resolve(assetsDir, 'core/js-yaml.min.js')
const runtimePath = resolve(assetsDir, 'tressoir-md.js')
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

  it('projects front-matter title/description into the locked header (type optional)', () => {
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
    expect(html).toContain('<div class="wrap">')
    expect(html).toContain('<header class="plan-head">')
    expect(html).toContain('My Plan Title')
    expect(html).toContain('<span class="badge type">Plan</span>')
    expect(html).toContain('<p class="dek">A one-line dek.</p>')
    // Free-form feedback host must carry the morph-skip contract (CodeMirror lives here).
    expect(html).toContain('<div class="head-feedback" data-morph-skip>')
    expect(html).toContain('id="ff-editor"')
  })

  it('omits the type badge when front-matter has no `tressoir:` type', () => {
    const md = ['---', 'title: No Type', '---', '', 'Body.'].join('\n')
    const html = project(md)
    expect(html).toContain('<h1>No Type</h1>')
    expect(html).not.toContain('badge type')
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
    expect(html).toContain('<section class="ua-section"><h2 class="section">Executive Summary</h2>')
    // Consecutive items group into a single .ctx-list.
    expect(html).toContain('<div class="ctx-list">')
    // Open item carries the open class + keep-class contract; closed item does not start open.
    expect(html).toContain('<div class="ctx-item open" data-morph-keep-class="open">')
    expect(html).toContain('<div class="ctx-item" data-morph-keep-class="open">')
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('Goal')
    expect(html).toContain('Make it first-class.')
  })

  it('projects ::::card into a .milestone reveal card with a raw inline state badge', () => {
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
    // Consecutive cards group into .milestones; card is collapsed by default.
    expect(html).toContain('<div class="milestones">')
    expect(html).toContain('<section class="milestone" data-morph-keep-class="selected">')
    expect(html).toContain('<div class="m-title">M1 — Core</div>')
    expect(html).toContain('<div class="m-intent">Wire the projector</div>')
    // State is injected RAW (inline badge HTML) inside the .m-state slot.
    expect(html).toContain('<span class="m-state"><span class=\'badge ok\'>Done</span></span>')
    // Card head is a keyboard-activatable div button; the item nests inside.
    expect(html).toContain('<div class="m-head" role="button" tabindex="0" aria-expanded="false">')
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
    expect(html).toContain('<section class="milestone selected" data-morph-keep-class="selected">')
    expect(html).toContain('aria-expanded="true"')
  })

  it('projects :::input into a .m-decision row: question head, markdown options, bound textbox', () => {
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
    // Decision row carries the locked classes + the read-back key.
    expect(html).toContain('<div class="ctx-item m-decision m-input" data-key="approach.scope" data-morph-keep-class="open">')
    // Head = the first paragraph (the question); a check turns green when resolved.
    expect(html).toContain('<span class="dec-check" aria-hidden="true"></span>')
    expect(html).toContain('<span class="dec-name">Which approach should we take?</span>')
    // Options render as a normal markdown list, recommended via emphasis.
    expect(html).toContain('<li>Approach A <em>(recommended)</em></li>')
    expect(html).toContain('<li>Approach B</li>')
    // Bound, morph-skipped text box keyed for interactions.json read-back.
    expect(html).toContain('<div class="other-box show" data-morph-skip>')
    expect(html).toContain('<textarea data-input-key="approach.scope"')
  })

  it('uses an `oneliner=`/`question=` attribute as the input head when present', () => {
    const md = [
      ':::input{key=k question="Explicit question?"}',
      '- opt',
      ':::',
    ].join('\n')
    const html = project(md)
    expect(html).toContain('<span class="dec-name">Explicit question?</span>')
    expect(html).toContain('<li>opt</li>')
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
    expect(html).toContain('<h2 class="section">Section</h2>')
    expect(html).toContain('<h3>A sub heading</h3>')
    expect(html).toContain('<h4>A label</h4>')
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

  it('renders fenced code (```lang -> pre.code) and ```diff -> pre.diff', () => {
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
    expect(html).toContain('<pre class="code" data-lang="py">')
    expect(html).toContain('<pre class="diff" data-lang="">')
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
    expect(html).toContain('<table>')
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

  it('treats missing front-matter as a WARNING, not an error (front-matter is optional in v2)', () => {
    const findings = lint('Just a paragraph, no front-matter.\n')
    expect(levels(findings, 'error')).toHaveLength(0)
    expect(levels(findings, 'warn').some((f) => /front-matter/.test(f.msg))).toBe(true)
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
})
