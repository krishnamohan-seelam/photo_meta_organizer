import { describe, expect, it } from 'vitest'
import { UNKNOWN_DATE } from './captureDate'
import { filterChips, galleryTitle } from './filterChips'
import type { LibraryFilters } from './search'

const base: LibraryFilters = {
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  filterRating: null,
  filterModel: '',
  filterHasLocation: null,
  filterDateRange: null,
  sortBy: 'captured_at',
  sortOrder: 'desc',
}

describe('filterChips (FR-1d.4)', () => {
  it('has no chips when nothing is filtered', () => {
    expect(filterChips(base)).toEqual([])
  })

  it('lists every active filter, tags as #tag so AND is visible', () => {
    const chips = filterChips({
      ...base,
      searchQuery: ' kyoto ',
      filterCameras: ['Sony'],
      filterTags: ['iceland', 'night'],
      filterRating: 5,
      filterCollection: 'Japan 2026',
      filterTimeframe: '2024',
    })
    expect(chips.map((c) => c.label)).toEqual(['“kyoto”', 'Sony', '#iceland', '#night', '★5', 'Japan 2026', '2024'])
  })

  it('does not chip Picks (it is the view title) and labels unknown dates', () => {
    const chips = filterChips({ ...base, filterCollection: 'Favorites', filterTimeframe: UNKNOWN_DATE })
    expect(chips.map((c) => c.label)).toEqual(['Unknown date'])
  })
})

describe('map area chip', () => {
  it('shows a removable chip while a map area narrows the library', () => {
    const area = { south: 30, west: 130, north: 40, east: 145 }
    expect(filterChips({ ...base, filterArea: area }).map((c) => [c.kind, c.label])).toEqual([['area', 'Map area']])
    expect(filterChips({ ...base, filterArea: null })).toEqual([])
  })
})

describe('galleryTitle', () => {
  it('names the library, Picks or the collection', () => {
    expect(galleryTitle('all')).toBe('All photos')
    expect(galleryTitle('Favorites')).toBe('Picks')
    expect(galleryTitle('Japan 2026')).toBe('Japan 2026')
  })
})
