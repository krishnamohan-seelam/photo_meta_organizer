import { useQuery } from '@tanstack/react-query'
import { fetchFacetsApi } from '../api/client'
import { demoFacets } from '../demo/demoLibrary'
import type { Facets } from '../types/metadata'
import { isDemoMode } from './usePhotos'

export const facetsKey = ['facets'] as const

const EMPTY_FACETS: Facets = {
  cameras: [],
  tags: [],
  years: [],
  isos: [],
  stats: { total_count: 0, flagged_count: 0, geotagged_count: 0, undated_count: 0, total_bytes: 0, avg_megapixels: 0 },
}

/**
 * Whole-library camera/tag/year/ISO counts and totals from `GET /api/facets` (PMO-27):
 * the browser no longer holds the whole library to count it. Edits and finished jobs
 * invalidate `facetsKey`.
 */
export function useFacetsQuery() {
  return useQuery({ queryKey: facetsKey, queryFn: isDemoMode() ? demoFacets : fetchFacetsApi })
}

export function useFacets(): Facets {
  return useFacetsQuery().data ?? EMPTY_FACETS
}
