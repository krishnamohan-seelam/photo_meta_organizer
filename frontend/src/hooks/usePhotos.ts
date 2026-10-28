import { useMemo } from 'react'
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import type { PaginatedPhotosResponse, PhotoMetadata, SearchRequest } from '../types/metadata'
import { ApiError, getPhotoByHash, searchPhotosApi } from '../api/client'
import { demoSearch, findDemoPhoto } from '../demo/demoLibrary'
import { useViewStore } from '../stores/useViewStore'
import { toSearchRequest } from '../utils/search'
import { useLibraryFilters } from './useLibraryFilters'

/**
 * Prefix of every photo query: the paged search, the map's geotagged set and single
 * records. Edits patch all of them in place; a finished job or a delete invalidates them.
 */
export const photosKey = ['photos'] as const

/** `?demo=1` shows the built-in sample library instead of calling the backend. It is never a fallback. */
export function isDemoMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('demo') === '1'
  } catch {
    return false
  }
}

/** Photos per request while scrolling (PMO-27): the first screen needs one request, not the library. */
export const PAGE_SIZE = 200

const NO_PHOTOS: PhotoMetadata[] = []

export function runSearch(request: SearchRequest): Promise<PaginatedPhotosResponse> {
  return isDemoMode() ? demoSearch(request) : searchPhotosApi(request)
}

/** The server query for the current filters and sort, stable while they do not change. */
export function useSearchRequest(): SearchRequest {
  const filters = useLibraryFilters()
  return useMemo(() => toSearchRequest(filters), [filters])
}

/**
 * The library as the current filters see it, one page at a time (PMO-27). Every view reads
 * this one cache entry; `fetchNextPage` loads more as the user scrolls. While a new filter
 * loads, the previous results stay on screen.
 */
export function usePhotoSearch() {
  const request = useSearchRequest()
  const qc = useQueryClient()
  const queryKey = [...photosKey, 'search', request]
  const query = useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam }) => {
      // A ranked search pages through the server's snapshot: later pages send page 1's token.
      const first = pageParam > 1 ? qc.getQueryData<InfiniteData<PaginatedPhotosResponse>>(queryKey)?.pages[0] : undefined
      const token = first?.rank_token
      try {
        return await runSearch({ ...request, page: pageParam, page_size: PAGE_SIZE, ...(token && { rank_token: token }) })
      } catch (err) {
        // The snapshot expired: run the search again from page 1.
        if (token && err instanceof ApiError && err.status === 410) void qc.resetQueries({ queryKey, exact: true })
        throw err
      }
    },
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.total_pages ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  })
  const photos = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? NO_PHOTOS, [query.data])
  const totalCount = query.data?.pages[0]?.total_count ?? 0
  return { ...query, photos, totalCount, request }
}

/** Any cached shape a photo query holds. */
export type PhotoCacheData = InfiniteData<PaginatedPhotosResponse> | PaginatedPhotosResponse | PhotoMetadata | undefined

/** Swap in changed photos by hash in any photo query's data, leaving everything else (and its identity) alone. */
export function patchPhotoCache(data: PhotoCacheData, changed: Map<string, PhotoMetadata>): PhotoCacheData {
  if (!data || changed.size === 0) return data
  const patchPage = (page: PaginatedPhotosResponse): PaginatedPhotosResponse => {
    if (!page.items.some((p) => changed.has(p.file_hash))) return page
    return { ...page, items: page.items.map((p) => changed.get(p.file_hash) ?? p) }
  }
  if ('pages' in data) return { ...data, pages: data.pages.map(patchPage) }
  if ('items' in data) return patchPage(data)
  return changed.get(data.file_hash) ?? data
}

/** Every cached copy of the photos in `hashes` (first one found per hash). */
export function findCachedPhotos(qc: QueryClient, hashes: Iterable<string>): Map<string, PhotoMetadata> {
  const wanted = new Set(hashes)
  const found = new Map<string, PhotoMetadata>()
  const take = (p: PhotoMetadata) => {
    if (wanted.has(p.file_hash) && !found.has(p.file_hash)) found.set(p.file_hash, p)
  }
  for (const [, data] of qc.getQueriesData<PhotoCacheData>({ queryKey: photosKey })) {
    if (!data) continue
    if ('pages' in data) data.pages.forEach((page) => page.items.forEach(take))
    else if ('items' in data) data.items.forEach(take)
    else take(data)
  }
  return found
}

/** The inspected photo, and whether its hash names a photo the library no longer has (a stale `photo=` link). */
export interface InspectedPhoto {
  photo: PhotoMetadata | undefined
  missing: boolean
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404

/**
 * The photo shown in the inspector. Served from whatever query already holds it (edits patch
 * every copy), fetched by hash when the current results do not include it.
 */
export function useInspectedPhoto(): InspectedPhoto {
  const hash = useViewStore((s) => s.inspectedHash)
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: [...photosKey, 'one', hash],
    queryFn: async () => {
      if (!hash) throw new Error('no photo')
      if (isDemoMode()) {
        const photo = findDemoPhoto(hash)
        if (!photo) throw new ApiError('Photo not found', 404)
        return photo
      }
      return getPhotoByHash(hash)
    },
    enabled: hash !== null,
    initialData: () => (hash ? findCachedPhotos(qc, [hash]).get(hash) : undefined),
    staleTime: Infinity,
    retry: (count, error) => !isNotFound(error) && count < 1,
  })
  return { photo: query.data, missing: hash !== null && isNotFound(query.error) }
}
