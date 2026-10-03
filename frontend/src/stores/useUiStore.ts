import { create } from 'zustand'
import type { SortField } from '../types/metadata'
import { loadTheme, saveTheme, type Theme } from '../utils/theme'

export type ViewMode = 'studio' | 'timeline' | 'map' | 'kanban' | 'analytics'
export type ToastKind = 'success' | 'error'
export type JobDialogKind = 'index' | 'sync'

interface UiState {
  /** Applied to the document by App (an effect), not by the store: updaters stay free of side effects. */
  theme: Theme
  activeView: ViewMode
  lightsOut: boolean
  sidebarOpen: boolean
  inspectorOpen: boolean
  gridItemSize: number
  /** Which photo the inspector shows. The record itself comes from the photos query, so it is never stale. */
  inspectedHash: string | null
  lightboxIndex: number | null
  commandPaletteOpen: boolean
  /** Which folder dialog is open: Scan (index) or Sync. */
  jobDialog: JobDialogKind | null
  searchQuery: string
  filterCameras: string[]
  filterTags: string[]
  filterCollection: string
  filterTimeframe: string
  /** Server-side sort of the library (PMO-27). */
  sortBy: SortField
  sortOrder: 'asc' | 'desc'
  radiusKm: number
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
  setSearchQuery: (q: string) => void
  toggleCameraFilter: (camera: string) => void
  toggleTagFilter: (tag: string) => void
  setCollectionFilter: (col: string) => void
  setTimeframeFilter: (year: string) => void
  setSort: (sortBy: SortField, sortOrder: 'asc' | 'desc') => void
  setRadiusKm: (r: number) => void
  resetFilters: () => void
  showToast: (msg: string, kind?: ToastKind) => void
  hideToast: () => void
}

let toastTimer: ReturnType<typeof setTimeout> | null = null

export const useUiStore = create<UiState>((set, get) => ({
  theme: loadTheme() ?? 'dark',
  activeView: 'studio',
  lightsOut: false,
  sidebarOpen: true,
  inspectorOpen: true,
  gridItemSize: 220,
  inspectedHash: null,
  lightboxIndex: null,
  commandPaletteOpen: false,
  jobDialog: null,
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  sortBy: 'captured_at',
  sortOrder: 'desc',
  radiusKm: 25,
  toastMessage: null,
  toastKind: 'success',

  setTheme: (theme) => {
    saveTheme(theme)
    set({ theme })
  },

  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),

  setActiveView: (activeView) => set({ activeView }),
  toggleLightsOut: () => set((state) => ({ lightsOut: !state.lightsOut })),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleInspector: () => set((state) => ({ inspectorOpen: !state.inspectorOpen })),
  setGridItemSize: (gridItemSize) => set({ gridItemSize }),
  setInspectedHash: (inspectedHash) => set({ inspectedHash }),
  setLightboxIndex: (lightboxIndex) => set({ lightboxIndex }),
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
  setJobDialog: (jobDialog) => set({ jobDialog }),
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
  setTimeframeFilter: (filterTimeframe) => set({ filterTimeframe }),
  setSort: (sortBy, sortOrder) => set({ sortBy, sortOrder }),
  setRadiusKm: (radiusKm) => set({ radiusKm }),

  resetFilters: () =>
    set({
      filterCameras: [],
      filterTags: [],
      filterCollection: 'all',
      filterTimeframe: 'all',
      searchQuery: '',
    }),

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
