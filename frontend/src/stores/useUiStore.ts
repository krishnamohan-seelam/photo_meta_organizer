import { create } from 'zustand'

export type ViewMode = 'studio' | 'timeline' | 'map' | 'kanban' | 'analytics'
export type ToastKind = 'success' | 'error'
export type JobDialogKind = 'index' | 'sync'

interface UiState {
  theme: 'dark' | 'light'
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
  filterCity: string
  radiusKm: number
  toastMessage: string | null
  toastKind: ToastKind

  setTheme: (theme: 'dark' | 'light') => void
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
  setCityFilter: (city: string) => void
  setRadiusKm: (r: number) => void
  resetFilters: () => void
  showToast: (msg: string, kind?: ToastKind) => void
  hideToast: () => void
}

const savedTheme = (typeof window !== 'undefined' && localStorage.getItem('pmo_theme')) as
  | 'dark'
  | 'light'
  | null

let toastTimer: ReturnType<typeof setTimeout> | null = null

export const useUiStore = create<UiState>((set) => ({
  theme: savedTheme || 'dark',
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
  filterCity: 'all',
  radiusKm: 25,
  toastMessage: null,
  toastKind: 'success',

  setTheme: (theme) => {
    localStorage.setItem('pmo_theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },

  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem('pmo_theme', next)
      document.documentElement.setAttribute('data-theme', next)
      return { theme: next }
    }),

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
  setCityFilter: (filterCity) => set({ filterCity }),
  setRadiusKm: (radiusKm) => set({ radiusKm }),

  resetFilters: () =>
    set({
      filterCameras: [],
      filterTags: [],
      filterCollection: 'all',
      filterTimeframe: 'all',
      filterCity: 'all',
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
