import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { EmptyLibraryState, ErrorState, LoadingState, StaleBanner } from './LibraryStates'

describe('library states (PMO-14)', () => {
  it('loading is announced politely', () => {
    render(<LoadingState />)
    expect(screen.getByRole('status').textContent).toMatch(/Loading your library/)
  })

  it("the error state shows the server's message and Retry calls back", () => {
    const onRetry = vi.fn()
    render(<ErrorState message="database is locked" onRetry={onRetry} retrying={false} />)
    expect(screen.getByRole('alert').textContent).toContain('database is locked')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('Retry is disabled while retrying', () => {
    render(<ErrorState message="x" onRetry={() => {}} retrying />)
    expect(screen.getByRole('button', { name: /Retrying/ })).toHaveProperty('disabled', true)
  })

  it('the empty library offers a scan', () => {
    const onScan = vi.fn()
    render(<EmptyLibraryState onScan={onScan} scanning={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'Scan folder' }))
    expect(onScan).toHaveBeenCalledOnce()
  })

  it('a failed refresh with cached photos is a banner, not an error page', () => {
    render(<StaleBanner message="Cannot reach the backend. Is it running?" onRetry={() => {}} retrying={false} />)
    expect(screen.getByRole('alert').textContent).toContain('Cannot reach the backend')
  })
})
