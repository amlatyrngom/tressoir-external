import { vi } from 'vitest'

// ---------------------------------------------------------------------------
// EventEmitter mock
// ---------------------------------------------------------------------------

export class EventEmitter {
  private handlers: Function[] = []
  event = (handler: Function) => {
    this.handlers.push(handler)
    return { dispose: () => { this.handlers = this.handlers.filter(h => h !== handler) } }
  }
  fire(data: any) { this.handlers.forEach(h => h(data)) }
  dispose() { this.handlers = [] }
}

// ---------------------------------------------------------------------------
// Uri mock
// ---------------------------------------------------------------------------

export const Uri = {
  file: (path: string) => ({ scheme: 'file', fsPath: path, path, toString: () => `file://${path}` }),
  parse: (str: string) => ({ scheme: 'file', fsPath: str, path: str, toString: () => str }),
  joinPath: (base: any, ...segments: string[]) => {
    const fullPath = [base.fsPath || base.path, ...segments].join('/')
    return { scheme: 'file', fsPath: fullPath, path: fullPath, toString: () => `file://${fullPath}` }
  },
}

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const StatusBarAlignment = { Left: 1, Right: 2 }
export const ConfigurationTarget = { Global: 1, Workspace: 2, WorkspaceFolder: 3 }
export const ViewColumn = { Active: -1, Beside: -2, One: 1, Two: 2 }
export enum TextEditorRevealType { Default = 0, InCenter = 1, InCenterIfOutsideViewport = 2, AtTop = 3 }
export const ColorThemeKind = { Light: 1, Dark: 2, HighContrast: 3, HighContrastLight: 4 }
export const FileType = { Unknown: 0, File: 1, Directory: 2, SymbolicLink: 64 }

// ---------------------------------------------------------------------------
// Classes
// ---------------------------------------------------------------------------

export class ThemeIcon {
  constructor(public readonly id: string) {}
}

export class ThemeColor {
  constructor(public readonly id: string) {}
}

export class RelativePattern {
  constructor(public readonly base: string, public readonly pattern: string) {}
}

export class Position {
  constructor(public readonly line: number, public readonly character: number) {}
}

export class Range {
  constructor(public readonly start: Position, public readonly end: Position) {}
}

export class Selection {
  constructor(public readonly anchor: Position, public readonly active: Position) {}
  get start() {
    if (this.anchor.line < this.active.line) return this.anchor
    if (this.anchor.line > this.active.line) return this.active
    return this.anchor.character <= this.active.character ? this.anchor : this.active
  }
  get end() {
    if (this.anchor.line > this.active.line) return this.anchor
    if (this.anchor.line < this.active.line) return this.active
    return this.anchor.character >= this.active.character ? this.anchor : this.active
  }
  get isEmpty() {
    return this.anchor.line === this.active.line && this.anchor.character === this.active.character
  }
}

// ---------------------------------------------------------------------------
// Workspace mock
// ---------------------------------------------------------------------------

const mockConfig = new Map<string, any>()
const changeTextEmitter = new EventEmitter()
const saveTextEmitter = new EventEmitter()
const colorThemeEmitter = new EventEmitter()
const activeEditorEmitter = new EventEmitter()

export class WorkspaceEdit {
  entries: Array<{ uri: any; range: any; newText: string }> = []
  replace(uri: any, range: any, newText: string) {
    this.entries.push({ uri, range, newText })
  }
}

export const workspace = {
  getConfiguration: vi.fn((section?: string) => ({
    get: vi.fn((key: string, defaultValue?: any) => mockConfig.get(`${section}.${key}`) ?? defaultValue),
    update: vi.fn(async (key: string, value: any) => { mockConfig.set(`${section}.${key}`, value) }),
    has: vi.fn((key: string) => mockConfig.has(`${section}.${key}`)),
    inspect: vi.fn((_key: string) => ({ globalValue: undefined })),
  })),
  workspaceFolders: [] as any[],
  textDocuments: [] as any[],
  onDidChangeConfiguration: vi.fn(() => ({ dispose: vi.fn() })),
  onDidChangeTextDocument: vi.fn((handler: Function) => changeTextEmitter.event(handler)),
  onDidSaveTextDocument: vi.fn((handler: Function) => saveTextEmitter.event(handler)),
  openTextDocument: vi.fn(),
  applyEdit: vi.fn(async (_edit: WorkspaceEdit) => true),
  updateWorkspaceFolders: vi.fn(() => true),
  createFileSystemWatcher: vi.fn(() => ({
    onDidChange: vi.fn(() => ({ dispose: vi.fn() })),
    onDidCreate: vi.fn(() => ({ dispose: vi.fn() })),
    onDidDelete: vi.fn(() => ({ dispose: vi.fn() })),
    dispose: vi.fn(),
  })),
  fs: {
    readFile: vi.fn(async (uri: any) => {
      const data = mockFiles.get(uri.fsPath || uri.path)
      if (data == null) {
        const err: any = new Error('ENOENT')
        err.code = 'FileNotFound'
        throw err
      }
      return new TextEncoder().encode(data)
    }),
    writeFile: vi.fn(async (uri: any, bytes: Uint8Array) => {
      mockFiles.set(uri.fsPath || uri.path, new TextDecoder().decode(bytes))
    }),
    readDirectory: vi.fn(async (uri: any) => {
      const base = (uri.fsPath || uri.path).replace(/\/$/, '')
      const out: Array<[string, number]> = []
      for (const p of mockFiles.keys()) {
        const dir = p.slice(0, p.lastIndexOf('/'))
        if (dir === base) {
          out.push([p.slice(p.lastIndexOf('/') + 1), FileType.File])
        }
      }
      return out
    }),
  },
}

/** In-memory file store for the workspace.fs mock (keyed by fsPath). */
const mockFiles = new Map<string, string>()
export function __seedFile(fsPath: string, content: string) {
  mockFiles.set(fsPath, content)
}
export function __readFile(fsPath: string): string | undefined {
  return mockFiles.get(fsPath)
}
export function __resetFs() {
  mockFiles.clear()
}

/** Helper: seed config values for tests */
export function __setMockConfig(section: string, key: string, value: any) {
  mockConfig.set(`${section}.${key}`, value)
}

/** Helper: clear all mock config */
export function __clearMockConfig() {
  mockConfig.clear()
}

export function __fireDidChangeTextDocument(data: any) {
  changeTextEmitter.fire(data)
}

export function __fireDidSaveTextDocument(data: any) {
  saveTextEmitter.fire(data)
}

// ---------------------------------------------------------------------------
// Window mock
// ---------------------------------------------------------------------------

export const window = {
  activeColorTheme: { kind: 2 },  // Dark
  onDidChangeActiveColorTheme: vi.fn((handler: Function) => colorThemeEmitter.event(handler)),
  onDidChangeActiveTextEditor: vi.fn((handler: Function) => activeEditorEmitter.event(handler)),
  createOutputChannel: vi.fn(() => ({
    appendLine: vi.fn(),
    append: vi.fn(),
    show: vi.fn(),
    dispose: vi.fn(),
    clear: vi.fn(),
  })),
  createStatusBarItem: vi.fn(() => ({
    text: '',
    tooltip: '',
    command: '',
    show: vi.fn(),
    hide: vi.fn(),
    dispose: vi.fn(),
  })),
  showInformationMessage: vi.fn(() => Promise.resolve(undefined)),
  showErrorMessage: vi.fn(() => Promise.resolve(undefined)),
  showWarningMessage: vi.fn(() => Promise.resolve(undefined)),
  showTextDocument: vi.fn(),
  createTextEditorDecorationType: vi.fn(() => ({ dispose: vi.fn() })),
  createWebviewPanel: vi.fn(() => {
    const panel = {
      webview: {
        html: '',
        onDidReceiveMessage: vi.fn((_handler: Function) => ({ dispose: vi.fn() })),
        postMessage: vi.fn(),
        asWebviewUri: vi.fn((uri: any) => uri),
        options: {} as any,
        cspSource: 'https://test.csp',
      },
      reveal: vi.fn(),
      dispose: vi.fn(),
      onDidDispose: vi.fn((_handler: Function) => ({ dispose: vi.fn() })),
      iconPath: undefined as any,
      visible: true,
    }
    return panel
  }),
  registerWebviewViewProvider: vi.fn(() => ({ dispose: vi.fn() })),
  registerCustomEditorProvider: vi.fn(() => ({ dispose: vi.fn() })),
  activeTextEditor: null as any,
}

export function __fireDidChangeActiveColorTheme(theme: any) {
  window.activeColorTheme = theme
  colorThemeEmitter.fire(theme)
}

export function __fireDidChangeActiveTextEditor(editor: any) {
  window.activeTextEditor = editor
  activeEditorEmitter.fire(editor)
}

// ---------------------------------------------------------------------------
// Commands mock
// ---------------------------------------------------------------------------

export const commands = {
  registerCommand: vi.fn((_cmd: string, _handler: Function) => ({ dispose: vi.fn() })),
  executeCommand: vi.fn(),
}

// ---------------------------------------------------------------------------
// Extensions mock
// ---------------------------------------------------------------------------

export const extensions = {
  getExtension: vi.fn(),
}

// ---------------------------------------------------------------------------
// Default export
// ---------------------------------------------------------------------------

export default {
  EventEmitter,
  Uri,
  StatusBarAlignment,
  ConfigurationTarget,
  ViewColumn,
  TextEditorRevealType,
  ColorThemeKind,
  FileType,
  ThemeIcon,
  Position,
  Range,
  Selection,
  WorkspaceEdit,
  workspace,
  window,
  commands,
  extensions,
  ThemeColor,
  RelativePattern,
}
