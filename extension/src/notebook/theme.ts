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
  codeSurface: string
  border: string
  text: string
  muted: string
  accent: string
  positive: string
  warning: string
  danger: string
  selection: string
}

const LIGHT_THEME: NotebookThemePalette = {
  bg: '#eff1f5',
  surface: '#ffffff',
  surfaceAlt: '#e6e9ef',
  codeSurface: '#e6e9ef',
  border: '#bcc0cc',
  text: '#4c4f69',
  muted: '#6c6f85',
  accent: '#1e66f5',
  positive: '#2f7657',
  warning: '#946115',
  danger: '#a33a3a',
  selection: '#ccd0da',
}

const DARK_THEME: NotebookThemePalette = {
  bg: '#1e1e2e',
  surface: '#313244',
  surfaceAlt: '#181825',
  codeSurface: '#111318',
  border: '#585b70',
  text: '#cdd6f4',
  muted: '#a6adc8',
  accent: '#89b4fa',
  positive: '#78bd96',
  warning: '#d4a85e',
  danger: '#e08383',
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
