// Keep a reading position through a live update and its short-lived layout work. This is
// deliberately bounded: it must never become a scroll lock or an automatic follow mode.
export function createScrollPreserver(root: HTMLElement, onSettled: () => void) {
  let cancelCurrent: (() => void) | undefined

  function begin(): () => void {
    cancelCurrent?.()
    const scrolling = document.scrollingElement as HTMLElement
    const candidates = Array.from(root.querySelectorAll<HTMLElement>('*'))
    const panels = candidates.filter(el => {
      if (!el.clientHeight) return false
      const style = getComputedStyle(el)
      return (el.scrollHeight > el.clientHeight && /auto|scroll/.test(style.overflowY)) ||
        (el.scrollWidth > el.clientWidth && /auto|scroll/.test(style.overflowX))
    })
    const key = (el: Element) => el.hasAttribute('data-morph-key')
      ? `key:${el.getAttribute('data-morph-key')}` : el.id ? `id:${el.id}` : undefined
    const anchors = candidates.filter(el => {
      if (!key(el) || panels.includes(el)) return false
      for (let node: HTMLElement | null = el; node && node !== root; node = node.parentElement) {
        if (/fixed|sticky/.test(getComputedStyle(node).position)) return false
      }
      return true
    })
    const snapshots = [scrolling, ...panels].map(container => {
      const page = container === scrolling
      const top = page ? 0 : container.getBoundingClientRect().top + container.clientTop
      const height = page ? window.innerHeight : container.clientHeight
      const visible = anchors.filter(el => {
        if (!page && !container.contains(el)) return false
        // An inner panel owns its own reading anchor.
        if (panels.some(panel => panel !== container && panel.contains(el) &&
          (page || container.contains(panel)))) return false
        const rect = el.getBoundingClientRect()
        return rect.height > 0 && rect.bottom > top && rect.top < top + height
      }).sort((a, b) => Math.abs(a.getBoundingClientRect().top - top) -
        Math.abs(b.getBoundingClientRect().top - top))
      const anchor = visible[0]
      return { container, page, containerKey: key(container), anchor,
        anchorKey: anchor && key(anchor), offset: anchor && anchor.getBoundingClientRect().top - top,
        x: container.scrollLeft, y: container.scrollTop }
    })
    let active = true
    let frame = 0
    const resolve = (el: HTMLElement | undefined, identity: string | undefined) => {
      if (el?.isConnected) return el
      if (!identity) return undefined
      return Array.from(root.querySelectorAll<HTMLElement>('[id], [data-morph-key]'))
        .find(node => key(node) === identity)
    }
    function restore() {
      if (!active) return
      for (const state of snapshots) {
        const container = state.page ? scrolling : resolve(state.container, state.containerKey)
        if (!container) continue
        const anchor = resolve(state.anchor, state.anchorKey)
        if (!state.page) sizes.observe(container)
        if (anchor) sizes.observe(anchor)
        const top = state.page ? 0 : container.getBoundingClientRect().top + container.clientTop
        const y = anchor && state.offset !== undefined && container.contains(anchor)
          ? container.scrollTop + anchor.getBoundingClientRect().top - top - state.offset
          : state.y
        if (Math.abs(container.scrollTop - y) > 0.5 || container.scrollLeft !== state.x) {
          container.scrollTo({ left: state.x, top: y, behavior: 'instant' })
        }
      }
    }
    function schedule() {
      if (active && !frame) frame = requestAnimationFrame(() => { frame = 0; restore() })
    }
    const mutations = new MutationObserver(schedule)
    mutations.observe(root, { childList: true, subtree: true, attributes: true, characterData: true })
    const sizes = new ResizeObserver(schedule)
    sizes.observe(root)
    panels.forEach(panel => sizes.observe(panel))
    const events = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const
    function cancel() {
      if (!active) return
      active = false
      cancelAnimationFrame(frame)
      clearTimeout(timeout)
      mutations.disconnect()
      sizes.disconnect()
      events.forEach(event => window.removeEventListener(event, cancel, true))
      if (cancelCurrent === cancel) cancelCurrent = undefined
      onSettled()
    }
    events.forEach(event => window.addEventListener(event, cancel, { capture: true, passive: true }))
    const timeout = window.setTimeout(cancel, 1200)
    cancelCurrent = cancel
    // Call after the synchronous morph and again when render hooks have run. An obsolete
    // callback is inert, including when user input or a later update canceled this snapshot.
    return () => { restore(); schedule() }
  }
  return { begin, cancel: () => cancelCurrent?.(), get active() { return !!cancelCurrent } }
}
