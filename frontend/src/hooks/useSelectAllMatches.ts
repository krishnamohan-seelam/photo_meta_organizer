import { useCallback, useState } from 'react'
import { errorMessage, searchPhotoIdsApi } from '../api/client'
import { demoSearchIds } from '../demo/demoLibrary'
import { useSelectionStore } from '../stores/useSelectionStore'
import { useUiStore } from '../stores/useUiStore'
import { isDemoMode, useSearchRequest } from './usePhotos'

/** Select every match of the current filters, pages not loaded yet included (`POST /api/search/ids`). */
export function useSelectAllMatches() {
  const request = useSearchRequest()
  const [busy, setBusy] = useState(false)

  const selectAllMatches = useCallback(async () => {
    setBusy(true)
    try {
      const ids = await (isDemoMode() ? demoSearchIds(request) : searchPhotoIdsApi(request))
      useSelectionStore.getState().selectAll(ids)
      useUiStore.getState().showToast(`Selected all ${ids.length} photos`)
    } catch (err) {
      useUiStore.getState().showToast(errorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }, [request])

  return { selectAllMatches, busy }
}
