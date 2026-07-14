// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'
import { ensureArtifactBaseHref, recreateScripts } from '../notebook/webview/scriptInjection'

// jsdom does not fetch/run authored <script src> nodes, so it never fires their
// load/error events. recreateScripts awaits each include, so tests that contain src
// scripts must simulate the load: this observer fires `onload` on each inserted src
// script (on a microtask), letting recreateScripts proceed.
function autoResolveSrcLoads(container: HTMLElement): MutationObserver {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeName !== 'SCRIPT') return
        const script = node as HTMLScriptElement
        if (script.hasAttribute('src')) {
          queueMicrotask(() => script.onload?.(new Event('load')))
        }
      })
    }
  })
  observer.observe(container, { childList: true })
  return observer
}

describe('scriptInjection.recreateScripts', () => {
  it('re-creates inline scripts as fresh nodes and stamps the CSP nonce', async () => {
    const container = document.createElement('div')
    container.innerHTML = '<script type="text/javascript">window.__authored = 1</script>'
    const original = container.querySelector('script')!

    await recreateScripts(container, 'NONCE123')

    const fresh = container.querySelector('script')!
    expect(fresh).not.toBe(original) // a brand-new element, so the browser executes it
    expect(fresh.getAttribute('nonce')).toBe('NONCE123')
    expect(fresh.textContent).toBe('window.__authored = 1')
    expect(fresh.getAttribute('type')).toBe('text/javascript')
  })

  it('does not stamp a nonce on src scripts and preserves their attributes', async () => {
    const container = document.createElement('div')
    container.innerHTML =
      '<script src="./lib/a.js"></script><script src="./lib/b.js" defer></script>'
    const observer = autoResolveSrcLoads(container)

    await recreateScripts(container, 'NONCE123')
    observer.disconnect()

    const scripts = Array.from(container.querySelectorAll('script'))
    for (const s of scripts) {
      expect(s.hasAttribute('nonce')).toBe(false)
      expect(s.getAttribute('src')).toMatch(/^\.\/lib\//)
    }
    // The `defer` attribute is preserved on re-creation.
    expect(scripts[1]!.hasAttribute('defer')).toBe(true)
  })

  it('handles a mix of inline and src scripts', async () => {
    const container = document.createElement('div')
    container.innerHTML =
      '<script>const a = 1</script><script src="./x.js"></script><script>const b = 2</script>'
    const observer = autoResolveSrcLoads(container)

    await recreateScripts(container, 'N')
    observer.disconnect()

    const scripts = Array.from(container.querySelectorAll('script'))
    expect(scripts[0]!.getAttribute('nonce')).toBe('N')
    expect(scripts[1]!.hasAttribute('nonce')).toBe(false)
    expect(scripts[2]!.getAttribute('nonce')).toBe('N')
  })

  it('stamps a ran-marker and only re-creates NEW scripts on a second pass (morph case)', async () => {
    // The morph "lightweight refresh" re-runs recreateScripts over the same container; already
    // executed scripts must NOT run again (no double-init of authored top-level declarations),
    // and only a genuinely new authored script should be (re-)created.
    const container = document.createElement('div')
    container.innerHTML = '<script>window.__a = 1</script>'

    await recreateScripts(container, 'N')
    const first = container.querySelector('script')!
    expect(first.getAttribute('data-tressoir-script-ran')).toBe('1')

    // Simulate a morph that left the executed script in place and added a new one.
    const added = document.createElement('script')
    added.textContent = 'window.__b = 2'
    container.appendChild(added)

    await recreateScripts(container, 'N')

    const scripts = Array.from(container.querySelectorAll('script'))
    // The original executed node is untouched (same element ref, still marked).
    expect(scripts[0]).toBe(first)
    // The newly added script was re-created (fresh node) so the browser executes it, and is now
    // marked too.
    expect(scripts[1]).not.toBe(added)
    expect(scripts[1]!.getAttribute('data-tressoir-script-ran')).toBe('1')
    expect(scripts[1]!.getAttribute('nonce')).toBe('N')
  })

  it('awaits each src include before creating the next authored script (document order)', async () => {
    // Guards the vendored-lib / relative-include use case: a script following
    // `<script src="./lib/...">` must not be created until that include has loaded, so it
    // can rely on globals the include defines.
    const container = document.createElement('div')
    container.innerHTML =
      '<script src="./lib/dep.js"></script><script>window.__after = 1</script>'

    const insertedOrder: string[] = []
    let pendingSrc: HTMLScriptElement | null = null
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeName !== 'SCRIPT') return
          const script = node as HTMLScriptElement
          if (script.hasAttribute('src')) {
            insertedOrder.push('src')
            pendingSrc = script
          } else {
            insertedOrder.push('inline')
          }
        })
      }
    })
    observer.observe(container, { childList: true })

    const done = recreateScripts(container, 'N')

    // Flush microtasks: the src node is inserted and awaited, but the following inline node
    // must NOT be created yet because recreateScripts is blocked on the include's load.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(insertedOrder).toEqual(['src'])
    expect(pendingSrc).not.toBeNull()

    // Release the include's load; recreateScripts then creates the inline node, in order.
    pendingSrc!.onload?.(new Event('load'))
    await done
    observer.disconnect()

    expect(insertedOrder).toEqual(['src', 'inline'])
  })
})

describe('scriptInjection.ensureArtifactBaseHref', () => {
  beforeEach(() => {
    document.head.innerHTML = ''
  })

  it('inserts a single marked <base> as the first head child', () => {
    document.head.appendChild(document.createElement('meta'))
    ensureArtifactBaseHref('https://test.csp/artifact/')

    const bases = document.head.querySelectorAll('base[data-tressoir-artifact-base]')
    expect(bases).toHaveLength(1)
    expect(document.head.firstChild).toBe(bases[0])
    expect((bases[0] as HTMLBaseElement).getAttribute('href')).toBe('https://test.csp/artifact/')
  })

  it('is idempotent and updates the href on re-call', () => {
    ensureArtifactBaseHref('https://test.csp/a/')
    ensureArtifactBaseHref('https://test.csp/b/')

    const bases = document.head.querySelectorAll('base[data-tressoir-artifact-base]')
    expect(bases).toHaveLength(1)
    expect((bases[0] as HTMLBaseElement).getAttribute('href')).toBe('https://test.csp/b/')
  })
})
