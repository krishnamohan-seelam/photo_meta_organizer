import { useShallow } from 'zustand/react/shallow'
import { useViewStore } from '../stores/useViewStore'
import type { FilterChip } from '../utils/filterChips'
import type { LibraryFilters } from '../utils/search'

/** The filter and sort state as one object (stable while it does not change). */
export function useLibraryFilters(): LibraryFilters {
  return useViewStore(
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
      filterAiTag: s.filterAiTag,
      filterNear: s.filterNear,
      filterDuplicates: s.filterDuplicates,
      sortBy: s.sortBy,
      sortOrder: s.sortOrder,
      semantic: s.semantic,
    }))
  )
}

/** Remove the filter a chip stands for. */
export function removeFilterChip(chip: FilterChip): void {
  const s = useViewStore.getState()
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
      return useViewStore.setState({ filterModel: '' })
    case 'geo':
      return useViewStore.setState({ filterHasLocation: null })
    case 'dupes':
      return useViewStore.setState({ filterDuplicates: null })
    case 'near':
      return useViewStore.setState({ filterNear: null })
    case 'area':
      return s.setFilterArea(null)
    case 'aitag':
      return s.setAiTagFilter(null)
    case 'date':
      return s.setDateRangeFilter(null)
  }
}
