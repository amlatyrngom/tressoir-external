// Native disclosure state is reader-owned runtime state. Keep it across an authored-source morph
// while allowing morphdom to continue updating the summary and nested body.
export function preserveDetailsState(fromEl: Element, toEl: Element): void {
  if (fromEl instanceof HTMLDetailsElement && toEl instanceof HTMLDetailsElement) {
    toEl.open = fromEl.open
    if (fromEl.open) {
      toEl.setAttribute('open', '')
    } else {
      toEl.removeAttribute('open')
    }
  }
}
