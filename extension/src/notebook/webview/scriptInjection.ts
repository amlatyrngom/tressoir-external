// Helpers for executing authored JavaScript in the main webview document and resolving
// authored relative URLs against the artifact folder.
//
// Authored content is rendered directly into the main VS Code webview document rather
// than a child iframe so artifact-scoped webview resources resolve consistently. That means:
//   - <script> nodes parsed via innerHTML are flagged "already started" and never run, so
//     each must be re-created as a fresh element to execute (recreateScripts), and
//   - a per-render CSP nonce must be stamped on re-created INLINE scripts (the nonce-based
//     policy makes the browser ignore 'unsafe-inline'); relative `<script src>` stay covered
//     by the CSP host-source (${cspSource}).

const BASE_MARKER_ATTR = 'data-tressoir-artifact-base'

/**
 * Inject (once) a <base href> so authored relative URLs and `fetch('./...')` resolve to the
 * artifact's own folder. All webview-owned resources use absolute asWebviewUri values, so
 * the base only affects authored relatives.
 */
export function ensureArtifactBaseHref(href: string): void {
  const existing = document.head.querySelector<HTMLBaseElement>(`base[${BASE_MARKER_ATTR}]`)
  if (existing) {
    existing.href = href
    return
  }
  const base = document.createElement('base')
  base.setAttribute(BASE_MARKER_ATTR, '')
  base.href = href
  // Prepend so the base applies before any authored relative resources are encountered.
  document.head.insertBefore(base, document.head.firstChild)
}

/**
 * Re-create every <script> inside `container` so the browser executes authored scripts,
 * preserving authored DOCUMENT ORDER (like normal parser-inserted scripts).
 * INLINE (no-src) scripts are stamped with the per-render CSP nonce so the nonce-based
 * policy allows them; relative `<script src>` are covered by the CSP host-source and do
 * not need the nonce.
 *
 * Scripts are processed SEQUENTIALLY: each inline script executes synchronously when its
 * node is inserted, and each external (src) include is forced non-async and AWAITED before
 * the next node is created. This guarantees that a later inline script (or a later include)
 * can rely on globals defined by a preceding `<script src="./lib/...">`, matching the plan's
 * vendored-lib / relative-include use case. (Dynamically-created scripts default to
 * async=true, so `async=false` alone is insufficient — the per-node await is what enforces
 * include-then-use ordering.) Resolves once all authored scripts have run/settled.
 */
const RAN_MARKER_ATTR = 'data-tressoir-script-ran'

export async function recreateScripts(container: HTMLElement, nonce: string): Promise<void> {
  // Only (re-)execute scripts that have NOT already run. On the initial full render every
  // authored script is new; on a morph "lightweight refresh" the previously-executed scripts
  // are preserved untouched (they keep this marker) and only genuinely NEW authored scripts
  // run — so a morph never double-initializes authored top-level declarations.
  const scripts = Array.from(container.querySelectorAll('script')).filter(
    (s) => !s.hasAttribute(RAN_MARKER_ATTR),
  )
  for (const oldScript of scripts) {
    const fresh = document.createElement('script')
    for (const attr of Array.from(oldScript.attributes)) {
      fresh.setAttribute(attr.name, attr.value)
    }
    // Mark BEFORE insertion so a synchronous inline script that triggers another render does
    // not see this node as un-run.
    fresh.setAttribute(RAN_MARKER_ATTR, '1')
    fresh.textContent = oldScript.textContent
    const hasSrc = oldScript.hasAttribute('src') && oldScript.getAttribute('src') !== ''
    if (!hasSrc) {
      // Inline authored script: stamp the per-render nonce so the CSP allows execution.
      // Inserting the node runs it synchronously, in document order.
      fresh.setAttribute('nonce', nonce)
      oldScript.replaceWith(fresh)
    } else {
      // External include: force ordered (non-async) loading and AWAIT it before moving on,
      // so a following script can read globals this include defines.
      fresh.async = false
      const loaded = new Promise<void>((resolve) => {
        fresh.onload = () => resolve()
        // Resolve on error too: a missing authored global is reported elsewhere, and a
        // failed include should not wedge the render pipeline.
        fresh.onerror = () => resolve()
      })
      oldScript.replaceWith(fresh)
      await loaded
    }
  }
}
