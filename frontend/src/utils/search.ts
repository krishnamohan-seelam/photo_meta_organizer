import type { SearchRequest, SortField } from '../types/metadata'
import { UNKNOWN_DATE } from './captureDate'
import type { QueryFilters } from './query'
import type { SemanticQuery } from './urlState'

/** The filter and sort state the UI keeps (useUiStore). Sort and paging are view state, not query tokens. */
export interface LibraryFilters extends QueryFilters {
  sortBy: SortField
  sortOrder: 'asc' | 'desc'
  /** A search by meaning ranks the filtered photos instead of sorting them (ADR-003 R9). */
  semantic?: SemanticQuery | null
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
  if (f.filterRating !== null) request.rating = f.filterRating
  const model = f.filterModel.trim()
  if (model) request.camera_model = model
  if (f.filterHasLocation !== null) request.has_location = f.filterHasLocation
  if (f.filterNear) {
    request.location_lat = f.filterNear.lat
    request.location_lon = f.filterNear.lon
    request.radius_km = f.filterNear.km
  }
  if (f.filterArea) request.within = f.filterArea
  if (f.filterAiTag) request.ai_tag = f.filterAiTag
  if (f.filterDuplicates !== null && f.filterDuplicates !== undefined) request.duplicates = f.filterDuplicates
  if (f.filterDateRange) {
    request.date_start = `${f.filterDateRange.start}T00:00:00`
    request.date_end = `${f.filterDateRange.end}T23:59:59.999999`
  } else if (f.filterTimeframe === UNKNOWN_DATE) {
    request.has_capture_date = false
  } else if (f.filterTimeframe !== 'all') {
    request.date_start = `${f.filterTimeframe}-01-01T00:00:00`
    request.date_end = `${f.filterTimeframe}-12-31T23:59:59.999999`
  }
  if (f.semantic) {
    request.rank = {
      ...(f.semantic.kind === 'text' ? { text: f.semantic.text } : { like_hash: f.semantic.hash }),
      everything: Boolean(f.semantic.everything),
    }
  }
  return request
}
