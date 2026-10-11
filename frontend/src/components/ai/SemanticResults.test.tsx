import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { SEMANTIC_MAX, SEMANTIC_PAGE, useUiStore } from '../../stores/useUiStore'
import { makePhoto } from '../../test/photos'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { SemanticResults } from './SemanticResults'

const initial = useUiStore.getState()

function hits(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    photo: makePhoto({ file_hash: String(i).padStart(64, '0') }),
    score: 0.9 - i * 0.01,
  }))
}

/** Seed the cache under the key the component will ask for (no filters, the store's limit). */
function render(n: number, limit = SEMANTIC_PAGE) {
  useUiStore.setState({ semantic: { kind: 'text', text: 'beach' }, semanticLimit: limit })
  const qc = testQueryClient()
  qc.setQueryData(
    ['analysis', 'semantic', { sort_by: 'captured_at', sort_order: 'desc', text: 'beach', k: limit }],
    { items: hits(n), model_id: 'm' }
  )
  return renderWithQuery(<SemanticResults />, qc)
}

beforeEach(() => useUiStore.setState({ ...initial }))
afterEach(() => vi.unstubAllGlobals())

describe('SemanticResults', () => {
  it('lists the matches best first with their score', () => {
    render(3)
    expect(screen.getByRole('status').textContent).toContain('3 matches')
    const tiles = screen.getAllByRole('button', { name: /match$/ })
    expect(tiles[0].getAttribute('aria-label')).toContain('90% match')
  })

  it('opens the viewer on the double-clicked match', () => {
    render(3)
    fireEvent.doubleClick(screen.getAllByRole('button', { name: /match$/ })[2])
    expect(useUiStore.getState().lightboxIndex).toBe(2)
  })

  it('offers Show more only when a full page came back', () => {
    const { unmount } = render(5)
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
    unmount()
    render(SEMANTIC_PAGE)
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(useUiStore.getState().semanticLimit).toBe(SEMANTIC_PAGE * 2)
  })

  it('stops offering more at the API cap', () => {
    render(SEMANTIC_MAX, SEMANTIC_MAX)
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('Clear returns to the library and a new query starts from one page again', () => {
    render(SEMANTIC_PAGE)
    useUiStore.getState().showMoreSemantic()
    useUiStore.getState().setSemantic({ kind: 'text', text: 'dog' })
    expect(useUiStore.getState().semanticLimit).toBe(SEMANTIC_PAGE)
    useUiStore.getState().setSemantic(null)
    expect(useUiStore.getState().semantic).toBeNull()
  })
})
