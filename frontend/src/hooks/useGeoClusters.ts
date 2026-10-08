import { useMemo } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fetchConfigApi, fetchGeoClustersApi } from '../api/client'
import { demoGeoClusters } from '../demo/demoLibrary'
import type { AppConfig, GeoClustersRequest, SearchRequest } from '../types/metadata'
import { toSearchRequest } from '../utils/search'
import { useLibraryFilters } from './useLibraryFilters'
import { isDemoMode, photosKey } from './usePhotos'

const OFFLINE_CONFIG: AppConfig = { map_tiles_url: null, map_tiles_attribution: null }

/**
 * The Library's filters as a search request, without the map area: the Map view has its own
 * viewport, and filtering by the area it is showing would make panning impossible.
 */
export function useMapFilterRequest(): SearchRequest {
  const filters = useLibraryFilters()
  return useMemo(() => toSearchRequest({ ...filters, filterArea: null }), [filters])
}

/**
 * Clusters of the geotagged photos that match the filters inside the visible area. Under the
 * `['photos']` prefix, so edits and finished jobs refresh it; the previous clusters stay on the
 * map while a pan or zoom loads.
 */
export function useGeoClusters(request: GeoClustersRequest | null) {
  return useQuery({
    queryKey: [...photosKey, 'geo', request],
    queryFn: () => (isDemoMode() ? demoGeoClusters(request!) : fetchGeoClustersApi(request!)),
    enabled: request !== null,
    placeholderData: keepPreviousData,
  })
}

/** Deployment settings (opt-in map tiles). Fixed for the life of the server. */
export function useAppConfig(): AppConfig {
  const query = useQuery({
    queryKey: ['config'],
    queryFn: () => (isDemoMode() ? Promise.resolve(OFFLINE_CONFIG) : fetchConfigApi()),
    staleTime: Infinity,
  })
  return query.data ?? OFFLINE_CONFIG
}
