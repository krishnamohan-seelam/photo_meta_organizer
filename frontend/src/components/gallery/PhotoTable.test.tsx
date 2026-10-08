import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { PaginatedPhotosResponse, PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { toSearchRequest } from '../../utils/search'
import { makePhoto } from '../../test/photos'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { PhotoTable } from './PhotoTable'
import { PhotoGallery } from './PhotoGallery'

const initial = useUiStore.getState()

function photosOf(n: number): PhotoMetadata[] {
  return Array.from({ length: n }, (_, i) => {
    const hash = i.toString(16).padStart(64, '0')
    return makePhoto({ file_hash: hash, file_info: { name: `IMG_${i}.jpg`, path: `/p/${i}`, size_bytes: 1000 + i, mime_type: 'image/jpeg' } })
  })
}

function seed(ui: React.ReactElement, photos: PhotoMetadata[]) {
  const qc = testQueryClient()
  const request = toSearchRequest({ ...useUiStore.getState() })
  const page: PaginatedPhotosResponse = { items: photos, total_count: photos.length, page: 1, page_size: photos.length, total_pages: 1 }
  qc.setQueryData(['photos', 'search', request], { pages: [page], pageParams: [1] })
  return renderWithQuery(ui, qc)
}

// jsdom has no layout: give every element a 1200 × 800 box so the virtualizers render rows.
beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  )
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(1200)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(800)
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1200)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, top: 0, left: 0, width: 1200, height: 800, right: 1200, bottom: 800, toJSON: () => ({}) })
})
beforeEach(() => {
  useUiStore.setState({ ...initial, sortBy: 'captured_at', sortOrder: 'desc', topPhotoIndex: 0 })
  useSelectionStore.getState().clearSelection()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PhotoTable sorting (FR-2c.3, AC-2c.1)', () => {
  it('a sortable header sorts in its natural order first, then reverses', () => {
    seed(<PhotoTable />, photosOf(3))
    fireEvent.click(screen.getByRole('button', { name: 'Name' }))
    expect(useUiStore.getState()).toMatchObject({ sortBy: 'file_name', sortOrder: 'asc' })
    fireEvent.click(screen.getByRole('button', { name: 'Name' }))
    expect(useUiStore.getState()).toMatchObject({ sortBy: 'file_name', sortOrder: 'desc' })
    fireEvent.click(screen.getByRole('button', { name: 'Size' }))
    expect(useUiStore.getState()).toMatchObject({ sortBy: 'size_bytes', sortOrder: 'desc' })
  })

  it('the current sort column shows aria-sort', () => {
    seed(<PhotoTable />, photosOf(3))
    const captured = screen.getAllByRole('columnheader').find((h) => h.textContent?.startsWith('Captured'))!
    expect(captured.getAttribute('aria-sort')).toBe('descending')
  })

  it('non-sortable headers have no sort control', () => {
    seed(<PhotoTable />, photosOf(3))
    const lens = screen.getAllByRole('columnheader').find((h) => h.textContent === 'Lens')!
    expect(lens.querySelector('button')).toBeNull()
    expect(lens.getAttribute('aria-sort')).toBeNull()
    expect(screen.queryByRole('button', { name: 'ISO' })).toBeNull()
  })
})

describe('PhotoTable selection (FR-2c.5, AC-2c.2)', () => {
  it('Shift-click selects exactly the range from the clicked row', () => {
    const photos = photosOf(6)
    seed(<PhotoTable />, photos)
    const rows = screen.getAllByRole('row').slice(1)
    fireEvent.click(rows[1])
    fireEvent.click(rows[4], { shiftKey: true })
    expect([...useSelectionStore.getState().selectedHashes].sort()).toEqual(photos.slice(1, 5).map((p) => p.file_hash).sort())
    expect(useUiStore.getState().inspectedHash).toBe(photos[4].file_hash)
  })

  it('Ctrl-click toggles one row', () => {
    const photos = photosOf(3)
    seed(<PhotoTable />, photos)
    const rows = screen.getAllByRole('row').slice(1)
    fireEvent.click(rows[2], { ctrlKey: true })
    expect([...useSelectionStore.getState().selectedHashes]).toEqual([photos[2].file_hash])
  })

  it('the header checkbox selects every match through Select All', async () => {
    const photos = photosOf(3)
    seed(<PhotoTable />, photos)
    const ids = photos.map((p) => ({ file_hash: p.file_hash, size_bytes: p.file_info.size_bytes }))
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(ids), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all matching photos' }))
    await waitFor(() => expect(useSelectionStore.getState().selectedHashes.size).toBe(3))
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toContain('/search/ids')
  })
})

describe('virtualization keeps the DOM bounded (AC-1c.3, AC-2c.3)', () => {
  it('the table renders at most 60 rows of 20 000', () => {
    seed(<PhotoTable />, photosOf(20_000))
    const rows = screen.getAllByRole('row').length - 1
    expect(rows).toBeGreaterThan(0)
    expect(rows).toBeLessThanOrEqual(60)
  })

  it('the grid renders at most 60 rows of 20 000', () => {
    const { container } = seed(<PhotoGallery />, photosOf(20_000))
    const rows = container.querySelectorAll('.jrow')
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.length).toBeLessThanOrEqual(60)
  })
})
