import { useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelJobApi,
  dismissJobApi,
  errorMessage,
  isJobFinished,
  listJobsApi,
  resumeJobApi,
  startIndexJobApi,
  startSyncJobApi,
} from '../api/client'
import type { SyncOptions } from '../api/client'
import type { Job } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode, photosKey } from './usePhotos'
import { facetsKey } from './useFacets'

/** Recent background jobs (index and sync), newest first. One cache entry shared by every component. */
export const jobsKey = ['jobs'] as const
const POLL_MS = 700

export type JobKind = 'index' | 'sync'

export interface StartJobInput {
  kind: JobKind
  folderPath: string
  sync?: SyncOptions
}

/** Whether the event stream (`useEventStream`) is connected. While it is not, running jobs are polled. */
export const eventsLiveKey = ['events', 'live'] as const

/** `job` in place of the cached copy with its id, or first in the list when it is new. */
export function upsertJob(jobs: Job[] | undefined, job: Job): Job[] {
  const list = jobs ?? []
  return list.some((j) => j.id === job.id) ? list.map((j) => (j.id === job.id ? job : j)) : [job, ...list]
}

/**
 * The job list. The event stream pushes changes; only while it is down is a running job
 * polled. Because it reads `GET /api/jobs`, a reload (or a second window) picks up a job
 * that is already running.
 */
export function useJobs() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: jobsKey,
    queryFn: listJobsApi,
    enabled: !isDemoMode(),
    refetchInterval: (query) => {
      if (qc.getQueryData(eventsLiveKey) === true) return false
      return query.state.data?.some((j) => !isJobFinished(j)) ? POLL_MS : false
    },
  })
  const jobs = data ?? []
  return {
    jobs,
    activeJob: jobs.find((j) => !isJobFinished(j)) ?? null,
    // Stopped by the app ending (ADR-003 R5a); it waits for the user to resume or dismiss it.
    interruptedJob: jobs.find((j) => j.status === 'interrupted') ?? null,
  }
}

/** A mutation on one job: its server record replaces the cached one; a failure is an error toast. */
function useJobMutation(call: (jobId: string) => Promise<Job>, verb: string) {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  return useMutation({
    mutationFn: call,
    onSuccess: (job) => qc.setQueryData<Job[]>(jobsKey, (jobs) => upsertJob(jobs, job)),
    onError: (err) => showToast(`${verb} failed: ${errorMessage(err)}`, 'error'),
  })
}

/** Start, cancel, resume and dismiss jobs. Failures to start (e.g. a 409 because the folder is busy) become error toasts. */
export function useJobActions() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)

  const start = useMutation({
    mutationFn: ({ kind, folderPath, sync }: StartJobInput) =>
      kind === 'index' ? startIndexJobApi(folderPath) : startSyncJobApi(folderPath, sync),
    onSuccess: (job) => qc.setQueryData<Job[]>(jobsKey, (jobs) => upsertJob(jobs, job)),
    onError: (err, { kind }) =>
      showToast(`${kind === 'index' ? 'Indexing' : 'Sync'} could not start: ${errorMessage(err)}`, 'error'),
  })

  const cancel = useJobMutation(cancelJobApi, 'Cancel')
  const resume = useJobMutation(resumeJobApi, 'Resume')
  const dismiss = useJobMutation(dismissJobApi, 'Dismiss')

  const startJob = useCallback((input: StartJobInput) => start.mutateAsync(input), [start])
  const cancelJob = useCallback((jobId: string) => cancel.mutate(jobId), [cancel])
  const resumeJob = useCallback((jobId: string) => resume.mutate(jobId), [resume])
  const dismissJob = useCallback((jobId: string) => dismiss.mutate(jobId), [dismiss])
  return { startJob, isStarting: start.isPending, cancelJob, resumeJob, dismissJob }
}

function finishedNotice(job: Job): { text: string; kind: 'success' | 'error' } {
  const what = ({ sync: 'Sync', analyze: 'Analysis', 'model-download': 'Model download' } as Record<string, string>)[job.kind] ?? 'Indexing'
  if (job.status === 'interrupted') {
    return { text: `${what} was interrupted. Resume it from the top bar.`, kind: 'error' }
  }
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
        void qc.invalidateQueries({ queryKey: facetsKey })
        void qc.invalidateQueries({ queryKey: ['analysis'] })
      }
    }
  }, [jobs, qc, showToast])
}
