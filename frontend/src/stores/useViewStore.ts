import { create } from 'zustand'
import type { BoundingBox, SortField } from '../types/metadata'
import { EMPTY_QUERY_FILTERS, type DateRange, type QueryFilters } from '../utils/query'
import {
  DEFAULT_SORT,
  onlyPhotoDiffers,
  onlyTextDiffers,
  searchToState,
  stateToSearch,
  type SemanticQuery,
  type UrlState,
  type ViewMode,
  withForeignParams,
} from '../utils/urlState'

export type { SemanticQuery, ViewMode }

/**
 * The state the URL holds (ADR-003 R8): view, filters, sort, search by meaning and the inspected
 * photo. `startUrlSync` writes every change to the address bar and reads it back on Back/Forward,
 * so views and searches are linkable. Transient UI state lives in `useUiStore`.
 */
interface ViewState extends QueryFilters {
  activeView: ViewMode
  /** Which photo the inspector shows. The record itself comes from the photos query, so it is never stale. */
  inspectedHash: string | null
  semantic: SemanticQuery | null
  /** Server-side sort of the library (PMO-27). */
  sortBy: SortField
  sortOrder: 'asc' | 'desc'

  setActiveView: (view: ViewMode) => void
  setInspectedHash: (hash: string | null) => void
  setSemantic: (query: SemanticQuery | null) => void
  setAiTagFilter: (label: string | null) => void
  setSearchQuery: (q: string) => void
  toggleCameraFilter: (camera: string) => void
  toggleTagFilter: (tag: string) => void
  setCollectionFilter: (col: string) => void
  setTimeframeFilter: (year: string) => void
  setRatingFilter: (rating: number | null) => void
  setDateRangeFilter: (range: DateRange | null) => void
  /** Replace every query-bar filter at once (FR-2a.1). */
  applyQueryFilters: (filters: QueryFilters) => void
  setSort: (sortBy: SortField, sortOrder: 'asc' | 'desc') => void
  setFilterArea: (area: BoundingBox | null) => void
  resetFilters: () => void
}

function filtersState(f: QueryFilters): QueryFilters {
  return {
    searchQuery: f.searchQuery,
    filterCameras: f.filterCameras,
    filterTags: f.filterTags,
    filterCollection: f.filterCollection,
    filterTimeframe: f.filterDateRange ? 'all' : f.filterTimeframe,
    filterRating: f.filterRating,
    filterModel: f.filterModel,
    filterHasLocation: f.filterHasLocation,
    filterDateRange: f.filterDateRange,
    filterArea: f.filterArea ?? null,
    filterAiTag: f.filterAiTag ?? null,
    filterNear: f.filterNear ?? null,
    filterDuplicates: f.filterDuplicates ?? null,
  }
}

export const useViewStore = create<ViewState>((set, get) => ({
  ...filtersState(EMPTY_QUERY_FILTERS),
  activeView: 'studio',
  inspectedHash: null,
  semantic: null,
  ...DEFAULT_SORT,

  setActiveView: (activeView) => set({ activeView }),
  setInspectedHash: (inspectedHash) => set({ inspectedHash }),
  setSemantic: (semantic) => set({ semantic }),
  setAiTagFilter: (filterAiTag) => set({ filterAiTag }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  toggleCameraFilter: (camera) =>
    set((state) => ({
      filterCameras: state.filterCameras.includes(camera)
        ? state.filterCameras.filter((c) => c !== camera)
        : [...state.filterCameras, camera],
    })),
  toggleTagFilter: (tag) =>
    set((state) => ({
      filterTags: state.filterTags.includes(tag) ? state.filterTags.filter((t) => t !== tag) : [...state.filterTags, tag],
    })),
  setCollectionFilter: (filterCollection) => set({ filterCollection }),
  // A year and a date range are mutually exclusive (FR-2a.2): setting one clears the other.
  setTimeframeFilter: (filterTimeframe) => set({ filterTimeframe, ...(filterTimeframe !== 'all' && { filterDateRange: null }) }),
  setRatingFilter: (filterRating) => set({ filterRating }),
  setDateRangeFilter: (filterDateRange) => set({ filterDateRange, ...(filterDateRange && { filterTimeframe: 'all' }) }),
  applyQueryFilters: (f) => set(filtersState(f)),
  setSort: (sortBy, sortOrder) => set({ sortBy, sortOrder }),
  setFilterArea: (filterArea) => set({ filterArea }),
  resetFilters: () => {
    get().applyQueryFilters(EMPTY_QUERY_FILTERS)
    set({ semantic: null })
  },
}))

/** The URL-held part of the store. */
export function urlStateOf(s: ViewState): UrlState {
  return {
    activeView: s.activeView,
    filters: filtersState(s),
    sortBy: s.sortBy,
    sortOrder: s.sortOrder,
    semantic: s.semantic,
    inspectedHash: s.inspectedHash,
  }
}

function applyUrlState(u: UrlState): void {
  useViewStore.setState({
    ...filtersState(u.filters),
    activeView: u.activeView,
    sortBy: u.sortBy,
    sortOrder: u.sortOrder,
    semantic: u.semantic,
    inspectedHash: u.inspectedHash,
  })
}

/** Typing in the query bar within this long of the last change edits one history entry, not one per key. */
const TYPING_MS = 1000

/**
 * Read the URL into the store, then keep them in step: a view or filter change pushes a history
 * entry, the inspected photo (and typing) replaces the current one, and Back/Forward read the URL
 * back. Returns a function that stops it (tests).
 */
export function startUrlSync(win: Window = window): () => void {
  applyUrlState(searchToState(win.location.search))
  let written = stateToSearch(urlStateOf(useViewStore.getState()))
  let lastWrite = 0
  const href = (search: string) => {
    const full = withForeignParams(win.location.search, search)
    return `${win.location.pathname}${full ? `?${full}` : ''}${win.location.hash}`
  }
  win.history.replaceState(win.history.state, '', href(written))

  let applyingPop = false
  const unsubscribe = useViewStore.subscribe((state) => {
    if (applyingPop) return
    const next = stateToSearch(urlStateOf(state))
    if (next === written) return
    const now = Date.now()
    const replace = onlyPhotoDiffers(written, next) || (onlyTextDiffers(written, next) && now - lastWrite < TYPING_MS)
    if (replace) win.history.replaceState(win.history.state, '', href(next))
    else win.history.pushState(null, '', href(next))
    written = next
    lastWrite = now
  })
  const onPop = () => {
    applyingPop = true
    try {
      applyUrlState(searchToState(win.location.search))
    } finally {
      applyingPop = false
    }
    written = stateToSearch(urlStateOf(useViewStore.getState()))
  }
  win.addEventListener('popstate', onPop)
  return () => {
    unsubscribe()
    win.removeEventListener('popstate', onPop)
  }
}
