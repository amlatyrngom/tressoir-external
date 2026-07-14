export type NotebookSelectionState = {
  path: string
  text: string
}

let activeNotebookDocument: string | null = null
let activeNotebookSelection: NotebookSelectionState | null = null

export function setActiveNotebookDocument(path: string | null): void {
  activeNotebookDocument = path
  if (path == null) {
    activeNotebookSelection = null
  }
}

export function getActiveNotebookDocument(): string | null {
  return activeNotebookDocument
}

export function setNotebookSelection(selection: NotebookSelectionState | null): void {
  activeNotebookSelection = selection && selection.text.length > 0 ? selection : null
  if (selection?.path) {
    activeNotebookDocument = selection.path
  }
}

export function getNotebookSelection(): NotebookSelectionState | null {
  return activeNotebookSelection
}

export function clearNotebookStateForPath(path: string): void {
  if (activeNotebookDocument === path) {
    activeNotebookDocument = null
  }
  if (activeNotebookSelection?.path === path) {
    activeNotebookSelection = null
  }
}

export function clearNotebookState(): void {
  activeNotebookDocument = null
  activeNotebookSelection = null
}
