import { useEffect, useRef } from 'react'
import type { PhotoMetadata } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { useSelectionStore } from '../stores/useSelectionStore'
import { shouldIgnoreHotkey } from '../utils/hotkeys'
import { dialogOpen } from '../utils/shortcuts'
import { useCuration } from './usePhotoMutations'

/** Keys that step the inspected photo: back, forward. The grid uses ←/→; the table adds ↑/↓ and K/J. */
export interface StepKeys {
  previous: string[]
  next: string[]
}

export const GRID_STEP_KEYS: StepKeys = { previous: ['ArrowLeft'], next: ['ArrowRight'] }

interface Options {
  photos: PhotoMetadata[]
  /** Scroll the photo at this index into view. */
  reveal: (index: number) => void
  /** Load the next page when stepping past the last loaded photo; null when everything is loaded. */
  loadMore: (() => void) | null
  stepKeys?: StepKeys
  /** Whether Space toggles the selection (table) instead of opening the viewer (grid). */
  spaceSelects?: boolean
  /** Shift + a step key extends the selection (table). */
  onShiftStep?: (from: number, to: number) => void
}

/** Enter/Space act on the inspected photo only from the page or a photo tile, never from another control. */
function activatesPhoto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return true
  if (target === document.body) return true
  return target.dataset.photoIndex !== undefined
}

/**
 * Culling from the keyboard in the Library view (FR-1f.1): arrows move the inspected photo, 1-5/0 rate,
 * P picks, X selects, Enter opens the viewer and Esc clears the selection. Quiet while typing, with a
 * modifier, or while a dialog (the viewer included) is open.
 */
export function useLibraryHotkeys({ photos, reveal, loadMore, stepKeys = GRID_STEP_KEYS, spaceSelects = false, onShiftStep }: Options): void {
  const { patchPhoto } = useCuration()
  // The listener is registered once; it reads the latest values through a ref.
  const latest = useRef({ photos, reveal, loadMore, stepKeys, spaceSelects, onShiftStep, patchPhoto })
  useEffect(() => {
    latest.current = { photos, reveal, loadMore, stepKeys, spaceSelects, onShiftStep, patchPhoto }
  })

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Shift is not a reason to ignore: Shift + a step key extends the selection in the table.
      if (shouldIgnoreHotkey(e) || dialogOpen()) return

      const { photos, reveal, loadMore, stepKeys, spaceSelects, onShiftStep, patchPhoto } = latest.current
      const ui = useUiStore.getState()
      const selection = useSelectionStore.getState()
      const index = photos.findIndex((p) => p.file_hash === ui.inspectedHash)
      const current = index >= 0 ? photos[index] : undefined
      const key = e.key

      const step = stepKeys.previous.includes(key) ? -1 : stepKeys.next.includes(key) ? 1 : 0
      if (step !== 0) {
        if (photos.length === 0) return
        e.preventDefault()
        const from = index < 0 ? (step > 0 ? -1 : photos.length) : index
        const to = Math.min(photos.length - 1, Math.max(0, from + step))
        if (to === photos.length - 1 && step > 0 && loadMore) loadMore()
        if (e.shiftKey && onShiftStep) onShiftStep(Math.max(0, from), to)
        ui.setInspectedHash(photos[to].file_hash)
        reveal(to)
        return
      }
      if (e.shiftKey) return

      if (key === 'Escape') {
        if (selection.selectedHashes.size > 0) {
          e.preventDefault()
          selection.clearSelection()
        }
        return
      }
      if (!current) return

      const lower = key.toLowerCase()
      if (/^[0-5]$/.test(key)) {
        e.preventDefault()
        const rating = Number(key)
        void patchPhoto(current.file_hash, { rating: rating === 0 ? null : rating }, rating === 0 ? 'Rating cleared' : `Rated ${rating} ★`)
      } else if (lower === 'p') {
        e.preventDefault()
        const next = !current.flagged
        void patchPhoto(current.file_hash, { flagged: next }, next ? 'Picked' : 'Pick removed')
      } else if (lower === 'x' || (key === ' ' && spaceSelects && activatesPhoto(e.target))) {
        e.preventDefault()
        selection.toggleSelect(current.file_hash, current.file_info.size_bytes)
      } else if ((key === 'Enter' || (key === ' ' && !spaceSelects)) && activatesPhoto(e.target)) {
        e.preventDefault()
        ui.setLightboxIndex(index)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
