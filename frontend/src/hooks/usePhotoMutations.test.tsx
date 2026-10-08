import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PaginatedPhotosResponse, PhotoMetadata } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { makePhoto } from '../test/photos'
import { useCuration } from './usePhotoMutations'

const HASH = 'f'.repeat(64)
const searchKey = ['photos', 'search', { sort_by: 'captured_at' }]

function setup(photo: PhotoMetadata) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const page: PaginatedPhotosResponse = { items: [photo], total_count: 1, page: 1, page_size: 200, total_pages: 1 }
  qc.setQueryData(searchKey, page)
  qc.setQueryData(['photos', 'detail', HASH], photo)
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useCuration(), { wrapper })
  const cached = () => ({
    inPage: qc.getQueryData<PaginatedPhotosResponse>(searchKey)!.items[0],
    single: qc.getQueryData<PhotoMetadata>(['photos', 'detail', HASH])!,
  })
  return { result, cached }
}

function deferredFetch() {
  let resolve!: (r: Response) => void
  const fetchMock = vi.fn(() => new Promise<Response>((r) => (resolve = r)))
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, respond: (body: unknown, status = 200) => resolve(new Response(JSON.stringify(body), { status })) }
}

beforeEach(() => useUiStore.setState({ toastMessage: null, toastKind: 'success' }))
afterEach(() => useUiStore.getState().hideToast())

describe('useCuration (PMO-13/15)', () => {
  it('updates every cached copy at once, then keeps the server record', async () => {
    const { respond } = deferredFetch()
    const { result, cached } = setup(makePhoto({ file_hash: HASH, rating: null }))

    let saved: Promise<boolean>
    act(() => {
      saved = result.current.patchPhoto(HASH, { rating: 4 }, 'Rated 4 stars')
    })
    await waitFor(() => expect(cached().inPage.rating).toBe(4))
    expect(cached().single.rating).toBe(4)

    // The server's answer wins (here it also normalised the labels).
    respond(makePhoto({ file_hash: HASH, rating: 4, labels: ['from-server'] }))
    await act(async () => {
      expect(await saved).toBe(true)
    })
    expect(cached().inPage.labels).toEqual(['from-server'])
    expect(useUiStore.getState().toastMessage).toBe('Rated 4 stars')
    expect(useUiStore.getState().toastKind).toBe('success')
  })

  it("rolls back a failed save and shows the server's reason, never the success message", async () => {
    const { respond } = deferredFetch()
    const { result, cached } = setup(makePhoto({ file_hash: HASH, rating: 2, flagged: false }))

    let saved: Promise<boolean>
    act(() => {
      saved = result.current.patchPhoto(HASH, { rating: 5, flagged: true }, 'Saved')
    })
    await waitFor(() => expect(cached().inPage.rating).toBe(5))

    respond({ detail: 'Rating must be between 1 and 5' }, 422)
    await act(async () => {
      expect(await saved).toBe(false)
    })
    expect(cached().inPage.rating).toBe(2)
    expect(cached().inPage.flagged).toBe(false)
    expect(cached().single.rating).toBe(2)
    expect(useUiStore.getState().toastKind).toBe('error')
    expect(useUiStore.getState().toastMessage).toBe('Not saved: Rating must be between 1 and 5')
  })

  it('reports an unreachable backend as an error toast', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const { result, cached } = setup(makePhoto({ file_hash: HASH, flagged: false }))

    await act(async () => {
      expect(await result.current.patchPhoto(HASH, { flagged: true })).toBe(false)
    })
    expect(cached().inPage.flagged).toBe(false)
    expect(useUiStore.getState().toastMessage).toMatch(/^Not saved: Cannot reach the backend/)
  })

  it('batch rating updates every selected photo at once and rolls back all of them on failure (FR-1f.2)', async () => {
    const { respond } = deferredFetch()
    const other = 'e'.repeat(64)
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const page: PaginatedPhotosResponse = {
      items: [makePhoto({ file_hash: HASH, rating: 1 }), makePhoto({ file_hash: other, rating: null })],
      total_count: 2,
      page: 1,
      page_size: 200,
      total_pages: 1,
    }
    qc.setQueryData(searchKey, page)
    const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useCuration(), { wrapper })
    const ratings = () => qc.getQueryData<PaginatedPhotosResponse>(searchKey)!.items.map((p) => p.rating)

    let saved: Promise<boolean>
    act(() => {
      saved = result.current.batchPhotos({ photo_hashes: [HASH, other], action: 'set_rating', value: 4 }, 'Rated')
    })
    await waitFor(() => expect(ratings()).toEqual([4, 4]))

    respond({ detail: 'database is locked' }, 500)
    await act(async () => {
      expect(await saved).toBe(false)
    })
    expect(ratings()).toEqual([1, null])
    expect(useUiStore.getState().toastKind).toBe('error')
  })
})
