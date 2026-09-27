import { useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import type { BatchPhotoRequest, PatchPhotoRequest, PhotoMetadata } from '../types/metadata'
import { batchUpdatePhotosApi, errorMessage, patchPhotoApi } from '../api/client'
import { applyBatchAction, applyPatch } from '../utils/photoPatch'
import { useUiStore } from '../stores/useUiStore'
import { saveDemoPhoto } from '../demo/demoLibrary'
import { findCachedPhotos, isDemoMode, patchPhotoCache, photosKey } from './usePhotos'
import type { PhotoCacheData } from './usePhotos'
import { facetsKey } from './useFacets'

interface PatchVars {
  hash: string
  patch: PatchPhotoRequest
}

/** Swap `changed` into every cached photo query (search pages, map set, single records). */
function writeToCache(qc: QueryClient, changed: Map<string, PhotoMetadata>): void {
  if (changed.size === 0) return
  qc.setQueriesData<PhotoCacheData>({ queryKey: photosKey }, (old) => patchPhotoCache(old, changed))
}

/**
 * Edit one photo. Every cached copy is updated at once (optimistic), replaced by the server's record
 * on success and put back on failure, so the UI never shows a save that did not happen. A photo that
 * no longer matches the filters stays in view until the next reload, rather than vanishing mid-edit.
 */
export function useUpdatePhoto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ hash, patch }: PatchVars): Promise<PhotoMetadata> => {
      if (isDemoMode()) {
        // Demo data lives only in memory: there is no backend to confirm with.
        const current = findCachedPhotos(qc, [hash]).get(hash)
        if (!current) throw new Error('Photo not found')
        const updated = applyPatch(current, patch)
        saveDemoPhoto(updated)
        return updated
      }
      return patchPhotoApi(hash, patch)
    },
    onMutate: async ({ hash, patch }) => {
      await qc.cancelQueries({ queryKey: photosKey })
      const previous = findCachedPhotos(qc, [hash]).get(hash)
      if (previous) writeToCache(qc, new Map([[hash, applyPatch(previous, patch)]]))
      return { previous }
    },
    onError: (_err, { hash }, ctx) => {
      // Roll back only this photo: other in-flight edits keep their optimistic state.
      if (ctx?.previous) writeToCache(qc, new Map([[hash, ctx.previous]]))
    },
    onSuccess: (updated) => {
      writeToCache(qc, new Map([[updated.file_hash, updated]]))
      void qc.invalidateQueries({ queryKey: facetsKey })
    },
  })
}

interface BatchVars {
  request: BatchPhotoRequest
}

type NonDeleteAction = Exclude<BatchPhotoRequest['action'], 'delete'>

/** Apply one action to many photos, with the same optimistic-then-confirm-or-roll-back behaviour. */
export function useBatchUpdatePhotos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ request }: BatchVars) => {
      if (isDemoMode()) return { updated_count: request.photo_hashes.length, action: request.action, message: 'demo' }
      return batchUpdatePhotosApi(request)
    },
    onMutate: async ({ request }) => {
      await qc.cancelQueries({ queryKey: photosKey })
      if (request.action === 'delete') return { previous: new Map<string, PhotoMetadata>() }
      // Selected photos that were never loaded (select all) are updated on the server only.
      const previous = findCachedPhotos(qc, request.photo_hashes)
      const next = new Map<string, PhotoMetadata>()
      for (const [hash, photo] of previous) {
        next.set(hash, applyBatchAction(photo, request.action as NonDeleteAction, request.value))
      }
      writeToCache(qc, next)
      if (isDemoMode()) next.forEach(saveDemoPhoto)
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) writeToCache(qc, ctx.previous)
    },
    onSuccess: (_res, { request }) => {
      // Deleting removes records the optimistic path did not touch: reload the list.
      if (request.action === 'delete') void qc.invalidateQueries({ queryKey: photosKey })
      void qc.invalidateQueries({ queryKey: facetsKey })
    },
  })
}

/**
 * Curation actions for components: each awaits the server, reports failure as an error toast, and shows the
 * success message only after the save was confirmed. Resolves to whether it worked.
 */
export function useCuration() {
  const { mutateAsync: updateAsync } = useUpdatePhoto()
  const { mutateAsync: batchAsync } = useBatchUpdatePhotos()
  const showToast = useUiStore((s) => s.showToast)

  const patchPhoto = useCallback(
    async (hash: string, patch: PatchPhotoRequest, successMessage?: string): Promise<boolean> => {
      try {
        await updateAsync({ hash, patch })
        if (successMessage) showToast(successMessage)
        return true
      } catch (err) {
        showToast(`Not saved: ${errorMessage(err)}`, 'error')
        return false
      }
    },
    [updateAsync, showToast]
  )

  const batchPhotos = useCallback(
    async (request: BatchPhotoRequest, successMessage?: string): Promise<boolean> => {
      try {
        await batchAsync({ request })
        if (successMessage) showToast(successMessage)
        return true
      } catch (err) {
        showToast(`Not saved: ${errorMessage(err)}`, 'error')
        return false
      }
    },
    [batchAsync, showToast]
  )

  return { patchPhoto, batchPhotos }
}
