import { UNKNOWN_DATE } from './captureDate'

/**
 * The query bar's language (FR-2a.3): only fields the search API can filter on. The store stays
 * the single source of truth; these pure functions translate between it and the bar's tokens.
 */
export type QueryField = 'make' | 'model' | 'tag' | 'in' | 'pick' | 'rating' | 'year' | 'date' | 'geo'

export type Token =
  | { kind: 'field'; field: QueryField; value: string }
  | { kind: 'text'; value: string }
  | { kind: 'invalid'; raw: string; reason: string }

export interface DateRange {
  /** Naive local dates, `YYYY-MM-DD`; the end is inclusive. */
  start: string
  end: string
}

/** The filters the query bar edits (a subset of the store's `LibraryFilters`). */
export interface QueryFilters {
  searchQuery: string
  filterCameras: string[]
  filterTags: string[]
  /** 'all', 'Favorites' (flagged) or a collection name. */
  filterCollection: string
  /** 'all', a four-digit year, or UNKNOWN_DATE. Never set together with `filterDateRange`. */
  filterTimeframe: string
  filterRating: number | null
  /** Camera model substring, or ''. */
  filterModel: string
  filterHasLocation: boolean | null
  filterDateRange: DateRange | null
}

export const EMPTY_QUERY_FILTERS: QueryFilters = {
  searchQuery: '',
  filterCameras: [],
  filterTags: [],
  filterCollection: 'all',
  filterTimeframe: 'all',
  filterRating: null,
  filterModel: '',
  filterHasLocation: null,
  filterDateRange: null,
}

/** What the bar knows about the library, to resolve `make:` and `in:` values. */
export interface QueryContext {
  cameras: string[]
  collections: string[]
}

/** Every field, with a description and an example for the autocomplete (FR-2b.3). */
export const QUERY_FIELDS: { field: QueryField; description: string; example: string }[] = [
  { field: 'make', description: 'Camera make (any of several)', example: 'make:sony' },
  { field: 'model', description: 'Camera model contains', example: 'model:"a7 iv"' },
  { field: 'tag', description: 'Tag (all of several)', example: 'tag:night' },
  { field: 'in', description: 'In a collection', example: 'in:"Japan 2026"' },
  { field: 'pick', description: 'Picked photos', example: 'pick:yes' },
  { field: 'rating', description: 'Exact star rating', example: 'rating:5' },
  { field: 'year', description: 'Capture year', example: 'year:2026' },
  { field: 'date', description: 'Capture date or range', example: 'date:2026-05-14..2026-05-21' },
  { field: 'geo', description: 'Has GPS location', example: 'geo:yes' },
]

const FIELD_NAMES = new Set<string>(QUERY_FIELDS.map((f) => f.field))

function isValidDate(value: string): boolean {
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return false
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(y, mo - 1, d))
  return date.getUTCFullYear() === y && date.getUTCMonth() === mo - 1 && date.getUTCDate() === d
}

/** `YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD`, or the reason it is not. */
export function parseDateRange(value: string): DateRange | string {
  const [start, end = start, ...rest] = value.split('..')
  if (rest.length > 0 || !isValidDate(start) || !isValidDate(end)) {
    return 'date takes a valid date, YYYY-MM-DD, or a range YYYY-MM-DD..YYYY-MM-DD'
  }
  if (start > end) return 'the start date must be on or before the end date'
  return { start, end }
}

/** Check one `field:value` pair; the value is kept as typed (makes and collections resolve later). */
function fieldToken(rawField: string, value: string, raw: string): Token {
  const field = rawField.toLowerCase()
  if (!FIELD_NAMES.has(field)) {
    return { kind: 'invalid', raw, reason: `${field}: is not searchable (the server cannot filter by it yet)` }
  }
  const f = field as QueryField
  if (value === '') return { kind: 'invalid', raw, reason: `${f}: needs a value` }
  const lower = value.toLowerCase()
  switch (f) {
    case 'pick':
      if (lower === 'yes') return { kind: 'field', field: f, value: 'yes' }
      if (lower === 'no') return { kind: 'invalid', raw, reason: 'pick:no is not supported yet' }
      return { kind: 'invalid', raw, reason: 'pick takes yes' }
    case 'rating':
      return /^[1-5]$/.test(value)
        ? { kind: 'field', field: f, value }
        : { kind: 'invalid', raw, reason: 'rating takes a whole number 1–5 (no ranges)' }
    case 'year':
      if (lower === UNKNOWN_DATE) return { kind: 'field', field: f, value: UNKNOWN_DATE }
      return /^\d{4}$/.test(value)
        ? { kind: 'field', field: f, value }
        : { kind: 'invalid', raw, reason: 'year takes a four-digit year or "unknown"' }
    case 'date': {
      const range = parseDateRange(value)
      return typeof range === 'string' ? { kind: 'invalid', raw, reason: range } : { kind: 'field', field: f, value }
    }
    case 'geo':
      return lower === 'yes' || lower === 'no'
        ? { kind: 'field', field: f, value: lower }
        : { kind: 'invalid', raw, reason: 'geo takes yes or no' }
    default:
      return { kind: 'field', field: f, value }
  }
}

// A field (`make:sony`, `model:"a7 iv"`), a quoted phrase, or a plain word.
const PIECE = /([A-Za-z]+):(?:"([^"]*)"?|(\S*))|"([^"]*)"?|(\S+)/g

/**
 * Split a query into tokens (FR-2a.4). Field names are case-insensitive, quoted values may hold
 * spaces, adjacent plain words form one search text, and unknown fields or bad values become
 * `invalid` tokens with a reason.
 */
export function parseQuery(text: string): Token[] {
  const tokens: Token[] = []
  let words: string[] = []
  const flushWords = () => {
    if (words.length > 0) tokens.push({ kind: 'text', value: words.join(' ') })
    words = []
  }
  for (const m of text.matchAll(PIECE)) {
    const [raw, field, quotedValue, plainValue, quotedText, word] = m
    if (field !== undefined) {
      flushWords()
      tokens.push(fieldToken(field, (quotedValue ?? plainValue ?? '').trim(), raw))
    } else if (quotedText !== undefined) {
      flushWords()
      if (quotedText.trim()) tokens.push({ kind: 'text', value: quotedText.trim() })
    } else if (word !== undefined) {
      words.push(word)
    }
  }
  flushWords()
  return tokens
}

/** Match `make:` and `in:` values to the library's real names (case-insensitive); unknown ones are invalid. */
export function resolveTokens(tokens: Token[], ctx: QueryContext): Token[] {
  return tokens.map((t) => {
    if (t.kind !== 'field' || (t.field !== 'make' && t.field !== 'in')) return t
    const names = t.field === 'make' ? ctx.cameras : ctx.collections
    const match = names.find((n) => n.toLowerCase() === t.value.toLowerCase())
    if (match) return { ...t, value: match }
    const what = t.field === 'make' ? 'camera make' : 'collection named'
    return { kind: 'invalid', raw: tokenText(t), reason: `No ${what} “${t.value}” in the library` }
  })
}

/** The filters the valid tokens describe, applied in order: a later single-valued field replaces an earlier one. */
export function tokensToFilters(tokens: Token[]): QueryFilters {
  const f: QueryFilters = { ...EMPTY_QUERY_FILTERS, filterCameras: [], filterTags: [] }
  for (const t of tokens) {
    if (t.kind === 'text') {
      f.searchQuery = t.value
      continue
    }
    if (t.kind !== 'field') continue
    switch (t.field) {
      case 'make':
        if (!f.filterCameras.includes(t.value)) f.filterCameras.push(t.value)
        break
      case 'tag':
        if (!f.filterTags.includes(t.value)) f.filterTags.push(t.value)
        break
      case 'model':
        f.filterModel = t.value
        break
      case 'in':
        f.filterCollection = t.value
        break
      case 'pick':
        f.filterCollection = 'Favorites'
        break
      case 'rating':
        f.filterRating = Number(t.value)
        break
      case 'year':
        f.filterTimeframe = t.value
        f.filterDateRange = null
        break
      case 'date': {
        const range = parseDateRange(t.value)
        if (typeof range !== 'string') {
          f.filterDateRange = range
          f.filterTimeframe = 'all'
        }
        break
      }
      case 'geo':
        f.filterHasLocation = t.value === 'yes'
        break
    }
  }
  return f
}

/** The tokens that describe the store's filters, in a fixed order (the query bar shows these). */
export function filtersToTokens(f: QueryFilters): Token[] {
  const tokens: Token[] = []
  const field = (name: QueryField, value: string) => tokens.push({ kind: 'field', field: name, value })
  f.filterCameras.forEach((c) => field('make', c))
  if (f.filterModel) field('model', f.filterModel)
  f.filterTags.forEach((t) => field('tag', t))
  if (f.filterRating !== null) field('rating', String(f.filterRating))
  if (f.filterCollection === 'Favorites') field('pick', 'yes')
  else if (f.filterCollection !== 'all') field('in', f.filterCollection)
  if (f.filterDateRange) {
    const { start, end } = f.filterDateRange
    field('date', start === end ? start : `${start}..${end}`)
  } else if (f.filterTimeframe !== 'all') {
    field('year', f.filterTimeframe)
  }
  if (f.filterHasLocation !== null) field('geo', f.filterHasLocation ? 'yes' : 'no')
  const term = f.searchQuery.trim()
  if (term) tokens.push({ kind: 'text', value: term })
  return tokens
}

function quote(value: string, always: RegExp): string {
  return always.test(value) ? `"${value.replace(/"/g, '')}"` : value
}

/** One token as the user would type it. */
export function tokenText(t: Token): string {
  if (t.kind === 'invalid') return t.raw
  if (t.kind === 'text') return quote(t.value, /[\s:"]/)
  return `${t.field}:${quote(t.value, /[\s"]/)}`
}

export function tokensToText(tokens: Token[]): string {
  return tokens.map(tokenText).join(' ')
}

/** Stable identity for a token (React keys, removal). */
export function tokenKey(t: Token): string {
  return t.kind === 'field' ? `${t.field}:${t.value}` : t.kind === 'text' ? `text:${t.value}` : `invalid:${t.raw}`
}
