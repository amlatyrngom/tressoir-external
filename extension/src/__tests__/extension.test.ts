import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as vscode from 'vscode'

function context() {
  return {
    subscriptions: [] as Array<{ dispose?: () => void }>,
    extensionUri: { fsPath: '/tmp/tressoir-artifacts', path: '/tmp/tressoir-artifacts' },
  } as any
}

describe('artifact-only extension activation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(vscode.extensions.getExtension).mockReturnValue(undefined)
  })

  it('registers both artifact custom editors and no commands', async () => {
    const vscode = await import('vscode')
    const { activate } = await import('../extension')

    activate(context())

    const registrations = vi.mocked(vscode.window.registerCustomEditorProvider).mock.calls
    expect(registrations.map(([viewType]) => viewType)).toEqual([
      'tressoir.notebookHtml',
      'tressoir.notebookMd',
    ])
    for (const registration of registrations) {
      expect(registration[2]).toEqual(
        expect.objectContaining({
          webviewOptions: expect.objectContaining({ retainContextWhenHidden: true }),
        }),
      )
    }
    expect(vscode.commands.registerCommand).not.toHaveBeenCalled()
    expect(vscode.window.registerWebviewViewProvider).not.toHaveBeenCalled()
  })

  it('reports the legacy bridge conflict instead of registering duplicate view types', async () => {
    const vscode = await import('vscode')
    const { activate } = await import('../extension')
    vi.mocked(vscode.extensions.getExtension).mockReturnValue({ id: 'tressoir.bridge' } as any)

    activate(context())

    expect(vscode.window.registerCustomEditorProvider).not.toHaveBeenCalled()
    expect(vscode.window.showErrorMessage).toHaveBeenCalledWith(
      expect.stringContaining('Disable or uninstall tressoir.bridge'),
    )
  })
})
