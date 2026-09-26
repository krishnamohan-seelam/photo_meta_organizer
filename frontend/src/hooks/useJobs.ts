import { useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelJobApi,
  errorMessage,
  isJobFinished,
  listJobsApi,
  startIndexJobApi,
  startSyncJobApi,
} from '../api/client'
import type { Job, SyncOptions } from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode, photosKey } from './usePhotos'

/** Recent background jobs (index and sync), newest first. One cache entry shared by every component. */
export const jobsKey = ['jobs'] as const
const POLL_MS = 700

export type JobKind = 'index' | 'sync'

export interface StartJobInput {
  kind: JobKind
  folderPath: string
  sync?: SyncOptions
}

function upsert(jobs: Job[] | undefined, job: Job): Job[] {
  return [job, ...(jobs ?? []).filter((j) => j.id !== job.id)]
}

/**
 * The job list, polled only while a job is running. Because it reads `GET /api/jobs`,
 * a reload (or a second window) picks up a job that is already running.
 */
export function useJobs() {
  const { data } = useQuery({
    queryKey: jobsKey,
    queryFn: listJobsApi,
    enabled: !isDemoMode(),
    refetchInterval: (query) => (query.state.data?.some((j) => !isJobFinished(j)) ? POLL_MS : false),
  })
  const jobs = data ?? []
  return { jobs, activeJob: jobs.find((j) => !isJobFinished(j)) ?? null }
}

/** Start and cancel jobs. Failures to start (e.g. a 409 because the folder is busy) become error toasts. */
export function useJobActions() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)

  const start = useMutation({
    mutationFn: ({ kind, folderPath, sync }: StartJobInput) =>
      kind === 'index' ? startIndexJobApi(folderPath) : startSyncJobApi(folderPath, sync),
    onSuccess: (job) => qc.setQueryData<Job[]>(jobsKey, (jobs) => upsert(jobs, job)),
    onError: (err, { kind }) =>
      showToast(`${kind === 'index' ? 'Indexing' : 'Sync'} could not start: ${errorMessage(err)}`, 'error'),
  })

  const cancel = useMutation({
    mutationFn: cancelJobApi,
    onSuccess: (job) => qc.setQueryData<Job[]>(jobsKey, (jobs) => upsert(jobs, job)),
    onError: (err) => showToast(`Cancel failed: ${errorMessage(err)}`, 'error'),
  })

  const startJob = useCallback((input: StartJobInput) => start.mutateAsync(input), [start])
  const cancelJob = useCallback((jobId: string) => cancel.mutate(jobId), [cancel])
  return { startJob, isStarting: start.isPending, cancelJob }
}

function finishedNotice(job: Job): { text: string; kind: 'success' | 'error' } {
  const what = job.kind === 'sync' ? 'Sync' : 'Indexing'
  if (job.status === 'failed') return { text: `${what} failed: ${job.message}`, kind: 'error' }
  if (job.failed_count > 0) {
    const first = job.errors[0] ? ` First: ${job.errors[0]}` : ''
    return { text: `${job.message}${first}`, kind: 'error' }
  }
  return { text: job.message, kind: 'success' }
}

/**
 * Mount once (App): when a job this page saw running finishes, say how it went and reload the
 * library (even a failed or cancelled job may have saved some photos).
 */
export function useJobCompletionNotices() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const { jobs } = useJobs()
  const running = useRef(new Set<string>())

  useEffect(() => {
    for (const job of jobs) {
      if (!isJobFinished(job)) {
        running.current.add(job.id)
      } else if (running.current.delete(job.id)) {
        const { text, kind } = finishedNotice(job)
        showToast(text, kind)
        void qc.invalidateQueries({ queryKey: photosKey })
      }
    }
  }, [jobs, qc, showToast])
}
