// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { SearchRequest } from '../types/metadata'
import { filtersToTokens, parseQuery, resolveTokens, tokensToFilters, tokensToText, type QueryContext } from './query'
import { toSearchRequest, type LibraryFilters } from './search'

// Ticket 13 (ADR-003 R8): every filter of POST /api/search can be written in the query bar, so any
// view can later be rebuilt from text. The field list is read from openapi.json, so adding a field to
// the API fails here until it has a token (or is declared view state below).

const ctx: QueryContext = { cameras: ['Sony', 'Canon'], collections: ['Japan 2026'] }

interface Sample {
  /** The SearchRequest fields this query covers. */
  fields: (keyof SearchRequest)[]
  q: string
  /** What the request must contain for that query. */
  request: Partial<SearchRequest>
}

const SAMPLES: Sample[] = [
  { fields: ['search_term'], q: 'kyoto', request: { search_term: 'kyoto' } },
  { fields: ['camera_makes'], q: 'make:sony make:canon', request: { camera_makes: ['Canon', 'Sony'] } },
  { fields: ['camera_model'], q: 'model:"a7 iv"', request: { camera_model: 'a7 iv' } },
  { fields: ['tags'], q: 'tag:night tag:city', request: { tags: ['city', 'night'] } },
  { fields: ['collection'], q: 'in:"Japan 2026"', request: { collection: 'Japan 2026' } },
  { fields: ['flagged'], q: 'pick:yes', request: { flagged: true } },
  { fields: ['rating'], q: 'rating:4', request: { rating: 4 } },
  {
    fields: ['date_start', 'date_end'],
    q: 'date:2026-05-14..2026-05-21',
    request: { date_start: '2026-05-14T00:00:00', date_end: '2026-05-21T23:59:59.999999' },
  },
  { fields: ['has_capture_date'], q: 'year:unknown', request: { has_capture_date: false } },
  { fields: ['has_location'], q: 'geo:no', request: { has_location: false } },
  {
    fields: ['location_lat', 'location_lon', 'radius_km'],
    q: 'near:35.68,139.69,5',
    request: { location_lat: 35.68, location_lon: 139.69, radius_km: 5 },
  },
  {
    fields: ['within'],
    q: 'within:35,139,36.5,140.25',
    request: { within: { south: 35, west: 139, north: 36.5, east: 140.25 } },
  },
  { fields: ['duplicates'], q: 'dupes:yes', request: { duplicates: true } },
  { fields: ['ai_tag'], q: 'ai:"dog on a beach"', request: { ai_tag: 'dog on a beach' } },
]

/** Fields that are not filters, with why. */
const NOT_A_FILTER: Record<string, string> = {
  page: 'paging, not a filter',
  page_size: 'paging, not a filter',
  sort_by: 'view state: ticket 14 keeps sorting in its own URL parameters',
  sort_order: 'view state: ticket 14 keeps sorting in its own URL parameters',
  camera_make: 'the older single-value form of camera_makes, which the UI never sends',
}

const requestOf = (q: string) => {
  const filters: LibraryFilters = {
    ...tokensToFilters(resolveTokens(parseQuery(q), ctx)),
    sortBy: 'captured_at',
    sortOrder: 'desc',
  }
  return { filters, request: toSearchRequest(filters) }
}

const schemaFields = (): string[] => {
  const doc = JSON.parse(readFileSync('openapi.json', 'utf8'))
  return Object.keys(doc.components.schemas.SearchRequest.properties)
}

describe('query tokens cover the search API (ticket 13)', () => {
  it('every SearchRequest field has a token, or is declared not a filter', () => {
    const covered = new Set<string>([...SAMPLES.flatMap((s) => s.fields), ...Object.keys(NOT_A_FILTER)])
    const missing = schemaFields().filter((f) => !covered.has(f))
    expect(missing, `SearchRequest fields with no query token: ${missing.join(', ')}`).toEqual([])
  })

  it('the samples and exemptions name only fields that exist', () => {
    const real = new Set(schemaFields())
    const named = [...SAMPLES.flatMap((s) => s.fields), ...Object.keys(NOT_A_FILTER)]
    expect(named.filter((f) => !real.has(f))).toEqual([])
  })

  it.each(SAMPLES.map((s) => [s.fields.join('+'), s] as const))('%s: a query becomes that request', (_name, s) => {
    expect(requestOf(s.q).request).toMatchObject(s.request)
  })

  it.each(SAMPLES.map((s) => [s.fields.join('+'), s] as const))(
    '%s: the filters written back as text give the same request',
    (_name, s) => {
      const first = requestOf(s.q)
      const text = tokensToText(filtersToTokens(first.filters))
      expect(requestOf(text).request).toEqual(first.request)
    }
  )

  it('all filters together survive the round trip', () => {
    const q = SAMPLES.map((s) => s.q).join(' ')
    const first = requestOf(q)
    const second = requestOf(tokensToText(filtersToTokens(first.filters)))
    expect(second.request).toEqual(first.request)
    expect(filtersToTokens(first.filters).some((t) => t.kind === 'invalid')).toBe(false)
  })

  it('rejects malformed values with a reason', () => {
    for (const bad of ['near:91,0,5', 'near:1,2', 'near:1,2,0', 'within:36,139,35,140', 'within:1,2,3', 'ai:']) {
      expect(parseQuery(bad)[0].kind, bad).toBe('invalid')
    }
  })
})
