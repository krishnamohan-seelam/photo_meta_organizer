import { useCallback, useState } from 'react'
import { errorMessage, exportJsonApi, exportZipApi } from '../api/client'
import { useUiStore } from '../stores/useUiStore'

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/**
 * ZIP and JSON export (PMO-28): downloads through the server, toasts the outcome and,
 * for a ZIP, reports streamed progress (0..1) while it downloads.
 */
export function useExport() {
  const showToast = useUiStore((s) => s.showToast)
  const [zipProgress, setZipProgress] = useState<number | null>(null)
  const [jsonBusy, setJsonBusy] = useState(false)

  const exportZip = useCallback(
    async (hashes: string[]) => {
      setZipProgress(0)
      try {
        // Re-render on whole-percent steps only, not on every network chunk.
        let shown = 0
        const onProgress = (fraction: number) => {
          const step = Math.floor(fraction * 100) / 100
          if (step !== shown) {
            shown = step
            setZipProgress(step)
          }
        }
        const result = await exportZipApi(hashes, onProgress)
        const skipped = result.skipped ? `; ${plural(result.skipped, 'photo')} skipped (see export_report.txt)` : ''
        showToast(`Exported ${plural(result.files ?? hashes.length, 'photo')} to ${result.filename}${skipped}`, result.skipped ? 'error' : 'success')
      } catch (err) {
        showToast(errorMessage(err), 'error')
      } finally {
        setZipProgress(null)
      }
    },
    [showToast]
  )

  /** Metadata of `hashes`, or of the whole library when omitted or empty. */
  const exportJson = useCallback(
    async (hashes?: string[]) => {
      setJsonBusy(true)
      try {
        const result = await exportJsonApi(hashes && hashes.length > 0 ? hashes : undefined)
        showToast(`Exported metadata to ${result.filename}`)
      } catch (err) {
        showToast(errorMessage(err), 'error')
      } finally {
        setJsonBusy(false)
      }
    },
    [showToast]
  )

  return { exportZip, zipProgress, exportJson, jsonBusy }
}
