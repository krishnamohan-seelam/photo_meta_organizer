import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { batchUpdatePhotosApi, errorMessage, listRemovedApi, restoreRemovedApi, restorePhotosApi } from '../api/client'
import { useSelectionStore } from '../stores/useSelectionStore'
import { useUiStore } from '../stores/useUiStore'
import { facetsKey } from './useFacets'
import { isDemoMode, photosKey } from './usePhotos'
import { jobsKey } from './useJobs'

/** Files removed from the library for good (ticket 12). */
export const removedKey = ['removed'] as const

function reloadLibrary(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: photosKey })
  void qc.invalidateQueries({ queryKey: facetsKey })
}

/**
 * Remove photos from the library. The files on disk are not touched, and for a short while the toast
 * offers Undo, which brings the photos back with their ratings, tags and collections.
 */
export function useRemovePhotos() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const clearSelection = useSelectionStore((s) => s.clearSelection)

  return useCallback(
    async (hashes: string[]): Promise<boolean> => {
      if (isDemoMode() || hashes.length === 0) return false
      try {
        const res = await batchUpdatePhotosApi({ photo_hashes: hashes, action: 'delete' })
        clearSelection()
        reloadLibrary(qc)
        const n = res.deleted_count
        showToast(`Removed ${n} photo${n === 1 ? '' : 's'} from the library. Files on disk are untouched.`, 'success', {
          label: 'Undo',
          run: () => {
            restorePhotosApi(hashes)
              .then((r) => {
                reloadLibrary(qc)
                showToast(r.restored_count > 0 ? `Restored ${r.restored_count} photo${r.restored_count === 1 ? '' : 's'}` : 'Too late: those photos are gone for good', r.restored_count > 0 ? 'success' : 'error')
              })
              .catch((err) => showToast(`Could not restore: ${errorMessage(err)}`, 'error'))
          },
        })
        return true
      } catch (err) {
        showToast(`Not removed: ${errorMessage(err)}`, 'error')
        return false
      }
    },
    [qc, showToast, clearSelection]
  )
}

/** Files removed for good, newest first. */
export function useRemovedFiles(enabled: boolean) {
  return useQuery({ queryKey: removedKey, queryFn: listRemovedApi, enabled: enabled && !isDemoMode() })
}

/** Restore removed files: they are forgotten by the ignore list and their folders scanned. */
export function useRestoreRemoved() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: restoreRemovedApi,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: removedKey })
      void qc.invalidateQueries({ queryKey: jobsKey })
    },
    onError: (err) => showToast(`Could not restore: ${errorMessage(err)}`, 'error'),
  })
}
