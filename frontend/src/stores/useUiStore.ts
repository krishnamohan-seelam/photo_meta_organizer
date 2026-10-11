import { create } from 'zustand'
import type { BoundingBox, SortField } from '../types/metadata'
import { loadTheme, saveTheme, type Theme } from '../utils/theme'
import { isBoolean, isNumber, loadPref, savePref } from '../utils/prefs'
import { EMPTY_QUERY_FILTERS, type DateRange, type QueryFilters } from '../utils/query'
import { DEFAULT_GAP_HOURS, GAP_PRESETS } from '../utils/chapters'

export type ViewMode = 'studio' | 'timeline' | 'map' | 'kanban' | 'analytics'
export type ToastKind = 'success' | 'error'
export type JobDialogKind = 'index' | 'sync'
export type LibraryLayout = 'grid' | 'table'
/** A search by meaning: free text, or "photos like this one". Replaces the Library's list while set. */
export type SemanticQuery = { kind: 'text'; text: string } | { kind: 'like'; hash: string; name: string }

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
  activeView: ViewMode
  lightsOut: boolean
  sidebarOpen: boolean
  inspectorOpen: boolean
  /** Target row height of the Library grid, in px. */
  gridItemSize: number
  /** Which photo the inspector shows. The record itself comes from the photos query, so it is never stale. */
  inspectedHash: string | null
  lightboxIndex: number | null
  commandPaletteOpen: boolean
  /** Which folder dialog is open: Scan (index) or Sync. */
  jobDialog: JobDialogKind | null
  /** The AI setup dialog (model download, analysis). */
  aiDialogOpen: boolean
  semantic: SemanticQuery | null
  searchQuery: string
  filterCameras: string[]
  filterTags: string[]
  filterCollection: string
  filterTimeframe: string
  /** Exact star rating 1-5, or null for any. */
  filterRating: number | null
  /** Camera model substring, or ''. */
  filterModel: string
  filterHasLocation: boolean | null
  /** A capture-date range; never set together with a year (`filterTimeframe`). */
  filterDateRange: DateRange | null
  /** Library view layout (FR-2c.1). */
  libraryLayout: LibraryLayout
  /** First photo in view, so switching layout keeps the scroll position. */
  topPhotoIndex: number
  /** Hours between photos that start a new Timeline chapter (FR-3.10). */
  chapterGapHours: number
  /** Server-side sort of the library (PMO-27). */
  sortBy: SortField
  sortOrder: 'asc' | 'desc'
  /** Map area picked on the Map view; narrows the Library like any other filter. */
  filterArea: BoundingBox | null
  toastMessage: string | null
  toastKind: ToastKind

  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  setActiveView: (view: ViewMode) => void
  toggleLightsOut: () => void
  toggleSidebar: () => void
  toggleInspector: () => void
  setGridItemSize: (size: number) => void
  setInspectedHash: (hash: string | null) => void
  setLightboxIndex: (idx: number | null) => void
  setCommandPaletteOpen: (open: boolean) => void
  setJobDialog: (kind: JobDialogKind | null) => void
  setAiDialogOpen: (open: boolean) => void
  setSemantic: (query: SemanticQuery | null) => void
  setSearchQuery: (q: string) => void
  toggleCameraFilter: (camera: string) => void
  toggleTagFilter: (tag: string) => void
  setCollectionFilter: (col: string) => void
  setTimeframeFilter: (year: string) => void
  setRatingFilter: (rating: number | null) => void
  setDateRangeFilter: (range: DateRange | null) => void
  /** Replace every query-bar filter at once (FR-2a.1). */
  applyQueryFilters: (filters: QueryFilters) => void
  setLibraryLayout: (layout: LibraryLayout) => void
  setTopPhotoIndex: (index: number) => void
  setChapterGapHours: (hours: number) => void
  /** Shortcut overlay (`?`). */
  shortcutsOpen: boolean
  setShortcutsOpen: (open: boolean) => void
  setSort: (sortBy: SortField, sortOrder: 'asc' | 'desc') => void
  setFilterArea: (area: BoundingBox | null) => void
  resetFilters: () => void
  showToast: (msg: string, kind?: ToastKind) => void
  hideToast: () => void
}

let toastTimer: ReturnType<typeof setTimeout> | null = null

export const useUiStore = create<UiState>((set, get) => ({
  theme: loadTheme() ?? 'dark',
  activeView: 'studio',
  lightsOut: false,
  sidebarOpen: loadPref(SIDEBAR_KEY, isBoolean) ?? true,
  inspectorOpen: loadPref(INSPECTOR_KEY, isBoolean) ?? true,
  gridItemSize: loadPref(ROW_HEIGHT_KEY, isRowHeight) ?? ROW_HEIGHT_DEFAULT,
  inspectedHash: null,
  lightboxIndex: null,
  commandPaletteOpen: false,
  jobDialog: null,
  aiDialogOpen: false,
  semantic: null,
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  filterRating: null,
  filterModel: '',
  filterHasLocation: null,
  filterDateRange: null,
  libraryLayout: loadPref(LAYOUT_KEY, isLayout) ?? 'grid',
  topPhotoIndex: 0,
  chapterGapHours: loadPref(GAP_KEY, isGap) ?? DEFAULT_GAP_HOURS,
  shortcutsOpen: false,
  sortBy: 'captured_at',
  sortOrder: 'desc',
  filterArea: null,
  toastMessage: null,
  toastKind: 'success',

  setTheme: (theme) => {
    saveTheme(theme)
    set({ theme })
  },

  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),

  setActiveView: (activeView) => set({ activeView }),
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
  setInspectedHash: (inspectedHash) => set({ inspectedHash }),
  setLightboxIndex: (lightboxIndex) => set({ lightboxIndex }),
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
  setJobDialog: (jobDialog) => set({ jobDialog }),
  setAiDialogOpen: (aiDialogOpen) => set({ aiDialogOpen }),
  setSemantic: (semantic) => set({ semantic }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),

  toggleCameraFilter: (camera) =>
    set((state) => ({
      filterCameras: state.filterCameras.includes(camera)
        ? state.filterCameras.filter((c) => c !== camera)
        : [...state.filterCameras, camera],
    })),

  toggleTagFilter: (tag) =>
    set((state) => ({
      filterTags: state.filterTags.includes(tag)
        ? state.filterTags.filter((t) => t !== tag)
        : [...state.filterTags, tag],
    })),

  setCollectionFilter: (filterCollection) => set({ filterCollection }),
  // A year and a date range are mutually exclusive (FR-2a.2): setting one clears the other.
  setTimeframeFilter: (filterTimeframe) => set({ filterTimeframe, ...(filterTimeframe !== 'all' && { filterDateRange: null }) }),
  setRatingFilter: (filterRating) => set({ filterRating }),
  setDateRangeFilter: (filterDateRange) => set({ filterDateRange, ...(filterDateRange && { filterTimeframe: 'all' }) }),
  applyQueryFilters: (f) =>
    set({
      searchQuery: f.searchQuery,
      filterCameras: f.filterCameras,
      filterTags: f.filterTags,
      filterCollection: f.filterCollection,
      filterTimeframe: f.filterDateRange ? 'all' : f.filterTimeframe,
      filterRating: f.filterRating,
      filterModel: f.filterModel,
      filterHasLocation: f.filterHasLocation,
      filterDateRange: f.filterDateRange,
    }),
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
  setSort: (sortBy, sortOrder) => set({ sortBy, sortOrder }),
  setFilterArea: (filterArea) => set({ filterArea }),

  resetFilters: () => {
    get().applyQueryFilters(EMPTY_QUERY_FILTERS)
    set({ filterArea: null, semantic: null })
  },

  showToast: (toastMessage, toastKind = 'success') => {
    // One timer: an older toast's timeout must not dismiss the newer one early (an error would vanish).
    if (toastTimer) clearTimeout(toastTimer)
    set({ toastMessage, toastKind })
    toastTimer = setTimeout(() => {
      toastTimer = null
      set({ toastMessage: null })
    }, toastKind === 'error' ? 6000 : 2500)
  },

  hideToast: () => {
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = null
    set({ toastMessage: null })
  },
}))
