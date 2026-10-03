import { describe, expect, it } from 'vitest'
import { UNKNOWN_DATE } from './captureDate'
import { toSearchRequest, type LibraryFilters } from './search'

const base: LibraryFilters = {
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  sortBy: 'captured_at',
  sortOrder: 'desc',
}

describe('toSearchRequest (PMO-27)', () => {
  it('sends only the sort when nothing is filtered', () => {
    expect(toSearchRequest(base)).toEqual({ sort_by: 'captured_at', sort_order: 'desc' })
  })

  it('sorts cameras and tags so the query key does not depend on click order', () => {
    const request = toSearchRequest({ ...base, filterCameras: ['Sony', 'Canon'], filterTags: ['b', 'a'] })
    expect(request.camera_makes).toEqual(['Canon', 'Sony'])
    expect(request.tags).toEqual(['a', 'b'])
  })

  it('a year becomes naive local bounds, without Z (ADR D3)', () => {
    const request = toSearchRequest({ ...base, filterTimeframe: '2024' })
    expect(request.date_start).toBe('2024-01-01T00:00:00')
    expect(request.date_end).toBe('2024-12-31T23:59:59.999999')
  })

  it('unknown date asks for photos without a capture date', () => {
    expect(toSearchRequest({ ...base, filterTimeframe: UNKNOWN_DATE }).has_capture_date).toBe(false)
  })

  it('Favorites is the flag; any other collection is by name', () => {
    expect(toSearchRequest({ ...base, filterCollection: 'Favorites' }).flagged).toBe(true)
    expect(toSearchRequest({ ...base, filterCollection: 'Japan' }).collection).toBe('Japan')
  })

  it('trims the search term and drops a blank one', () => {
    expect(toSearchRequest({ ...base, searchQuery: '  tokyo ' }).search_term).toBe('tokyo')
    expect(toSearchRequest({ ...base, searchQuery: '   ' })).not.toHaveProperty('search_term')
  })
})
