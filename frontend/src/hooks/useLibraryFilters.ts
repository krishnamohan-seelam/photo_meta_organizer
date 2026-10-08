import { useShallow } from 'zustand/react/shallow'
import { useUiStore } from '../stores/useUiStore'
import type { FilterChip } from '../utils/filterChips'
import type { LibraryFilters } from '../utils/search'

/** The filter and sort state as one object (stable while it does not change). */
export function useLibraryFilters(): LibraryFilters {
  return useUiStore(
    useShallow((s) => ({
      searchQuery: s.searchQuery,
      filterCameras: s.filterCameras,
      filterTags: s.filterTags,
      filterCollection: s.filterCollection,
      filterTimeframe: s.filterTimeframe,
      filterRating: s.filterRating,
      filterModel: s.filterModel,
      filterHasLocation: s.filterHasLocation,
      filterDateRange: s.filterDateRange,
      filterArea: s.filterArea,
      sortBy: s.sortBy,
      sortOrder: s.sortOrder,
    }))
  )
}

/** Remove the filter a chip stands for. */
export function removeFilterChip(chip: FilterChip): void {
  const s = useUiStore.getState()
  switch (chip.kind) {
    case 'search':
      return s.setSearchQuery('')
    case 'camera':
      return s.toggleCameraFilter(chip.value)
    case 'tag':
      return s.toggleTagFilter(chip.value)
    case 'rating':
      return s.setRatingFilter(null)
    case 'collection':
      return s.setCollectionFilter('all')
    case 'year':
      return s.setTimeframeFilter('all')
    case 'model':
      return useUiStore.setState({ filterModel: '' })
    case 'geo':
      return useUiStore.setState({ filterHasLocation: null })
    case 'area':
      return s.setFilterArea(null)
    case 'date':
      return s.setDateRangeFilter(null)
  }
}
