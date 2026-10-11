import { UNKNOWN_DATE } from './captureDate'
import type { LibraryFilters } from './search'

export type ChipKind = 'search' | 'camera' | 'model' | 'tag' | 'rating' | 'collection' | 'year' | 'date' | 'geo' | 'area' | 'aitag'

export interface FilterChip {
  id: string
  kind: ChipKind
  /** The store value the chip removes (camera or tag name). */
  value: string
  label: string
}

/**
 * One removable chip per active filter, in the gallery toolbar (FR-1d.4). "Picks" is not a chip:
 * it is the gallery title, like a collection the user navigated to from the panel.
 */
export function filterChips(f: LibraryFilters): FilterChip[] {
  const chips: FilterChip[] = []
  const term = f.searchQuery.trim()
  if (term) chips.push({ id: 'search', kind: 'search', value: term, label: `“${term}”` })
  for (const c of f.filterCameras) chips.push({ id: `camera:${c}`, kind: 'camera', value: c, label: c })
  const model = f.filterModel.trim()
  if (model) chips.push({ id: 'model', kind: 'model', value: model, label: `model “${model}”` })
  for (const t of f.filterTags) chips.push({ id: `tag:${t}`, kind: 'tag', value: t, label: `#${t}` })
  if (f.filterRating !== null) {
    chips.push({ id: 'rating', kind: 'rating', value: String(f.filterRating), label: `★${f.filterRating}` })
  }
  if (f.filterCollection !== 'all' && f.filterCollection !== 'Favorites') {
    chips.push({ id: 'collection', kind: 'collection', value: f.filterCollection, label: f.filterCollection })
  }
  if (f.filterTimeframe !== 'all') {
    const label = f.filterTimeframe === UNKNOWN_DATE ? 'Unknown date' : f.filterTimeframe
    chips.push({ id: 'year', kind: 'year', value: f.filterTimeframe, label })
  }
  if (f.filterDateRange) {
    const { start, end } = f.filterDateRange
    chips.push({ id: 'date', kind: 'date', value: start, label: start === end ? start : `${start} – ${end}` })
  }
  if (f.filterHasLocation !== null) {
    chips.push({ id: 'geo', kind: 'geo', value: String(f.filterHasLocation), label: f.filterHasLocation ? 'Geotagged' : 'No location' })
  }
  if (f.filterArea) chips.push({ id: 'area', kind: 'area', value: 'area', label: 'Map area' })
  if (f.filterAiTag) chips.push({ id: 'aitag', kind: 'aitag', value: f.filterAiTag, label: `✨ ${f.filterAiTag}` })
  return chips
}

/** The gallery toolbar title for the panel's Library/Collections choice. */
export function galleryTitle(filterCollection: string): string {
  if (filterCollection === 'all') return 'All photos'
  if (filterCollection === 'Favorites') return 'Picks'
  return filterCollection
}
