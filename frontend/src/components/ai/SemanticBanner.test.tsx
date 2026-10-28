import { describe, expect, it } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { useViewStore } from '../../stores/useViewStore'
import { renderWithQuery } from '../../test/render'
import { SemanticBanner } from './SemanticBanner'

describe('SemanticBanner (ADR-003 R9)', () => {
  it('says what the Library is ranked by, switches to everything and clears', () => {
    useViewStore.setState({ semantic: { kind: 'text', text: 'beach' } })
    renderWithQuery(<SemanticBanner />)
    expect(screen.getByRole('status').textContent).toContain('Meaning: “beach”')

    fireEvent.click(screen.getByRole('button', { name: 'Show everything' }))
    expect(useViewStore.getState().semantic).toEqual({ kind: 'text', text: 'beach', everything: true })

    fireEvent.click(screen.getByRole('button', { name: /clear/i }))
    expect(useViewStore.getState().semantic).toBeNull()
  })

  it('shows nothing without a search by meaning', () => {
    const { container } = renderWithQuery(<SemanticBanner />)
    expect(container.textContent).toBe('')
  })
})
