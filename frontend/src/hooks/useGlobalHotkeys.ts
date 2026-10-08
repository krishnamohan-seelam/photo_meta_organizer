import { useEffect } from 'react'
import { useUiStore } from '../stores/useUiStore'
import { shouldIgnoreHotkey } from '../utils/hotkeys'
import { VIEW_KEYS, dialogOpen } from '../utils/shortcuts'

/** id of the top bar's search input, focused by `/`. */
export const SEARCH_INPUT_ID = 'library-search'

/**
 * App-wide single-key shortcuts (FR-1b.3, Appendix B): views, panels, Lights Out, `/` and `?`.
 * Ignored while typing, with a modifier held, or while a dialog is open (G-8).
 */
export function useGlobalHotkeys(): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (shouldIgnoreHotkey(e) || dialogOpen()) return
      const state = useUiStore.getState()
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
      const view = VIEW_KEYS[key]
      if (view) {
        state.setActiveView(view)
      } else if (key === 'l') {
        state.toggleLightsOut()
      } else if (key === '\\' && state.activeView === 'studio') {
        state.toggleSidebar()
      } else if (key === 'i' && state.activeView === 'studio') {
        state.toggleInspector()
      } else if (key === 'v' && state.activeView === 'studio') {
        state.setLibraryLayout(state.libraryLayout === 'grid' ? 'table' : 'grid')
      } else if (key === '?') {
        state.setShortcutsOpen(true)
      } else if (key === '/') {
        const input = document.getElementById(SEARCH_INPUT_ID)
        if (!input) return
        input.focus()
      } else {
        return
      }
      e.preventDefault()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
