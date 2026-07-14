import { describe, expect, it } from 'vitest'
import {
  notebookPaletteForTheme,
  notebookThemeFromColorKind,
} from '../notebook/theme'

describe('notebook theme mapping', () => {
  it('maps light theme kinds to latte', () => {
    expect(notebookThemeFromColorKind(1)).toEqual({ kind: 'light', flavor: 'latte' })
    expect(notebookThemeFromColorKind(4)).toEqual({ kind: 'light', flavor: 'latte' })
  })

  it('maps dark and high-contrast-dark kinds to mocha', () => {
    expect(notebookThemeFromColorKind(2)).toEqual({ kind: 'dark', flavor: 'mocha' })
    expect(notebookThemeFromColorKind(3)).toEqual({ kind: 'dark', flavor: 'mocha' })
  })

  it('returns distinct palettes for light and dark themes', () => {
    const light = notebookPaletteForTheme({ kind: 'light', flavor: 'latte' })
    const dark = notebookPaletteForTheme({ kind: 'dark', flavor: 'mocha' })

    expect(light.bg).not.toBe(dark.bg)
    expect(light.text).not.toBe(dark.text)
  })
})
