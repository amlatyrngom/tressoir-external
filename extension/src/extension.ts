import * as vscode from 'vscode'
import {
  registerTressoirNotebookEditor,
  registerTressoirNotebookMdEditor,
} from './notebook/provider'
import { clearNotebookState } from './notebook/state'

export function activate(context: vscode.ExtensionContext): void {
  // The original Tressoir Bridge contributes and eagerly registers the same custom-editor
  // view types. Two providers cannot own one view type, and whichever extension loses the race
  // cannot render artifacts. Fail clearly instead of throwing an opaque duplicate-provider
  // activation error. The standalone installer also detects this conflict before installation.
  if (vscode.extensions.getExtension('tressoir.bridge')) {
    void vscode.window.showErrorMessage(
      'Tressoir Artifacts cannot start while the legacy Tressoir Bridge extension is enabled. ' +
        'Disable or uninstall tressoir.bridge, then reload the VS Code window.',
    )
    return
  }
  context.subscriptions.push(registerTressoirNotebookEditor(context))
  context.subscriptions.push(registerTressoirNotebookMdEditor(context))
}

export function deactivate(): void {
  clearNotebookState()
}
