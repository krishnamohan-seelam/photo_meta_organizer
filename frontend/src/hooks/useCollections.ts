import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage, fetchCollectionsApi, saveCollectionApi } from '../api/client'
import type { Collection } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode } from './usePhotos'

const EMPTY_COLLECTIONS: Collection[] = []

export const collectionsKey = ['collections'] as const

/** The real, saved collections (PMO-17). Selecting one in the sidebar filters the
 *  gallery to its members through the search API (PMO-27). */
export function useCollections(): Collection[] {
  return useQuery({ queryKey: collectionsKey, queryFn: fetchCollectionsApi, enabled: !isDemoMode() }).data ?? EMPTY_COLLECTIONS
}

/**
 * Create a collection from photos, or add photos to an existing one (`POST /api/collections`
 * replaces the member list, so existing members are merged in first). Resolves to whether it saved.
 */
export function useSaveCollection() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const { mutateAsync } = useMutation({
    mutationFn: ({ name, hashes, description }: { name: string; hashes: string[]; description: string }) =>
      saveCollectionApi(name, hashes, description),
    onSuccess: () => qc.invalidateQueries({ queryKey: collectionsKey }),
  })

  return useCallback(
    async (name: string, hashes: string[], existing?: Collection): Promise<boolean> => {
      const trimmed = name.trim()
      if (!trimmed) return false
      if (isDemoMode()) {
        showToast('Collections are not available in the demo', 'error')
        return false
      }
      const members = existing ? [...new Set([...existing.photo_hashes, ...hashes])] : hashes
      try {
        await mutateAsync({ name: trimmed, hashes: members, description: existing?.description ?? '' })
        const added = existing ? members.length - existing.photo_hashes.length : members.length
        showToast(`${existing ? 'Added' : 'Saved'} ${added} photo${added === 1 ? '' : 's'} ${existing ? 'to' : 'as'} “${trimmed}”`)
        return true
      } catch (err) {
        showToast(`Not saved: ${errorMessage(err)}`, 'error')
        return false
      }
    },
    [mutateAsync, showToast]
  )
}
