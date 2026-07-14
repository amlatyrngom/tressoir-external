import { beforeEach, describe, expect, it, vi } from 'vitest'

function context() {
  return {
    subscriptions: [] as Array<{ dispose?: () => void }>,
    extensionUri: { fsPath: '/tmp/tressoir-artifacts', path: '/tmp/tressoir-artifacts' },
  } as any
}

describe('artifact-only extension activation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
})
