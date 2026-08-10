// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { JSDOM } from 'jsdom'

const runtimeSource = readFileSync(
  resolve(__dirname, '../notebook/assets/tressoir-md.js'),
  'utf8',
)

const realms: JSDOM[] = []
afterEach(() => {
  while (realms.length > 0) realms.pop()?.window.close()
})

describe('rendered local artifact navigation', () => {
  it('opens relative Markdown links and images through the contained VS Code bridge', () => {
    const dom = new JSDOM(
      '<!doctype html><html><body>' +
        '<a id="local" href="./note.jpg" target="_blank">source</a>' +
        '<img id="image" src="diagram.png">' +
        '<a id="parent" href="../../../Summer2026/RQE/TRESSOIR_PAPER.pdf">paper</a>' +
        '<a id="remote" href="https://example.com/x">remote</a>' +
        '<a id="absolute" href="/tmp/secret.txt">absolute</a>' +
      '</body></html>',
      { runScripts: 'outside-only', url: 'https://artifact.test/' },
    )
    realms.push(dom)
    const opened: string[] = []
    ;(dom.window as any).tressoirNotebook = { openFile: (path: string) => opened.push(path) }

    dom.window.eval(runtimeSource)
    dom.window.document.dispatchEvent(new dom.window.CustomEvent('tressoir:render'))
    const local = dom.window.document.getElementById('local')!
    const remote = dom.window.document.getElementById('remote')!
    expect(local.getAttribute('href')).toBe('#')
    expect(local.getAttribute('target')).toBeNull()
    expect(local.getAttribute('data-tressoir-local-path')).toBe('./note.jpg')
    expect(remote.getAttribute('href')).toBe('https://example.com/x')

    const downstreamClicks: string[] = []
    dom.window.document.addEventListener('click', (event) => {
      downstreamClicks.push((event.target as Element).id)
    })
    const canceled: Record<string, boolean> = {}
    for (const id of ['local', 'image', 'parent', 'remote', 'absolute']) {
      canceled[id] = !dom.window.document.getElementById(id)!.dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true, cancelable: true }),
      )
    }

    expect(opened).toEqual([
      './note.jpg',
      'diagram.png',
      '../../../Summer2026/RQE/TRESSOIR_PAPER.pdf',
    ])
    expect(canceled).toEqual({
      local: true,
      image: true,
      parent: true,
      remote: false,
      absolute: false,
    })
    expect(downstreamClicks).toEqual(['remote', 'absolute'])
  })
})
