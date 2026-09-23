import { useCallback } from 'react'
import { queryOptions, useQuery } from '@tanstack/react-query'
import type { PhotoMetadata } from '../types/metadata'
import { fetchPhotos } from '../api/client'
import { SAMPLE_PHOTOS } from '../demo/samplePhotos'
import { useUiStore } from '../stores/useUiStore'

/** The one cache entry every view reads: the whole library, newest first. */
export const photosKey = ['photos'] as const

/** `?demo=1` shows the built-in sample library instead of calling the backend. It is never a fallback. */
export function isDemoMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('demo') === '1'
  } catch {
    return false
  }
}

// The backend caps page_size at 500; page 1 tells us how many more pages there are.
const PAGE_SIZE = 500

async function fetchAllPhotos(): Promise<PhotoMetadata[]> {
  const first = await fetchPhotos(1, PAGE_SIZE, 'captured_at', 'desc')
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, first.total_pages - 1) }, (_, i) =>
      fetchPhotos(i + 2, PAGE_SIZE, 'captured_at', 'desc')
    )
  )
  return first.items.concat(...rest.map((page) => page.items))
}

export const photosQuery = () =>
  queryOptions({
    queryKey: photosKey,
    queryFn: isDemoMode() ? () => Promise.resolve(SAMPLE_PHOTOS) : fetchAllPhotos,
  })

/** The whole library. `isPending` = first load, `isError` = the last fetch failed (`data` may still hold older photos). */
export function usePhotos() {
  return useQuery(photosQuery())
}

/** The photo shown in the inspector, looked up in the cache by hash so it always reflects the latest edit. */
export function useInspectedPhoto(): PhotoMetadata | undefined {
  const hash = useUiStore((s) => s.inspectedHash)
  const select = useCallback(
    (photos: PhotoMetadata[]) => (hash ? photos.find((p) => p.file_hash === hash) : undefined),
    [hash]
  )
  return useQuery({ ...photosQuery(), select }).data
}
