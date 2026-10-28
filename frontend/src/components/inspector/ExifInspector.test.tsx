import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { useViewStore } from '../../stores/useViewStore'
import { testQueryClient } from '../../test/render'
import { ExifInspector } from './ExifInspector'

afterEach(() => vi.unstubAllGlobals())

describe('ExifInspector', () => {
  it('says a linked photo is no longer in the library and keeps the filters', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Photo not found' }), { status: 404 })))
    useViewStore.setState({ inspectedHash: 'gone', filterRating: 4 })
    render(
      <QueryClientProvider client={testQueryClient()}>
        <ExifInspector />
      </QueryClientProvider>
    )
    expect(await screen.findByText('This photo is no longer in the library')).toBeTruthy()
    expect(useViewStore.getState().filterRating).toBe(4)
    expect(useViewStore.getState().inspectedHash).toBe('gone')
  })
})
