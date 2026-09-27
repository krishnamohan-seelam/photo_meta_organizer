import type { SearchRequest, SortField } from '../types/metadata'
import { UNKNOWN_DATE } from './captureDate'

/** The filter and sort state the UI keeps (useUiStore). */
export interface LibraryFilters {
  searchQuery: string
  filterCameras: string[]
  filterTags: string[]
  /** 'all', 'Favorites' (flagged) or a collection name. */
  filterCollection: string
  /** 'all', a four-digit year, or UNKNOWN_DATE. */
  filterTimeframe: string
  sortBy: SortField
  sortOrder: 'asc' | 'desc'
}

/**
 * The server query for the UI's filters (PMO-27). The server applies them, so the gallery
 * shows exactly what `main.py search` / `POST /api/search` return for the same criteria.
 * Dates are naive local ISO strings, no `Z` (ADR D3); tags are AND (ADR D2).
 */
export function toSearchRequest(f: LibraryFilters): SearchRequest {
  const request: SearchRequest = { sort_by: f.sortBy, sort_order: f.sortOrder }
  const term = f.searchQuery.trim()
  if (term) request.search_term = term
  if (f.filterCameras.length > 0) request.camera_makes = [...f.filterCameras].sort()
  if (f.filterTags.length > 0) request.tags = [...f.filterTags].sort()
  if (f.filterCollection === 'Favorites') request.flagged = true
  else if (f.filterCollection !== 'all') request.collection = f.filterCollection
  if (f.filterTimeframe === UNKNOWN_DATE) {
    request.has_capture_date = false
  } else if (f.filterTimeframe !== 'all') {
    request.date_start = `${f.filterTimeframe}-01-01T00:00:00`
    request.date_end = `${f.filterTimeframe}-12-31T23:59:59.999999`
  }
  return request
}
