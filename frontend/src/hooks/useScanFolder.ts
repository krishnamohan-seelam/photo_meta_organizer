import { useCallback } from 'react'
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage, getJobApi, isJobFinished, startIndexJobApi } from '../api/client'
import type { Job } from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { photosKey } from './usePhotos'

const SCAN_KEY = ['index-folder']
const POLL_MS = 500

/** Start an index job and poll it until it finishes (PMO-18: indexing no longer holds a request open). */
async function runIndexJob(folderPath: string): Promise<Job> {
  let job = await startIndexJobApi(folderPath)
  while (!isJobFinished(job)) {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS))
    job = await getJobApi(job.id)
  }
  return job
}

/** Ask for a folder (native picker in the desktop app, a prompt in the browser) and index it. */
export function useScanFolder() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const isScanning = useIsMutating({ mutationKey: SCAN_KEY }) > 0

  const { mutateAsync } = useMutation({
    mutationKey: SCAN_KEY,
    mutationFn: runIndexJob,
    // Even a failed or cancelled job may have saved some photos.
    onSettled: () => qc.invalidateQueries({ queryKey: photosKey }),
  })

  const scan = useCallback(async () => {
    const folderPath = window.electronAPI?.openDirectory
      ? await window.electronAPI.openDirectory()
      : window.prompt('Enter absolute folder path to index:')
    if (!folderPath) return

    showToast(`Indexing folder: ${folderPath}...`)
    try {
      const job = await mutateAsync(folderPath)
      if (job.status === 'failed') showToast(`Indexing failed: ${job.message}`, 'error')
      else showToast(job.message, job.failed_count > 0 ? 'error' : 'success')
    } catch (err) {
      showToast(`Indexing failed: ${errorMessage(err)}`, 'error')
    }
  }, [mutateAsync, showToast])

  return { scan, isScanning }
}
