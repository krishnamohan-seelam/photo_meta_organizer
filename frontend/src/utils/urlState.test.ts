import { describe, expect, it } from 'vitest'
import { EMPTY_QUERY_FILTERS } from './query'
import { onlyPhotoDiffers, onlyTextDiffers, searchToState, stateToSearch, withForeignParams, type UrlState } from './urlState'

const base: UrlState = {
  activeView: 'studio',
  filters: { ...EMPTY_QUERY_FILTERS },
  sortBy: 'captured_at',
  sortOrder: 'desc',
  semantic: null,
  inspectedHash: null,
}

describe('URL state (ADR-003 R8)', () => {
  it('leaves the default Library out of the URL', () => {
    expect(stateToSearch(base)).toBe('')
    expect(searchToState('')).toEqual(base)
  })

  it('round-trips view, filters, sort, a search by meaning and the inspected photo', () => {
    const state: UrlState = {
      activeView: 'timeline',
      filters: { ...EMPTY_QUERY_FILTERS, filterCameras: ['Sony'], filterRating: 4, filterTags: ['night sky'], searchQuery: 'beach' },
      sortBy: 'file_name',
      sortOrder: 'asc',
      semantic: { kind: 'text', text: 'dog on a beach' },
      inspectedHash: 'abc',
    }
    const search = stateToSearch(state)
    expect(new URLSearchParams(search).get('q')).toBe('make:Sony tag:"night sky" rating:4 beach')
    expect(new URLSearchParams(search).get('view')).toBe('timeline')
    expect(new URLSearchParams(search).get('sort')).toBe('file_name-asc')
    expect(searchToState(search)).toEqual(state)
  })

  it('round-trips photos like a photo, with its name', () => {
    const state: UrlState = { ...base, semantic: { kind: 'like', hash: 'h1', name: 'IMG_1.jpg' } }
    expect(searchToState(stateToSearch(state))).toEqual(state)
  })

  it('falls back to defaults for unknown values', () => {
    expect(searchToState('view=nowhere&sort=bogus-asc&photo=')).toEqual(base)
  })

  it('tells a photo-only or text-only change apart from a filter change', () => {
    expect(onlyPhotoDiffers('q=make%3ASony&photo=a', 'q=make%3ASony&photo=b')).toBe(true)
    expect(onlyPhotoDiffers('q=make%3ASony', 'q=make%3ACanon')).toBe(false)
    expect(onlyTextDiffers('q=make%3ASony+be', 'q=make%3ASony+beach')).toBe(true)
    expect(onlyTextDiffers('q=be', 'q=rating%3A4+be')).toBe(false)
  })

  it('keeps parameters it does not own', () => {
    expect(withForeignParams('demo=1&q=old', 'q=new')).toBe('q=new&demo=1')
  })
})
