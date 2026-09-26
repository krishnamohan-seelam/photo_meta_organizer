import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { photosQuery } from './usePhotos'
import type { PhotoMetadata } from '../types/metadata'

export interface FacetCount {
  name: string
  count: number
}

export interface Facets {
  cameras: FacetCount[]
  tags: FacetCount[]
  years: FacetCount[]
}

const EMPTY_FACETS: Facets = { cameras: [], tags: [], years: [] }

function toSorted(counts: Map<string, number>): FacetCount[] {
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

function computeFacets(photos: PhotoMetadata[]): Facets {
  const cameraCounts = new Map<string, number>()
  const tagCounts = new Map<string, number>()
  const yearCounts = new Map<string, number>()

  for (const photo of photos) {
    const make = photo.exif.camera_make
    if (make) cameraCounts.set(make, (cameraCounts.get(make) ?? 0) + 1)

    for (const tag of photo.labels) {
      tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1)
    }

    const dateStr = photo.exif.captured_at || photo.added_at
    if (dateStr) {
      const year = dateStr.substring(0, 4)
      yearCounts.set(year, (yearCounts.get(year) ?? 0) + 1)
    }
  }

  return {
    cameras: toSorted(cameraCounts),
    tags: toSorted(tagCounts),
    years: toSorted(yearCounts),
  }
}

/**
 * Camera/tag/year counts derived from the already-loaded library (client-side,
 * PMO-17). A later swap to server-driven facets (`GET /api/facets`, PMO-27)
 * only changes this hook's body, not its callers.
 */
export function useFacets(): Facets {
  const select = useCallback((photos: PhotoMetadata[]) => computeFacets(photos), [])
  return useQuery({ ...photosQuery(), select }).data ?? EMPTY_FACETS
}
