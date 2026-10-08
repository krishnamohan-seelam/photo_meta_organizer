import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { PaginatedPhotosResponse, PhotoMetadata } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { useSelectionStore } from '../stores/useSelectionStore'
import { makePhoto } from '../test/photos'
import { renderWithQuery, testQueryClient } from '../test/render'
import { useLibraryHotkeys } from './useLibraryHotkeys'

const photos: PhotoMetadata[] = ['a', 'b', 'c'].map((c) => makePhoto({ file_hash: c.repeat(64), rating: null }))
const searchKey = ['photos', 'search', { sort_by: 'captured_at' }]

function Harness({ reveal = () => {} }: { reveal?: (i: number) => void }) {
  useLibraryHotkeys({ photos, reveal, loadMore: null })
  return <input aria-label="typing here" />
}

function setup(reveal?: (i: number) => void) {
  const qc = testQueryClient()
  const page: PaginatedPhotosResponse = { items: photos, total_count: 3, page: 1, page_size: 200, total_pages: 1 }
  qc.setQueryData(searchKey, page)
  renderWithQuery(<Harness reveal={reveal} />, qc)
  return { rating: (i: number) => qc.getQueryData<PaginatedPhotosResponse>(searchKey)!.items[i].rating }
}

beforeEach(() => {
  useUiStore.setState({ inspectedHash: photos[0].file_hash, lightboxIndex: null })
  useSelectionStore.getState().clearSelection()
})
afterEach(() => vi.unstubAllGlobals())

describe('Library culling hotkeys (FR-1f.1)', () => {
  it('arrows move the inspected photo and reveal it', () => {
    const reveal = vi.fn()
    setup(reveal)
    fireEvent.keyDown(document.body, { key: 'ArrowRight' })
    expect(useUiStore.getState().inspectedHash).toBe(photos[1].file_hash)
    expect(reveal).toHaveBeenLastCalledWith(1)
    fireEvent.keyDown(document.body, { key: 'ArrowLeft' })
    fireEvent.keyDown(document.body, { key: 'ArrowLeft' })
    expect(useUiStore.getState().inspectedHash).toBe(photos[0].file_hash)
  })

  it('1-5 rate the inspected photo (optimistically)', async () => {
    const { rating } = setup()
    fireEvent.keyDown(document.body, { key: '3' })
    await waitFor(() => expect(rating(0)).toBe(3))
  })

  it('X toggles the selection, Esc clears it, Enter opens the viewer', () => {
    setup()
    fireEvent.keyDown(document.body, { key: 'x' })
    expect(useSelectionStore.getState().selectedHashes.has(photos[0].file_hash)).toBe(true)
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(useSelectionStore.getState().selectedHashes.size).toBe(0)
    fireEvent.keyDown(document.body, { key: 'Enter' })
    expect(useUiStore.getState().lightboxIndex).toBe(0)
  })

  it('do nothing while typing (AC-1f.1)', async () => {
    const { rating } = setup()
    const input = screen.getByRole('textbox', { name: 'typing here' })
    input.focus()
    for (const key of ['ArrowRight', '4', 'x', 'p', 'Enter']) fireEvent.keyDown(input, { key })
    expect(useUiStore.getState().inspectedHash).toBe(photos[0].file_hash)
    expect(useSelectionStore.getState().selectedHashes.size).toBe(0)
    expect(useUiStore.getState().lightboxIndex).toBeNull()
    expect(rating(0)).toBeNull()
  })

  it('do nothing while a dialog is open (AC-1f.1)', () => {
    setup()
    const dialog = document.createElement('div')
    dialog.setAttribute('aria-modal', 'true')
    document.body.appendChild(dialog)
    fireEvent.keyDown(document.body, { key: 'ArrowRight' })
    fireEvent.keyDown(document.body, { key: 'x' })
    dialog.remove()
    expect(useUiStore.getState().inspectedHash).toBe(photos[0].file_hash)
    expect(useSelectionStore.getState().selectedHashes.size).toBe(0)
  })
})
