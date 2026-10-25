import { useCallback, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addRootApi,
  dismissRootSuggestionsApi,
  errorMessage,
  fetchRootSuggestionsApi,
  getJobApi,
  listRootsApi,
  recheckRootsApi,
  removeRootApi,
} from '../api/client'
import type { Job } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode } from './usePhotos'
import { jobsKey, upsertJob } from './useJobs'

/** The folders the library rescans on start. */
export const rootsKey = ['roots'] as const
/** Folders found in an existing library's files, offered once as roots. */
export const rootSuggestionsKey = ['roots', 'suggestions'] as const

export function useRoots() {
  const { data } = useQuery({ queryKey: rootsKey, queryFn: listRootsApi, enabled: !isDemoMode() })
  return data ?? []
}

/** The offer to watch the folders an older library already uses. Empty when there is nothing to offer. */
export function useRootSuggestions() {
  const { data } = useQuery({
    queryKey: rootSuggestionsKey,
    queryFn: fetchRootSuggestionsApi,
    enabled: !isDemoMode(),
  })
  return data?.suggestions ?? []
}

/** Add, remove and skip roots. Failures become error toasts; a scan the server started shows up as a job. */
export function useRootActions() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const refresh = () => qc.invalidateQueries({ queryKey: rootsKey })

  const add = useMutation({
    mutationFn: ({ path, scan }: { path: string; scan?: boolean }) => addRootApi(path, scan),
    onSuccess: async (root) => {
      await refresh()
      if (!root.job_id) return
      // Put the scan in the jobs list now; the event stream keeps it current from here.
      const job: Job = await getJobApi(root.job_id)
      qc.setQueryData<Job[]>(jobsKey, (jobs) => upsertJob(jobs, job))
    },
    onError: (err) => showToast(`Could not add the folder: ${errorMessage(err)}`, 'error'),
  })

  const remove = useMutation({
    mutationFn: removeRootApi,
    onSuccess: refresh,
    onError: (err) => showToast(`Could not remove the folder: ${errorMessage(err)}`, 'error'),
  })

  const skip = useMutation({
    mutationFn: dismissRootSuggestionsApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: rootSuggestionsKey }),
    onError: (err) => showToast(`Could not skip: ${errorMessage(err)}`, 'error'),
  })

  const addRoot = useCallback((path: string, scan = true) => add.mutateAsync({ path, scan }), [add])
  const removeRoot = useCallback((path: string) => remove.mutate(path), [remove])
  const skipSuggestions = useCallback(() => skip.mutate(), [skip])
  return { addRoot, isAdding: add.isPending, removeRoot, skipSuggestions }
}

/** Do not ask the server to look at the roots again more often than this. */
export const RECHECK_THROTTLE_MS = 10_000

/**
 * Mount once (App): when the window gets focus again, tell the server to look at the watched folders
 * (a drive may have been plugged in while the app was in the background) and refresh their online state.
 * A quiet hint: nothing is shown and a failure is ignored.
 */
export function useRecheckRootsOnFocus() {
  const qc = useQueryClient()
  useEffect(() => {
    if (isDemoMode()) return
    let last = 0
    const onFocus = () => {
      const now = Date.now()
      if (now - last < RECHECK_THROTTLE_MS) return
      last = now
      recheckRootsApi()
        .then(() => qc.invalidateQueries({ queryKey: rootsKey }))
        .catch(() => {})
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [qc])
}
