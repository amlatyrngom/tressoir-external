export type NotebookThemeKind = 'light' | 'dark'
export type NotebookThemeFlavor = 'latte' | 'mocha'

export type NotebookThemeState = {
  kind: NotebookThemeKind
  flavor: NotebookThemeFlavor
}

export type NotebookThemePalette = {
  bg: string
  surface: string
  surfaceAlt: string
  border: string
  text: string
  muted: string
  accent: string
  selection: string
}

const LIGHT_THEME: NotebookThemePalette = {
  bg: '#eff1f5',
  surface: '#ffffff',
  surfaceAlt: '#e6e9ef',
  border: '#bcc0cc',
  text: '#4c4f69',
  muted: '#6c6f85',
  accent: '#1e66f5',
  selection: '#ccd0da',
}

const DARK_THEME: NotebookThemePalette = {
  bg: '#1e1e2e',
  surface: '#313244',
  surfaceAlt: '#181825',
  border: '#585b70',
  text: '#cdd6f4',
  muted: '#a6adc8',
  accent: '#89b4fa',
  selection: '#45475a',
}

export function notebookThemeFromColorKind(kind: number): NotebookThemeState {
  if (kind === 1 || kind === 4) {
    return {
      kind: 'light',
      flavor: 'latte',
    }
  }
  return {
    kind: 'dark',
    flavor: 'mocha',
  }
}

export function notebookPaletteForTheme(theme: NotebookThemeState): NotebookThemePalette {
  return theme.kind === 'light' ? LIGHT_THEME : DARK_THEME
}
