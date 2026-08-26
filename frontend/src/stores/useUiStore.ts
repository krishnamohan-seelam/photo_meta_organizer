import { create } from 'zustand'
import type { PhotoMetadata } from '../types/metadata'

export type ViewMode = 'studio' | 'timeline' | 'map' | 'kanban' | 'analytics'

interface UiState {
  theme: 'dark' | 'light'
  activeView: ViewMode
  lightsOut: boolean
  sidebarOpen: boolean
  inspectorOpen: boolean
  gridItemSize: number
  inspectedPhoto: PhotoMetadata | null
  lightboxIndex: number | null
  commandPaletteOpen: boolean
  searchQuery: string
  filterCameras: string[]
  filterTags: string[]
  filterCollection: string
  filterTimeframe: string
  filterCity: string
  radiusKm: number
  toastMessage: string | null

  setTheme: (theme: 'dark' | 'light') => void
  toggleTheme: () => void
  setActiveView: (view: ViewMode) => void
  toggleLightsOut: () => void
  toggleSidebar: () => void
  toggleInspector: () => void
  setGridItemSize: (size: number) => void
  setInspectedPhoto: (photo: PhotoMetadata | null) => void
  setLightboxIndex: (idx: number | null) => void
  setCommandPaletteOpen: (open: boolean) => void
  setSearchQuery: (q: string) => void
  toggleCameraFilter: (camera: string) => void
  toggleTagFilter: (tag: string) => void
  setCollectionFilter: (col: string) => void
  setTimeframeFilter: (year: string) => void
  setCityFilter: (city: string) => void
  setRadiusKm: (r: number) => void
  resetFilters: () => void
  showToast: (msg: string) => void
  hideToast: () => void
}

const savedTheme = (typeof window !== 'undefined' && localStorage.getItem('pmo_theme')) as
  | 'dark'
  | 'light'
  | null

export const useUiStore = create<UiState>((set) => ({
  theme: savedTheme || 'dark',
  activeView: 'studio',
  lightsOut: false,
  sidebarOpen: true,
  inspectorOpen: true,
  gridItemSize: 220,
  inspectedPhoto: null,
  lightboxIndex: null,
  commandPaletteOpen: false,
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  filterCity: 'all',
  radiusKm: 25,
  toastMessage: null,

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
  setInspectedPhoto: (inspectedPhoto) => set({ inspectedPhoto }),
  setLightboxIndex: (lightboxIndex) => set({ lightboxIndex }),
  setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
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

  showToast: (toastMessage) => {
    set({ toastMessage })
    setTimeout(() => {
      set({ toastMessage: null })
    }, 2500)
  },

  hideToast: () => set({ toastMessage: null }),
}))
