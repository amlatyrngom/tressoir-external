// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import morphdom from 'morphdom'
import { preserveDetailsState } from '../notebook/webview/morphState'

function morph(source: HTMLDetailsElement, authored: string): void {
  const target = document.createElement('details')
  target.innerHTML = authored
  morphdom(source, target, {
    onBeforeElUpdated(fromEl, toEl) {
      preserveDetailsState(fromEl, toEl)
      return true
    },
  })
}

describe('native disclosure state during live morphs', () => {
  it('keeps an open disclosure open while updating its authored body', () => {
    const details = document.createElement('details')
    details.innerHTML = '<summary>Useful conclusion</summary><p>Old evidence</p>'
    details.open = true

    morph(details, '<summary>Useful conclusion</summary><p>New evidence</p>')

    expect(details.open).toBe(true)
    expect(details.hasAttribute('open')).toBe(true)
    expect(details.querySelector('p')?.textContent).toBe('New evidence')
  })

  it('does not reopen a disclosure the reader closed', () => {
    const details = document.createElement('details')
    details.innerHTML = '<summary>Conclusion</summary><p>Evidence</p>'
    details.open = false

    morph(details, '<summary>Conclusion</summary><p>Revised evidence</p>')

    expect(details.open).toBe(false)
    expect(details.hasAttribute('open')).toBe(false)
  })
})
