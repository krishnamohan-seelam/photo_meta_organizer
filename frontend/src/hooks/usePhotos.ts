import { useMemo } from 'react'
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { useShallow } from 'zustand/react/shallow'
import type { PaginatedPhotosResponse, PhotoMetadata, SearchRequest } from '../types/metadata'
import { getPhotoByHash, searchPhotosApi } from '../api/client'
import { demoSearch, findDemoPhoto } from '../demo/demoLibrary'
import { useUiStore } from '../stores/useUiStore'
import { toSearchRequest } from '../utils/search'

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
  const filters = useUiStore(
    useShallow((s) => ({
      searchQuery: s.searchQuery,
      filterCameras: s.filterCameras,
      filterTags: s.filterTags,
      filterCollection: s.filterCollection,
      filterTimeframe: s.filterTimeframe,
      sortBy: s.sortBy,
      sortOrder: s.sortOrder,
    }))
  )
  return useMemo(() => toSearchRequest(filters), [filters])
}

/**
 * The library as the current filters see it, one page at a time (PMO-27). Every view reads
 * this one cache entry; `fetchNextPage` loads more as the user scrolls. While a new filter
 * loads, the previous results stay on screen.
 */
export function usePhotoSearch() {
  const request = useSearchRequest()
  const query = useInfiniteQuery({
    queryKey: [...photosKey, 'search', request],
    queryFn: ({ pageParam }) => runSearch({ ...request, page: pageParam, page_size: PAGE_SIZE }),
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

/**
 * The photo shown in the inspector. Served from whatever query already holds it (edits patch
 * every copy), fetched by hash when the current results do not include it.
 */
export function useInspectedPhoto(): PhotoMetadata | undefined {
  const hash = useUiStore((s) => s.inspectedHash)
  const qc = useQueryClient()
  return useQuery({
    queryKey: [...photosKey, 'one', hash],
    queryFn: async () => {
      if (!hash) throw new Error('no photo')
      if (isDemoMode()) {
        const photo = findDemoPhoto(hash)
        if (!photo) throw new Error('Photo not found')
        return photo
      }
      return getPhotoByHash(hash)
    },
    enabled: hash !== null,
    initialData: () => (hash ? findCachedPhotos(qc, [hash]).get(hash) : undefined),
    staleTime: Infinity,
  }).data
}
