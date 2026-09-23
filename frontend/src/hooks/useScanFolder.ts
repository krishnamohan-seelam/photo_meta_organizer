import { useCallback } from 'react'
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query'
import { errorMessage, indexFolderApi } from '../api/client'
import { useUiStore } from '../stores/useUiStore'
import { photosKey } from './usePhotos'

const SCAN_KEY = ['index-folder']

/** Ask for a folder (native picker in the desktop app, a prompt in the browser) and index it. */
export function useScanFolder() {
  const qc = useQueryClient()
  const showToast = useUiStore((s) => s.showToast)
  const isScanning = useIsMutating({ mutationKey: SCAN_KEY }) > 0

  const { mutateAsync } = useMutation({
    mutationKey: SCAN_KEY,
    mutationFn: (folderPath: string) => indexFolderApi(folderPath),
    onSuccess: () => qc.invalidateQueries({ queryKey: photosKey }),
  })

  const scan = useCallback(async () => {
    const folderPath = window.electronAPI?.openDirectory
      ? await window.electronAPI.openDirectory()
      : window.prompt('Enter absolute folder path to index:')
    if (!folderPath) return

    showToast(`Indexing folder: ${folderPath}...`)
    try {
      showToast((await mutateAsync(folderPath)).message)
    } catch (err) {
      showToast(`Indexing failed: ${errorMessage(err)}`, 'error')
    }
  }, [mutateAsync, showToast])

  return { scan, isScanning }
}
