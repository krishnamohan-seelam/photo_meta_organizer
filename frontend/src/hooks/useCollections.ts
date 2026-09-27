import { useQuery } from '@tanstack/react-query'
import { fetchCollectionsApi } from '../api/client'
import type { Collection } from '../types/metadata'

const EMPTY_COLLECTIONS: Collection[] = []

/** The real, saved collections (PMO-17). Selecting one in the sidebar filters the
 *  gallery to its members through the search API (PMO-27). */
export function useCollections(): Collection[] {
  return useQuery({ queryKey: ['collections'], queryFn: fetchCollectionsApi }).data ?? EMPTY_COLLECTIONS
}
