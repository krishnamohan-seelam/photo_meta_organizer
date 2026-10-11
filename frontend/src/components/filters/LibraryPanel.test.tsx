import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import type { Facets } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { LibraryPanel } from './LibraryPanel'

const initial = useUiStore.getState()

const facets: Facets = {
  cameras: [
    { name: 'Canon', count: 2 },
    { name: 'Sony', count: 8 },
  ],
  tags: [
    { name: 'iceland', count: 3 },
    { name: 'night', count: 2 },
  ],
  years: [],
  isos: [],
  gps_bounds: null,
  stats: { total_count: 10, flagged_count: 4, geotagged_count: 0, undated_count: 0, total_bytes: 0, avg_megapixels: 0 },
}

function renderPanel(seed?: Facets) {
  const qc = testQueryClient()
  if (seed) qc.setQueryData(['facets'], seed)
  qc.setQueryData(['collections'], [])
  return renderWithQuery(<LibraryPanel />, qc)
}

beforeEach(() => useUiStore.setState({ ...initial, sidebarOpen: true }))
afterEach(() => vi.unstubAllGlobals())

const aiStatus = {
  runtime_installed: true,
  model_installed: true,
  model_id: 'm',
  model_source: 's',
  model_licence: 'l',
  download_bytes: 0,
  total_photos: 10,
  analyzed_photos: 10,
  pending_photos: 0,
  active_job_id: null,
  active_job_kind: null,
}

describe('LibraryPanel: suggested by AI', () => {
  function renderWithAi(status: typeof aiStatus | null) {
    const qc = testQueryClient()
    qc.setQueryData(['facets'], facets)
    qc.setQueryData(['collections'], [])
    if (status) qc.setQueryData(['analysis', 'status'], status)
    qc.setQueryData(['analysis', 'counts'], [
      { name: 'beach', count: 4 },
      { name: 'dog', count: 2 },
    ])
    return renderWithQuery(<LibraryPanel />, qc)
  }

  it('is absent until photos are analysed', () => {
    renderWithAi({ ...aiStatus, analyzed_photos: 0 })
    expect(screen.queryByRole('region', { name: 'Suggested by AI' })).toBeNull()
  })

  it('lists suggested labels with counts and filters by one', () => {
    renderWithAi(aiStatus)
    const region = screen.getByRole('region', { name: 'Suggested by AI' })
    expect(region.textContent).toContain('beach')
    fireEvent.click(screen.getByRole('button', { name: /beach/ }))
    expect(useUiStore.getState().filterAiTag).toBe('beach')
    fireEvent.click(screen.getByRole('button', { name: /beach/ }))
    expect(useUiStore.getState().filterAiTag).toBeNull()
  })
})

describe('LibraryPanel (FR-1d)', () => {
  it('renders every section with no facets at all (AC-1d.2)', () => {
    renderPanel()
    for (const name of ['Library', 'Rating', 'Collections', 'Cameras', 'Tags']) {
      expect(screen.getByRole('region', { name })).toBeTruthy()
    }
    expect(screen.getByText('No camera data')).toBeTruthy()
  })

  it('lists cameras by count with whole-library counts', () => {
    renderPanel(facets)
    const cameras = screen.getByRole('region', { name: 'Cameras' }).querySelectorAll('.lib-row-label')
    expect([...cameras].map((c) => c.textContent)).toEqual(['Sony', 'Canon'])
    expect(screen.getByRole('button', { name: /All photos/ }).textContent).toContain('10')
  })

  it('a rating row filters by that exact rating and clicking it again clears it', () => {
    renderPanel(facets)
    fireEvent.click(screen.getByRole('button', { name: /^4 stars/ }))
    expect(useUiStore.getState().filterRating).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: /^4 stars/ }))
    expect(useUiStore.getState().filterRating).toBeNull()
  })

  it('tags toggle (AND) and Clear removes them', () => {
    renderPanel(facets)
    fireEvent.click(screen.getByRole('button', { name: /iceland/ }))
    fireEvent.click(screen.getByRole('button', { name: /night/ }))
    expect(useUiStore.getState().filterTags).toEqual(['iceland', 'night'])
    const tags = screen.getByRole('region', { name: 'Tags' })
    fireEvent.click(tags.querySelector('.link-btn') as HTMLElement)
    expect(useUiStore.getState().filterTags).toEqual([])
  })

  it('Picks filters to flagged photos', () => {
    renderPanel(facets)
    fireEvent.click(screen.getByRole('button', { name: /Picks/ }))
    expect(useUiStore.getState().filterCollection).toBe('Favorites')
  })

  it('the new-collection button needs a selection', () => {
    renderPanel(facets)
    expect((screen.getByRole('button', { name: 'New collection from the selection' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
