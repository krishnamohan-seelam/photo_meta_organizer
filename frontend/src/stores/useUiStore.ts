import { create } from 'zustand'
import { loadTheme, saveTheme, type Theme } from '../utils/theme'
import { isBoolean, isNumber, loadPref, savePref } from '../utils/prefs'
import { DEFAULT_GAP_HOURS, GAP_PRESETS } from '../utils/chapters'

export type ToastKind = 'success' | 'error'

/** A button on a toast, such as Undo. */
export interface ToastAction {
  label: string
  run: () => void
}
export type JobDialogKind = 'index' | 'sync'
export type LibraryLayout = 'grid' | 'table'

/** Row height of the justified Library grid (FR-1c.5). */
export const ROW_HEIGHT_MIN = 140
export const ROW_HEIGHT_MAX = 340
const ROW_HEIGHT_DEFAULT = 210

const SIDEBAR_KEY = 'pmo_library_panel'
const INSPECTOR_KEY = 'pmo_details_panel'
const ROW_HEIGHT_KEY = 'pmo_row_height'
const LAYOUT_KEY = 'pmo_library_layout'
const GAP_KEY = 'pmo_chapter_gap_hours'
const isGap = (v: unknown): v is number => isNumber(v) && GAP_PRESETS.some((p) => p.hours === v)
const isLayout = (v: unknown): v is LibraryLayout => v === 'grid' || v === 'table'

function narrowWindow(): boolean {
  try {
    return window.matchMedia('(max-width: 1100px)').matches
  } catch {
    return false
  }
}

const isRowHeight = (v: unknown): v is number => isNumber(v) && v >= ROW_HEIGHT_MIN && v <= ROW_HEIGHT_MAX

interface UiState {
  /** Applied to the document by App (an effect), not by the store: updaters stay free of side effects. */
  theme: Theme
  lightsOut: boolean
  sidebarOpen: boolean
  inspectorOpen: boolean
  /** Target row height of the Library grid, in px. */
  gridItemSize: number
  lightboxIndex: number | null
  commandPaletteOpen: boolean
  /** Which folder dialog is open: Scan (index) or Sync. */
  jobDialog: JobDialogKind | null
  /** The AI setup dialog (model download, analysis). */
  aiDialogOpen: boolean
  duplicatesDialogOpen: boolean
  reviewDialogOpen: boolean
  removedDialogOpen: boolean
  foldersDialogOpen: boolean
  /** Library view layout (FR-2c.1). */
  libraryLayout: LibraryLayout
  /** First photo in view, so switching layout keeps the scroll position. */
  topPhotoIndex: number
  /** Hours between photos that start a new Timeline chapter (FR-3.10). */
  chapterGapHours: number
  toastMessage: string | null
  toastKind: ToastKind
  toastAction: ToastAction | null

  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  toggleLightsOut: () => void
  toggleSidebar: () => void
  toggleInspector: () => void
  setGridItemSize: (size: number) => void
  setLightboxIndex: (idx: number | null) => void
  setCommandPaletteOpen: (open: boolean) => void
  setJobDialog: (kind: JobDialogKind | null) => void
  setAiDialogOpen: (open: boolean) => void
  setDuplicatesDialogOpen: (open: boolean) => void
  setReviewDialogOpen: (open: boolean) => void
  setRemovedDialogOpen: (open: boolean) => void
  setFoldersDialogOpen: (open: boolean) => void
  setLibraryLayout: (layout: LibraryLayout) => void
  setTopPhotoIndex: (index: number) => void
  setChapterGapHours: (hours: number) => void
  /** Shortcut overlay (`?`). */
  shortcutsOpen: boolean
  setShortcutsOpen: (open: boolean) => void
  showToast: (msg: string, kind?: ToastKind, action?: ToastAction) => void
  hideToast: () => void
}

let toastTimer: ReturnType<typeof setTimeout> | null = null

export const useUiStore = create<UiState>((set, get) => ({
  theme: loadTheme() ?? 'dark',
  lightsOut: false,
  sidebarOpen: loadPref(SIDEBAR_KEY, isBoolean) ?? true,
  inspectorOpen: loadPref(INSPECTOR_KEY, isBoolean) ?? true,
  gridItemSize: loadPref(ROW_HEIGHT_KEY, isRowHeight) ?? ROW_HEIGHT_DEFAULT,
  lightboxIndex: null,
  commandPaletteOpen: false,
  jobDialog: null,
  aiDialogOpen: false,
  duplicatesDialogOpen: false,
  reviewDialogOpen: false,
  removedDialogOpen: false,
  foldersDialogOpen: false,
  libraryLayout: loadPref(LAYOUT_KEY, isLayout) ?? 'grid',
  topPhotoIndex: 0,
  chapterGapHours: loadPref(GAP_KEY, isGap) ?? DEFAULT_GAP_HOURS,
  shortcutsOpen: false,
  toastMessage: null,
  toastKind: 'success',
  toastAction: null,

  setTheme: (theme) => {
    saveTheme(theme)
    set({ theme })
  },

  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),

  toggleLightsOut: () => set((state) => ({ lightsOut: !state.lightsOut })),
  // Below 1100 px the panels float over the photos (G-7): opening one there closes the other.
  toggleSidebar: () => {
    const sidebarOpen = !get().sidebarOpen
    savePref(SIDEBAR_KEY, sidebarOpen)
    set(sidebarOpen && narrowWindow() ? { sidebarOpen, inspectorOpen: false } : { sidebarOpen })
  },
  toggleInspector: () => {
    const inspectorOpen = !get().inspectorOpen
    savePref(INSPECTOR_KEY, inspectorOpen)
    set(inspectorOpen && narrowWindow() ? { inspectorOpen, sidebarOpen: false } : { inspectorOpen })
  },
  setGridItemSize: (size) => {
    const gridItemSize = Math.min(ROW_HEIGHT_MAX, Math.max(ROW_HEIGHT_MIN, size))
    savePref(ROW_HEIGHT_KEY, gridItemSize)
    set({ gridItemSize })
  },
  setLightboxIndex: (lightboxIndex) => set({ lightboxIndex }),
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
  setJobDialog: (jobDialog) => set({ jobDialog }),
  setAiDialogOpen: (aiDialogOpen) => set({ aiDialogOpen }),
  setDuplicatesDialogOpen: (duplicatesDialogOpen) => set({ duplicatesDialogOpen }),
  setReviewDialogOpen: (reviewDialogOpen) => set({ reviewDialogOpen }),
  setRemovedDialogOpen: (removedDialogOpen) => set({ removedDialogOpen }),
  setFoldersDialogOpen: (foldersDialogOpen) => set({ foldersDialogOpen }),

  setLibraryLayout: (libraryLayout) => {
    savePref(LAYOUT_KEY, libraryLayout)
    set({ libraryLayout })
  },
  setTopPhotoIndex: (topPhotoIndex) => set({ topPhotoIndex }),
  setChapterGapHours: (chapterGapHours) => {
    savePref(GAP_KEY, chapterGapHours)
    set({ chapterGapHours })
  },
  setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),

  showToast: (toastMessage, toastKind = 'success', toastAction) => {
    // One timer: an older toast's timeout must not dismiss the newer one early (an error would vanish).
    if (toastTimer) clearTimeout(toastTimer)
    set({ toastMessage, toastKind, toastAction: toastAction ?? null })
    // A toast with an action (Undo) stays long enough to be used.
    const visibleMs = toastAction ? 15000 : toastKind === 'error' ? 6000 : 2500
    toastTimer = setTimeout(() => {
      toastTimer = null
      set({ toastMessage: null, toastAction: null })
    }, visibleMs)
  },

  hideToast: () => {
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = null
    set({ toastMessage: null, toastAction: null })
  },
}))
