import * as vscode from 'vscode'
import {
  registerTressoirNotebookEditor,
  registerTressoirNotebookMdEditor,
} from './notebook/provider'
import { clearNotebookState } from './notebook/state'

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(registerTressoirNotebookEditor(context))
  context.subscriptions.push(registerTressoirNotebookMdEditor(context))
}

export function deactivate(): void {
  clearNotebookState()
}
