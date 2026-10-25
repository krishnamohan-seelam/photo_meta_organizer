import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage, hideFileApi, listDuplicatesApi } from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { facetsKey } from './useFacets'
import { isDemoMode, photosKey } from './usePhotos'

/** Duplicate groups; the page size is part of the key, "show more" asks for a longer list. */
export const duplicatesKey = ['duplicates'] as const

export function useDuplicates(limit: number) {
  return useQuery({
    queryKey: [...duplicatesKey, limit],
    queryFn: () => listDuplicatesApi(limit),
    enabled: !isDemoMode(),
    placeholderData: (previous) => previous,
  })
}

/** Hide a copy from the duplicates view, or show it again. Counts everywhere are reloaded. */
export function useHideCopy() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: ({ path, hidden }: { path: string; hidden: boolean }) => hideFileApi(path, hidden),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: duplicatesKey })
      void qc.invalidateQueries({ queryKey: facetsKey })
      void qc.invalidateQueries({ queryKey: photosKey })
    },
    onError: (err) => showToast(`Could not change the copy: ${errorMessage(err)}`, 'error'),
  })
}
