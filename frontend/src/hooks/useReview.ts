import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  acceptAboveApi,
  errorMessage,
  fetchReviewCountApi,
  fetchReviewItemsApi,
  fetchReviewLabelsApi,
  resolveAiTagApi,
} from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { analysisKey } from './useAnalysis'
import { facetsKey } from './useFacets'
import { isDemoMode, photosKey } from './usePhotos'

// Under the analysis key, so every AI-tag change that refreshes `['analysis']` refreshes these too.
const reviewKey = [...analysisKey, 'review'] as const
/** How many suggestions of one label the review loads at a time. */
export const REVIEW_BATCH = 200

/** Labels that still have open suggestions, best first. */
export function useReviewLabels(enabled: boolean) {
  return useQuery({
    queryKey: [...reviewKey, 'labels'],
    queryFn: fetchReviewLabelsApi,
    enabled: enabled && !isDemoMode(),
    retry: false,
  })
}

/** The open suggestions of one label, most confident first. */
export function useReviewItems(label: string | null) {
  return useQuery({
    queryKey: [...reviewKey, 'items', label],
    queryFn: () => fetchReviewItemsApi(label ?? '', REVIEW_BATCH),
    enabled: label !== null && !isDemoMode(),
    retry: false,
  })
}

/** What "accept all at or above" would accept right now. */
export function useReviewCount(label: string | null, minConfidence: number) {
  return useQuery({
    queryKey: [...reviewKey, 'count', label, minConfidence],
    queryFn: () => fetchReviewCountApi(label ?? '', minConfidence),
    enabled: label !== null && !isDemoMode(),
    retry: false,
  })
}

/** Accept or reject one suggestion. Accepting adds a real label, so photo caches refresh. */
export function useReviewDecision() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: ({ hash, label, action }: { hash: string; label: string; action: 'accept' | 'reject' }) =>
      resolveAiTagApi(hash, label, action),
    onSuccess: (_tags, { action }) => {
      void qc.invalidateQueries({ queryKey: analysisKey })
      if (action === 'accept') {
        void qc.invalidateQueries({ queryKey: photosKey })
        void qc.invalidateQueries({ queryKey: facetsKey })
      }
    },
    onError: (err) => showToast(`Could not save: ${errorMessage(err)}`, 'error'),
  })
}

/** Accept a label on every photo at or above a confidence; resolves to how many were accepted. */
export function useAcceptAbove() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useCallback(
    async (label: string, minConfidence: number) => {
      try {
        const r = await acceptAboveApi(label, minConfidence)
        showToast(`Accepted “${label}” on ${r.photos_changed} photo${r.photos_changed === 1 ? '' : 's'}`)
        void qc.invalidateQueries({ queryKey: analysisKey })
        void qc.invalidateQueries({ queryKey: photosKey })
        void qc.invalidateQueries({ queryKey: facetsKey })
        return r.photos_changed
      } catch (err) {
        showToast(`Could not accept: ${errorMessage(err)}`, 'error')
        return 0
      }
    },
    [qc, showToast]
  )
}
