import { useQuery } from '@tanstack/react-query'
import { fetchCollectionsApi } from '../api/client'
import type { Collection } from '../types/metadata'

const EMPTY_COLLECTIONS: Collection[] = []

/** The real, saved collections (PMO-17) — replaces the `FilterSidebar`'s
 *  hardcoded "Japan Trip 2026" / "Client Shoots" placeholders. Filtering the
 *  gallery by a collection's hash set is not wired up yet (PMO-27/28). */
export function useCollections(): Collection[] {
  return useQuery({ queryKey: ['collections'], queryFn: fetchCollectionsApi }).data ?? EMPTY_COLLECTIONS
}
