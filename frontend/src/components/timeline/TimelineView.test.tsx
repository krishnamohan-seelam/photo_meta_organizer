import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import type { PaginatedPhotosResponse, PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { toSearchRequest } from '../../utils/search'
import { makePhoto } from '../../test/photos'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { TimelineView } from './TimelineView'

const initial = useUiStore.getState()

function shot(i: number, capturedAt: string): PhotoMetadata {
  const photo = makePhoto({ file_hash: i.toString(16).padStart(64, '0') })
  photo.exif = { ...photo.exif, captured_at: capturedAt }
  return photo
}

const photos = [
  shot(1, '2026-05-21T10:00:00'),
  shot(2, '2026-05-20T10:00:00'),
  shot(3, '2026-05-17T10:00:00'), // 72 h before the previous: a new chapter at 36 h
  shot(4, '2026-05-16T10:00:00'),
]

function renderTimeline() {
  const qc = testQueryClient()
  const request = toSearchRequest({ ...useUiStore.getState() })
  const page: PaginatedPhotosResponse = { items: photos, total_count: photos.length, page: 1, page_size: 200, total_pages: 1 }
  qc.setQueryData(['photos', 'search', request], { pages: [page], pageParams: [1] })
  qc.setQueryData(['facets'], { cameras: [], tags: [], years: [{ name: '2026', count: 4 }], isos: [], gps_bounds: null, stats: { total_count: 4, flagged_count: 0, geotagged_count: 0, undated_count: 0, total_bytes: 0, avg_megapixels: 0 } })
  return renderWithQuery(<TimelineView />, qc)
}

beforeEach(() => useUiStore.setState({ ...initial, sortBy: 'captured_at', sortOrder: 'desc', chapterGapHours: 36 }))
afterEach(() => vi.unstubAllGlobals())

describe('TimelineView chapters (FR-3)', () => {
  it('groups the loaded photos into dated chapters', () => {
    renderTimeline()
    expect(screen.getByRole('heading', { name: '20–21 May 2026' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '16–17 May 2026' })).toBeTruthy()
  })

  it('a longer gap regroups without a new request (FR-3.10)', () => {
    renderTimeline()
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    const before = fetchMock.mock.calls.length
    fireEvent.change(screen.getByRole('combobox', { name: 'Chapter gap' }), { target: { value: '168' } })
    expect(screen.getByRole('heading', { name: '16–21 May 2026' })).toBeTruthy()
    expect(useUiStore.getState().chapterGapHours).toBe(168)
    expect(fetchMock.mock.calls.length).toBe(before)
  })

  it('Select chapter adds its photos to the selection', async () => {
    const { useSelectionStore } = await import('../../stores/useSelectionStore')
    useSelectionStore.getState().clearSelection()
    renderTimeline()
    fireEvent.click(screen.getAllByRole('button', { name: /Select chapter/ })[0])
    expect([...useSelectionStore.getState().selectedHashes].sort()).toEqual([photos[0].file_hash, photos[1].file_hash].sort())
  })
})

describe('sort dependency (FR-3.8, AC-3.4)', () => {
  it('another sort shows the notice and a flat mosaic, and never re-sorts on its own', () => {
    useUiStore.setState({ sortBy: 'file_name', sortOrder: 'asc' })
    renderTimeline()
    expect(screen.getByRole('status').textContent).toContain('Chapters follow capture date.')
    expect(screen.queryAllByRole('heading')).toHaveLength(0)
    expect(document.querySelectorAll('.mtile')).toHaveLength(4)
    expect(useUiStore.getState().sortBy).toBe('file_name')

    fireEvent.click(screen.getByRole('button', { name: 'Sort by date' }))
    expect(useUiStore.getState()).toMatchObject({ sortBy: 'captured_at', sortOrder: 'desc' })
  })
})
