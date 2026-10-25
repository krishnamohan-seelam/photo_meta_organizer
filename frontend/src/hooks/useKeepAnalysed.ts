import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage, fetchKeepAnalysedApi, setKeepAnalysedApi } from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { analysisKey } from './useAnalysis'
import { isDemoMode } from './usePhotos'

const keepKey = [...analysisKey, 'keep'] as const

/** Whether new photos are analysed automatically, and why it is or is not running right now. */
export function useKeepAnalysed(enabled: boolean = true) {
  return useQuery({
    queryKey: keepKey,
    queryFn: fetchKeepAnalysedApi,
    enabled: enabled && !isDemoMode(),
    retry: false,
  })
}

/** Turn automatic analysis on or off. */
export function useSetKeepAnalysed() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: setKeepAnalysedApi,
    onSuccess: (status) => qc.setQueryData(keepKey, status),
    onError: (err) => showToast(`Could not save: ${errorMessage(err)}`, 'error'),
  })
}
