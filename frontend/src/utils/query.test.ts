import { describe, expect, it } from 'vitest'
import { UNKNOWN_DATE } from './captureDate'
import {
  EMPTY_QUERY_FILTERS,
  filtersToTokens,
  parseQuery,
  resolveTokens,
  tokensToFilters,
  tokensToText,
  type QueryContext,
  type QueryFilters,
} from './query'
import { toSearchRequest, type LibraryFilters } from './search'

const ctx: QueryContext = { cameras: ['Sony', 'Canon', 'FUJIFILM'], collections: ['Japan 2026', 'Portfolio'] }
const filtersOf = (q: string) => tokensToFilters(resolveTokens(parseQuery(q), ctx))
const request = (q: string) => {
  const library: LibraryFilters = { ...filtersOf(q), sortBy: 'captured_at', sortOrder: 'desc' }
  return toSearchRequest(library)
}

describe('parseQuery (FR-2a.3, 2a.4)', () => {
  it('splits fields, quoted values and free text', () => {
    expect(parseQuery('make:sony model:"a7 iv" tag:night kyoto')).toEqual([
      { kind: 'field', field: 'make', value: 'sony' },
      { kind: 'field', field: 'model', value: 'a7 iv' },
      { kind: 'field', field: 'tag', value: 'night' },
      { kind: 'text', value: 'kyoto' },
    ])
  })

  it('reads field names case-insensitively', () => {
    expect(parseQuery('MAKE:Sony Tag:x')).toEqual([
      { kind: 'field', field: 'make', value: 'Sony' },
      { kind: 'field', field: 'tag', value: 'x' },
    ])
  })

  it('joins adjacent plain words into one search text; quotes keep spaces', () => {
    expect(parseQuery('tokyo tower make:sony')).toEqual([
      { kind: 'text', value: 'tokyo tower' },
      { kind: 'field', field: 'make', value: 'sony' },
    ])
    expect(parseQuery('"tokyo tower"')).toEqual([{ kind: 'text', value: 'tokyo tower' }])
  })

  it.each([
    ['iso:800', /not searchable/i],
    ['rating:6', /1.5/],
    ['rating:>=4', /1.5/],
    ['pick:no', /not supported/i],
    ['pick:maybe', /yes/],
    ['year:26', /four-digit/i],
    ['geo:sometimes', /yes or no/i],
    ['date:2026-05-21..2026-05-14', /before/i],
    ['date:2026-02-30', /date/i],
    ['make:', /value/i],
  ])('%s is invalid with a reason', (q, reason) => {
    const [token] = parseQuery(q)
    expect(token.kind).toBe('invalid')
    if (token.kind === 'invalid') expect(token.reason).toMatch(reason)
  })
})

describe('resolveTokens', () => {
  it('matches makes and collections case-insensitively to their real names', () => {
    expect(resolveTokens(parseQuery('make:sony in:"japan 2026"'), ctx)).toEqual([
      { kind: 'field', field: 'make', value: 'Sony' },
      { kind: 'field', field: 'in', value: 'Japan 2026' },
    ])
  })

  it('marks unknown makes and collections invalid', () => {
    const [make, col] = resolveTokens(parseQuery('make:leica in:nowhere'), ctx)
    expect(make.kind).toBe('invalid')
    expect(col.kind).toBe('invalid')
  })
})

describe('tokensToFilters', () => {
  it('ORs makes and ANDs tags', () => {
    const f = filtersOf('make:sony make:canon tag:iceland tag:night')
    expect(f.filterCameras).toEqual(['Sony', 'Canon'])
    expect(f.filterTags).toEqual(['iceland', 'night'])
    expect(request('make:sony make:canon tag:iceland tag:night')).toMatchObject({ camera_makes: ['Canon', 'Sony'], tags: ['iceland', 'night'] })
  })

  it('a later single-valued field replaces an earlier one', () => {
    const f = filtersOf('rating:3 model:a7 rating:5 model:"x-t5" kyoto osaka')
    expect(f.filterRating).toBe(5)
    expect(f.filterModel).toBe('x-t5')
    expect(f.searchQuery).toBe('kyoto osaka')
  })

  it('never applies invalid tokens', () => {
    expect(filtersOf('iso:800 rating:9')).toEqual(EMPTY_QUERY_FILTERS)
  })

  it('year and date are mutually exclusive: the later one wins (AC-2a.2)', () => {
    const a = filtersOf('year:2024 date:2026-05-14..2026-05-21')
    expect(a.filterTimeframe).toBe('all')
    expect(a.filterDateRange).toEqual({ start: '2026-05-14', end: '2026-05-21' })
    const b = filtersOf('date:2026-05-14..2026-05-21 year:2024')
    expect(b.filterTimeframe).toBe('2024')
    expect(b.filterDateRange).toBeNull()
  })

  it.each([
    ['make:sony', { camera_makes: ['Sony'] }],
    ['model:"a7 iv"', { camera_model: 'a7 iv' }],
    ['tag:japan', { tags: ['japan'] }],
    ['in:portfolio', { collection: 'Portfolio' }],
    ['pick:yes', { flagged: true }],
    ['rating:5', { rating: 5 }],
    ['year:2026', { date_start: '2026-01-01T00:00:00', date_end: '2026-12-31T23:59:59.999999' }],
    ['year:unknown', { has_capture_date: false }],
    ['date:2026-05-14..2026-05-21', { date_start: '2026-05-14T00:00:00', date_end: '2026-05-21T23:59:59.999999' }],
    ['date:2026-05-14', { date_start: '2026-05-14T00:00:00', date_end: '2026-05-14T23:59:59.999999' }],
    ['geo:yes', { has_location: true }],
    ['geo:no', { has_location: false }],
    ['"tokyo tower"', { search_term: 'tokyo tower' }],
  ])('%s → %j', (q, expected) => {
    expect(request(q)).toMatchObject(expected)
  })

  it('year:unknown keeps the unknown-date timeframe', () => {
    expect(filtersOf('year:unknown').filterTimeframe).toBe(UNKNOWN_DATE)
  })
})

describe('round trip (FR-2a.5)', () => {
  it.each([
    'make:sony make:canon tag:night tag:"long exposure" rating:4 kyoto',
    'model:"a7 iv" in:"japan 2026" geo:yes date:2026-05-14..2026-05-21',
    'pick:yes year:unknown "tokyo tower"',
    '',
  ])('%s is stable', (q) => {
    const once = filtersToTokens(filtersOf(q))
    const twice = filtersToTokens(filtersOf(tokensToText(once)))
    expect(twice).toEqual(once)
  })

  it('serialises the store filters back into a query', () => {
    const f: QueryFilters = {
      ...EMPTY_QUERY_FILTERS,
      searchQuery: 'tokyo tower',
      filterCameras: ['Sony'],
      filterTags: ['night'],
      filterRating: 5,
      filterCollection: 'Favorites',
      filterHasLocation: false,
    }
    expect(tokensToText(filtersToTokens(f))).toBe('make:Sony tag:night rating:5 pick:yes geo:no "tokyo tower"')
  })
})
