import { afterEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useViewStore } from '../stores/useViewStore'
import { makePhoto } from '../test/photos'
import { testQueryClient } from '../test/render'
import { usePhotoSearch } from './usePhotos'

afterEach(() => vi.unstubAllGlobals())

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const page = (n: number, token: string) => ({
  items: [makePhoto({ file_hash: `p${n}-${token}` })],
  total_count: 2,
  page: n,
  page_size: 200,
  total_pages: 2,
  scores: [0.5],
  rank_token: token,
})

describe('usePhotoSearch with a search by meaning (ADR-003 R9)', () => {
  it('sends page 1 token with later pages and reruns from page 1 when it has expired', async () => {
    const bodies: Record<string, unknown>[] = []
    let firstPages = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body))
        bodies.push(body)
        if (body.page === 1) return json(page(1, `t${++firstPages}`))
        return json({ detail: 'This search has expired.' }, 410)
      })
    )
    useViewStore.setState({ semantic: { kind: 'text', text: 'beach' } })
    const qc = testQueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result } = renderHook(() => usePhotoSearch(), { wrapper })
    await waitFor(() => expect(result.current.photos).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ rank: { text: 'beach', everything: false } })
    expect(bodies[0].rank_token).toBeUndefined()

    await act(async () => {
      await result.current.fetchNextPage()
    })
    expect(bodies[1]).toMatchObject({ page: 2, rank_token: 't1' })
    await waitFor(() => expect(firstPages).toBe(2))
  })

  it('a refetch pages with the token of the new page 1, not the old one', async () => {
    const bodies: Record<string, unknown>[] = []
    let firstPages = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body))
        bodies.push(body)
        return json(body.page === 1 ? page(1, `t${++firstPages}`) : page(2, String(body.rank_token)))
      })
    )
    useViewStore.setState({ semantic: { kind: 'text', text: 'beach' } })
    const qc = testQueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result } = renderHook(() => usePhotoSearch(), { wrapper })
    await waitFor(() => expect(result.current.photos).toHaveLength(1))
    await act(async () => {
      await result.current.fetchNextPage()
    })
    await act(async () => {
      await result.current.refetch()
    })
    const later = bodies.filter((b) => b.page === 2).map((b) => b.rank_token)
    expect(later).toEqual(['t1', 't2'])
  })
})
