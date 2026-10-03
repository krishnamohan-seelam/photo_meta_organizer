export type Theme = 'dark' | 'light'

const KEY = 'pmo_theme'

/** The theme saved last time, or `null`. Storage may be unavailable (private mode, disabled, no window). */
export function loadTheme(): Theme | null {
  try {
    const saved = localStorage.getItem(KEY)
    return saved === 'dark' || saved === 'light' ? saved : null
  } catch {
    return null
  }
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // Remembering the theme is a convenience only.
  }
}
