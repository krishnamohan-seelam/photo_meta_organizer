import { useCallback, useMemo } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  errorMessage,
  fetchAiTagCountsApi,
  fetchAiTagsApi,
  fetchAnalysisStatusApi,
  resolveAiTagApi,
  resolveAiTagsBatchApi,
  semanticSearchApi,
  startAnalysisApi,
  startModelDownloadApi,
} from '../api/client'
import type { AiTag, AnalysisStatus, Job, SemanticSearchRequest } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import type { SemanticQuery } from '../stores/useUiStore'
import { isDemoMode, photosKey, useSearchRequest } from './usePhotos'
import { jobsKey } from './useJobs'

export const analysisKey = ['analysis'] as const
const STATUS_POLL_MS = 1500
/** How many matches a "by meaning" search shows. */
export const SEMANTIC_K = 60

/** What the AI features need and how far along analysis is. Not available in `?demo=1`. */
export function useAnalysisStatus(): AnalysisStatus | undefined {
  const query = useQuery({
    queryKey: [...analysisKey, 'status'],
    queryFn: fetchAnalysisStatusApi,
    enabled: !isDemoMode(),
    refetchInterval: (q) => (q.state.data?.active_job_id ? STATUS_POLL_MS : false),
  })
  return query.data
}

/** True once at least one photo can be searched by meaning. */
export function aiSearchReady(status: AnalysisStatus | undefined): boolean {
  return Boolean(status?.runtime_installed && status.model_installed && status.analyzed_photos > 0)
}

function upsertJob(jobs: Job[] | undefined, job: Job): Job[] {
  return [job, ...(jobs ?? []).filter((j) => j.id !== job.id)]
}

/** Start the (consented) model download, or the analysis. Both then show in the job pill. */
export function useAnalysisActions() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const onStarted = (job: Job) => {
    qc.setQueryData<Job[]>(jobsKey, (jobs) => upsertJob(jobs, job))
    void qc.invalidateQueries({ queryKey: analysisKey })
  }
  const download = useMutation({
    mutationFn: startModelDownloadApi,
    onSuccess: onStarted,
    onError: (err) => showToast(`Download could not start: ${errorMessage(err)}`, 'error'),
  })
  const analyze = useMutation({
    mutationFn: startAnalysisApi,
    onSuccess: onStarted,
    onError: (err) => showToast(`Analysis could not start: ${errorMessage(err)}`, 'error'),
  })
  return {
    /** Resolve to whether the job started (a failure already showed a toast). */
    startDownload: useCallback(() => download.mutateAsync().then(() => true, () => false), [download]),
    startAnalysis: useCallback(() => analyze.mutateAsync({}).then(() => true, () => false), [analyze]),
    isStarting: download.isPending || analyze.isPending,
  }
}

/**
 * The best matches for a semantic query under the Library's current filters. Disabled when no
 * semantic query is set, so ordinary browsing never loads the model.
 */
export function useSemanticSearch(semantic: SemanticQuery | null, k: number = SEMANTIC_K, useFilters: boolean = true) {
  const libraryFilters = useSearchRequest()
  const filters = useFilters ? libraryFilters : {}
  const request: SemanticSearchRequest | null = semantic
    ? {
        ...filters,
        ...(semantic.kind === 'text' ? { text: semantic.text } : { like_hash: semantic.hash }),
        k,
      }
    : null
  return useQuery({
    queryKey: [...analysisKey, 'semantic', request],
    queryFn: () => semanticSearchApi(request!),
    enabled: request !== null && !isDemoMode(),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

/** Suggested labels and how many photos carry each as an open suggestion. */
export function useAiTagCounts(enabled: boolean) {
  return useQuery({
    queryKey: [...analysisKey, 'counts'],
    queryFn: fetchAiTagCountsApi,
    enabled: enabled && !isDemoMode(),
    retry: false,
  })
}

/** The photos of the active search by meaning (empty when none), in rank order. */
export function useSemanticPhotos() {
  const semantic = useUiStore((s) => s.semantic)
  const limit = useUiStore((s) => s.semanticLimit)
  const query = useSemanticSearch(semantic, limit)
  const hits = query.data?.items
  const photos = useMemo(() => (semantic ? (hits ?? []).map((h) => h.photo) : []), [semantic, hits])
  return { semantic, limit, query, hits: hits ?? [], photos }
}

/** A photo's suggested tags (any status). */
export function usePhotoAiTags(hash: string, enabled: boolean = true) {
  return useQuery({
    queryKey: [...analysisKey, 'tags', hash],
    queryFn: () => fetchAiTagsApi(hash),
    enabled: enabled && !isDemoMode(),
    retry: false,
  })
}

/** Accept, reject or reopen one suggestion. Accepting adds a real label, so photo caches refresh. */
export function useResolveAiTag(hash: string) {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: ({ label, action }: { label: string; action: 'accept' | 'reject' | 'reset' }) =>
      resolveAiTagApi(hash, label, action),
    onSuccess: (tags: AiTag[], { action }) => {
      qc.setQueryData([...analysisKey, 'tags', hash], tags)
      void qc.invalidateQueries({ queryKey: [...analysisKey, 'counts'] })
      if (action === 'accept' || useUiStore.getState().filterAiTag) {
        void qc.invalidateQueries({ queryKey: photosKey })
        void qc.invalidateQueries({ queryKey: ['facets'] })
      }
    },
    onError: (err) => showToast(`Could not save: ${errorMessage(err)}`, 'error'),
  })
}

/** Accept (or dismiss) every open suggestion of the selected photos. */
export function useResolveAiTagsBatch() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useCallback(
    async (hashes: string[], action: 'accept' | 'reject') => {
      try {
        const r = await resolveAiTagsBatchApi(hashes, action)
        const verb = action === 'accept' ? 'Accepted' : 'Dismissed'
        const tags = `${r.tags_changed} suggested tag${r.tags_changed === 1 ? '' : 's'}`
        showToast(
          r.tags_changed === 0
            ? 'No open suggestions on these photos'
            : `${verb} ${tags} on ${r.photos_changed} photo${r.photos_changed === 1 ? '' : 's'}`
        )
        void qc.invalidateQueries({ queryKey: analysisKey })
        if (action === 'accept') {
          void qc.invalidateQueries({ queryKey: photosKey })
          void qc.invalidateQueries({ queryKey: ['facets'] })
        }
      } catch (err) {
        showToast(`Could not save: ${errorMessage(err)}`, 'error')
      }
    },
    [qc, showToast]
  )
}
