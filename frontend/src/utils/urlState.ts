import type { SortField } from '../types/metadata'
import { EMPTY_QUERY_FILTERS, filtersToTokens, parseQuery, tokensToFilters, tokensToText, type QueryFilters } from './query'

/** The views of the app; `studio` is the Library and shows as `library` in the URL. */
export type ViewMode = 'studio' | 'timeline' | 'map' | 'kanban' | 'analytics'

/** A search by meaning: free text, or "photos like this one". */
export type SemanticQuery = { kind: 'text'; text: string } | { kind: 'like'; hash: string; name: string }

/**
 * What the URL holds (ADR-003 R8): the view, the filters, the sort, a search by meaning and the
 * inspected photo. Everything else (selection, dialogs, panel sizes) is transient and stays out.
 */
export interface UrlState {
  activeView: ViewMode
  filters: QueryFilters
  sortBy: SortField
  sortOrder: 'asc' | 'desc'
  semantic: SemanticQuery | null
  inspectedHash: string | null
}

export const DEFAULT_SORT: { sortBy: SortField; sortOrder: 'asc' | 'desc' } = { sortBy: 'captured_at', sortOrder: 'desc' }

const VIEW_IN_URL: Record<ViewMode, string> = {
  studio: 'library',
  timeline: 'timeline',
  map: 'map',
  kanban: 'kanban',
  analytics: 'analytics',
}

const SORT_FIELDS: readonly SortField[] = ['captured_at', 'size_bytes', 'camera_model', 'file_name']

/** The query string for a state (without `?`; empty for the default Library). Defaults are left out. */
export function stateToSearch(s: UrlState): string {
  const p = new URLSearchParams()
  if (s.activeView !== 'studio') p.set('view', VIEW_IN_URL[s.activeView])
  // `q` reuses the query bar's language, so there is one serializer for filters.
  const q = tokensToText(filtersToTokens(s.filters))
  if (q) p.set('q', q)
  if (s.sortBy !== DEFAULT_SORT.sortBy || s.sortOrder !== DEFAULT_SORT.sortOrder) p.set('sort', `${s.sortBy}-${s.sortOrder}`)
  if (s.semantic?.kind === 'text') p.set('meaning', s.semantic.text)
  else if (s.semantic?.kind === 'like') {
    p.set('like', s.semantic.hash)
    if (s.semantic.name) p.set('name', s.semantic.name)
  }
  if (s.inspectedHash) p.set('photo', s.inspectedHash)
  return p.toString()
}

/** The state a query string describes; anything missing or unreadable falls back to its default. */
export function searchToState(search: string): UrlState {
  const p = new URLSearchParams(search)
  const view = (Object.keys(VIEW_IN_URL) as ViewMode[]).find((v) => VIEW_IN_URL[v] === p.get('view')) ?? 'studio'
  const q = p.get('q')
  const filters = q ? tokensToFilters(parseQuery(q)) : { ...EMPTY_QUERY_FILTERS }
  let { sortBy, sortOrder } = DEFAULT_SORT
  const sort = /^(\w+)-(asc|desc)$/.exec(p.get('sort') ?? '')
  if (sort && SORT_FIELDS.includes(sort[1] as SortField)) {
    sortBy = sort[1] as SortField
    sortOrder = sort[2] as 'asc' | 'desc'
  }
  const meaning = p.get('meaning')?.trim()
  const like = p.get('like')
  const semantic: SemanticQuery | null = meaning
    ? { kind: 'text', text: meaning }
    : like
      ? { kind: 'like', hash: like, name: p.get('name') ?? '' }
      : null
  return { activeView: view, filters, sortBy, sortOrder, semantic, inspectedHash: p.get('photo') || null }
}

/** True when two query strings differ only in the inspected photo (replaceState, not a history entry). */
export function onlyPhotoDiffers(a: string, b: string): boolean {
  const strip = (s: string) => {
    const p = new URLSearchParams(s)
    p.delete('photo')
    return p.toString()
  }
  return strip(a) === strip(b)
}

/** True when two query strings differ only in the free text of `q` (typing in the query bar). */
export function onlyTextDiffers(a: string, b: string): boolean {
  const rest = (s: string) => {
    const p = new URLSearchParams(s)
    const filters = tokensToFilters(parseQuery(p.get('q') ?? ''))
    p.delete('q')
    p.delete('photo')
    return `${p.toString()}|${tokensToText(filtersToTokens({ ...filters, searchQuery: '' }))}`
  }
  return rest(a) === rest(b)
}

/** The parameters this module owns; any other (`demo=1`) is kept as it is. */
const OWN_PARAMS = ['view', 'q', 'sort', 'meaning', 'like', 'name', 'photo']

/** `next` (from `stateToSearch`) plus the parameters of `current` that are not ours. */
export function withForeignParams(current: string, next: string): string {
  const p = new URLSearchParams(current)
  OWN_PARAMS.forEach((k) => p.delete(k))
  const merged = new URLSearchParams(next)
  p.forEach((v, k) => merged.append(k, v))
  return merged.toString()
}
