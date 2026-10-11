import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import type { Facets } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { toSearchRequest } from '../../utils/search'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { QueryBar } from './QueryBar'

const initial = useUiStore.getState()
const facets: Facets = {
  cameras: [
    { name: 'Canon', count: 2 },
    { name: 'Sony', count: 8 },
  ],
  tags: [{ name: 'night', count: 3 }],
  years: [{ name: '2026', count: 10 }],
  isos: [],
  gps_bounds: null,
  stats: { total_count: 10, flagged_count: 0, geotagged_count: 0, undated_count: 0, total_bytes: 0, avg_megapixels: 0 },
}

function renderBar() {
  const qc = testQueryClient()
  qc.setQueryData(['facets'], facets)
  qc.setQueryData(['collections'], [])
  renderWithQuery(<QueryBar />, qc)
  return screen.getByRole('combobox', { name: 'Filter photos' }) as HTMLInputElement
}

const request = () => {
  const s = useUiStore.getState()
  return toSearchRequest({ ...s })
}

beforeEach(() => useUiStore.setState({ ...initial }))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('QueryBar (FR-2b, AC-2b.1)', () => {
  it('make:so + the suggestion filters by Sony; Backspace removes it', () => {
    const input = renderBar()
    input.focus()
    fireEvent.change(input, { target: { value: 'make:so' } })
    const option = screen.getByRole('option', { name: /make:Sony/ })
    expect(option.textContent).toContain('8')
    fireEvent.mouseDown(option)
    expect(useUiStore.getState().filterCameras).toEqual(['Sony'])
    expect(request().camera_makes).toEqual(['Sony'])
    expect(screen.getByRole('button', { name: 'Remove make:Sony' })).toBeTruthy()

    fireEvent.keyDown(input, { key: 'Backspace' })
    expect(useUiStore.getState().filterCameras).toEqual([])
  })

  it('Enter takes the highlighted suggestion', () => {
    const input = renderBar()
    input.focus()
    fireEvent.change(input, { target: { value: 'make:can' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(useUiStore.getState().filterCameras).toEqual(['Canon'])
    expect(input.value).toBe('')
  })

  it('a space after a complete field:value commits it', () => {
    const input = renderBar()
    input.focus()
    fireEvent.change(input, { target: { value: 'rating:5' } })
    fireEvent.keyDown(input, { key: ' ' })
    expect(useUiStore.getState().filterRating).toBe(5)
  })

  it('an invalid token is shown and changes nothing in the request', () => {
    const input = renderBar()
    const before = request()
    input.focus()
    fireEvent.change(input, { target: { value: 'iso:800' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(request()).toEqual(before)
    const token = screen.getByRole('button', { name: 'Remove iso:800' }).parentElement as HTMLElement
    expect(token.className).toContain('qtok-invalid')
    expect(token.title).toMatch(/not searchable/)
  })

  it('plain words search live after 250 ms and become the search text', () => {
    vi.useFakeTimers()
    const input = renderBar()
    input.focus()
    fireEvent.change(input, { target: { value: 'kyoto' } })
    expect(useUiStore.getState().searchQuery).toBe('')
    act(() => {
      vi.advanceTimersByTime(260)
    })
    expect(useUiStore.getState().searchQuery).toBe('kyoto')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(useUiStore.getState().searchQuery).toBe('kyoto')
    expect(screen.getByRole('button', { name: 'Remove kyoto' })).toBeTruthy()
  })

  it('with an empty input it lists the fields with examples', () => {
    const input = renderBar()
    input.focus()
    fireEvent.focus(input)
    expect(screen.getByRole('option', { name: /make:.*make:sony/ })).toBeTruthy()
    expect(screen.getAllByRole('option').length).toBe(9)
  })
})

describe('QueryBar stays in sync with the store (AC-2b.2)', () => {
  it('shows filters set elsewhere as tokens', () => {
    renderBar()
    act(() => {
      useUiStore.getState().toggleTagFilter('night')
      useUiStore.getState().setRatingFilter(4)
    })
    expect(screen.getByRole('button', { name: 'Remove tag:night' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Remove rating:4' })).toBeTruthy()
  })

  it('removing a token updates the store', () => {
    useUiStore.setState({ filterTags: ['night'], filterCollection: 'Favorites' })
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'Remove pick:yes' }))
    expect(useUiStore.getState().filterCollection).toBe('all')
    expect(useUiStore.getState().filterTags).toEqual(['night'])
  })
})

describe('QueryBar: search by meaning (Phase 5)', () => {
  const status = {
    runtime_installed: true,
    model_installed: true,
    model_id: 'm',
    model_source: 's',
    model_licence: 'l',
    download_bytes: 0,
    total_photos: 4,
    analyzed_photos: 4,
    pending_photos: 0,
    active_job_id: null,
    active_job_kind: null,
  }

  function renderWith(analysis: typeof status | null) {
    const qc = testQueryClient()
    qc.setQueryData(['facets'], facets)
    qc.setQueryData(['collections'], [])
    if (analysis) qc.setQueryData(['analysis', 'status'], analysis)
    renderWithQuery(<QueryBar />, qc)
    return screen.getByRole('combobox', { name: 'Filter photos' }) as HTMLInputElement
  }

  it('runs a search by meaning and leaves the text filter alone', () => {
    const input = renderWith(status)
    input.focus()
    fireEvent.change(input, { target: { value: 'dog on a beach' } })
    fireEvent.mouseDown(screen.getByRole('option', { name: /Search by meaning/ }))
    expect(useUiStore.getState().semantic).toEqual({ kind: 'text', text: 'dog on a beach' })
    expect(useUiStore.getState().searchQuery).toBe('')
    expect(input.value).toBe('')
  })

  it('opens the setup instead when nothing is analysed yet', () => {
    const input = renderWith({ ...status, model_installed: false, analyzed_photos: 0 })
    input.focus()
    fireEvent.change(input, { target: { value: 'sunset' } })
    fireEvent.mouseDown(screen.getByRole('option', { name: /Search by meaning/ }))
    expect(useUiStore.getState().aiDialogOpen).toBe(true)
    expect(useUiStore.getState().semantic).toBeNull()
  })

  it('is not offered when the backend has no AI runtime', () => {
    const input = renderWith({ ...status, runtime_installed: false })
    input.focus()
    fireEvent.change(input, { target: { value: 'sunset' } })
    expect(screen.queryByRole('option', { name: /Search by meaning/ })).toBeNull()
  })
})
