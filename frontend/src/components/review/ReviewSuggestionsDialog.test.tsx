import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { ReviewItems, ReviewLabel } from '../../types/metadata'
import { analysisKey } from '../../hooks/useAnalysis'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { ReviewSuggestionsDialog } from './ReviewSuggestionsDialog'

const labels: ReviewLabel[] = [
  { label: 'tiger', count: 2, top_confidence: 0.9 },
  { label: 'zoo', count: 5, top_confidence: 0.4 },
]

const tigerItems: ReviewItems = {
  label: 'tiger',
  total: 2,
  items: [
    { file_hash: 'h1', name: 'one.jpg', confidence: 0.9 },
    { file_hash: 'h2', name: 'two.jpg', confidence: 0.6 },
  ],
}

function open() {
  useUiStore.setState({ reviewDialogOpen: true })
  const qc = testQueryClient()
  qc.setQueryData([...analysisKey, 'review', 'labels'], labels)
  qc.setQueryData([...analysisKey, 'review', 'items', 'tiger'], tigerItems)
  qc.setQueryData([...analysisKey, 'review', 'count', 'tiger', 0.3], { count: 2 })
  renderWithQuery(<ReviewSuggestionsDialog />, qc)
  return qc
}

/** The server after photo h1 was decided; every request is recorded as "METHOD url body". */
function record() {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}${init?.body ? ` ${init.body}` : ''}`)
      let body: unknown = []
      if (url.includes('/ai-tags/review/items')) body = { ...tigerItems, total: 1, items: tigerItems.items.slice(1) }
      else if (url.includes('/ai-tags/review/count')) body = { count: 1 }
      else if (url.endsWith('/ai-tags/review')) body = labels
      return new Response(JSON.stringify(body), { status: 200 })
    })
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  useUiStore.setState({ reviewDialogOpen: false })
})

describe('ReviewSuggestionsDialog', () => {
  it('starts on the label with the most confident suggestion and shows its best photo first', () => {
    open()
    expect(screen.getByRole('button', { name: /tiger/ }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('img', { name: 'one.jpg' })).toBeTruthy()
    expect(screen.getByText(/90% sure/)).toBeTruthy()
    expect(screen.getByText('1 of 2')).toBeTruthy()
  })

  it('A accepts the photo shown and moves to the next', async () => {
    open()
    const calls = record()
    fireEvent.keyDown(window, { key: 'a' })
    await waitFor(() => expect(calls[0]).toBe('POST /api/photos/h1/ai-tags {"label":"tiger","action":"accept"}'))
    expect(screen.getByRole('img', { name: 'two.jpg' })).toBeTruthy()
    expect(screen.getByText('1 of 1')).toBeTruthy()
  })

  it('R rejects it', async () => {
    open()
    const calls = record()
    fireEvent.keyDown(window, { key: 'r' })
    await waitFor(() => expect(calls[0]).toBe('POST /api/photos/h1/ai-tags {"label":"tiger","action":"reject"}'))
  })

  it('J and K move without deciding anything', () => {
    open()
    const calls = record()
    fireEvent.keyDown(window, { key: 'j' })
    expect(screen.getByRole('img', { name: 'two.jpg' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'k' })
    expect(screen.getByRole('img', { name: 'one.jpg' })).toBeTruthy()
    expect(calls).toEqual([])
  })

  it('ignores the keys while a number is being typed', () => {
    open()
    const calls = record()
    const input = screen.getByLabelText(/at or above/)
    fireEvent.keyDown(input, { key: 'a' })
    expect(calls).toEqual([])
  })

  it('shows how many photos "accept all" would reach and asks again before applying', async () => {
    open()
    const calls = record()
    fireEvent.click(screen.getByRole('button', { name: /Accept all \(2 photos\)/ }))
    expect(screen.getByRole('alert').textContent).toContain('Add “tiger” to 2 photos?')
    expect(calls).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Accept 2' }))
    await waitFor(() => expect(calls[0]).toBe('POST /api/ai-tags/accept-above {"label":"tiger","min_confidence":0.3}'))
  })

  it('cancelling the confirmation applies nothing', () => {
    open()
    const calls = record()
    fireEvent.click(screen.getByRole('button', { name: /Accept all/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(calls).toEqual([])
    expect(screen.getByRole('button', { name: /Accept all/ })).toBeTruthy()
  })

  it('says so when there is nothing to review', () => {
    useUiStore.setState({ reviewDialogOpen: true })
    const qc = testQueryClient()
    qc.setQueryData([...analysisKey, 'review', 'labels'], [])
    renderWithQuery(<ReviewSuggestionsDialog />, qc)
    expect(screen.getByText(/Nothing to review/)).toBeTruthy()
  })

  it('Escape closes it', () => {
    open()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(useUiStore.getState().reviewDialogOpen).toBe(false)
  })
})
