import { useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { BatchPhotoRequest, PatchPhotoRequest, PhotoMetadata } from '../types/metadata'
import { batchUpdatePhotosApi, errorMessage, patchPhotoApi } from '../api/client'
import { applyBatchAction, applyPatch } from '../utils/photoPatch'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode, photosKey } from './usePhotos'

type Photos = PhotoMetadata[] | undefined

interface PatchVars {
  hash: string
  patch: PatchPhotoRequest
}

/** Swap in changed photos by hash, leaving every other record (and its object identity) alone. */
function replaceMany(photos: Photos, changed: Map<string, PhotoMetadata>): Photos {
  if (!photos || changed.size === 0) return photos
  return photos.map((p) => changed.get(p.file_hash) ?? p)
}

/**
 * Edit one photo. The cache is updated at once (optimistic), replaced by the server's record on success and
 * put back on failure, so the UI never shows a save that did not happen.
 */
export function useUpdatePhoto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ hash, patch }: PatchVars): Promise<PhotoMetadata> => {
      if (isDemoMode()) {
        // Demo data lives only in memory: there is no backend to confirm with.
        const current = qc.getQueryData<PhotoMetadata[]>(photosKey)?.find((p) => p.file_hash === hash)
        if (!current) throw new Error('Photo not found')
        return applyPatch(current, patch)
      }
      return patchPhotoApi(hash, patch)
    },
    onMutate: async ({ hash, patch }) => {
      await qc.cancelQueries({ queryKey: photosKey })
      const previous = qc.getQueryData<PhotoMetadata[]>(photosKey)?.find((p) => p.file_hash === hash)
      if (previous) {
        qc.setQueryData<Photos>(photosKey, (old) => replaceMany(old, new Map([[hash, applyPatch(previous, patch)]])))
      }
      return { previous }
    },
    onError: (_err, { hash }, ctx) => {
      // Roll back only this photo: other in-flight edits keep their optimistic state.
      const previous = ctx?.previous
      if (previous) qc.setQueryData<Photos>(photosKey, (old) => replaceMany(old, new Map([[hash, previous]])))
    },
    onSuccess: (updated) => {
      qc.setQueryData<Photos>(photosKey, (old) => replaceMany(old, new Map([[updated.file_hash, updated]])))
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
      const previous = new Map<string, PhotoMetadata>()
      if (request.action === 'delete') return { previous }
      const wanted = new Set(request.photo_hashes)
      const next = new Map<string, PhotoMetadata>()
      for (const p of qc.getQueryData<PhotoMetadata[]>(photosKey) ?? []) {
        if (!wanted.has(p.file_hash)) continue
        previous.set(p.file_hash, p)
        next.set(p.file_hash, applyBatchAction(p, request.action as NonDeleteAction, request.value))
      }
      qc.setQueryData<Photos>(photosKey, (old) => replaceMany(old, next))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx) qc.setQueryData<Photos>(photosKey, (old) => replaceMany(old, ctx.previous))
    },
    onSuccess: (_res, { request }) => {
      // Deleting removes records the optimistic path did not touch: reload the list.
      if (request.action === 'delete') void qc.invalidateQueries({ queryKey: photosKey })
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
