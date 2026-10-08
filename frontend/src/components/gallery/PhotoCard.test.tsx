import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { makePhoto } from '../../test/photos'
import { PhotoCard } from './PhotoCard'

const HASH = 'c'.repeat(64)
const photo = makePhoto({
  file_hash: HASH,
  file_info: { name: 'DSC04928_Tokyo_Tower_Sunset.ARW', path: '/p', size_bytes: 1000, mime_type: 'image/x-sony-arw' },
  rating: 4,
  flagged: true,
})

beforeEach(() => {
  useUiStore.setState({ inspectedHash: null, lightboxIndex: null })
  useSelectionStore.getState().clearSelection()
})

function renderCard() {
  return render(<PhotoCard photo={photo} index={7} width={300} height={200} thumbSize={320} />)
}

describe('PhotoCard tile (FR-1c.6–1c.8)', () => {
  it('names the photo by title, file, rating and pick', () => {
    renderCard()
    expect(screen.getByRole('button', { name: 'Tokyo Tower Sunset, DSC04928_Tokyo_Tower_Sunset.ARW, 4 stars, picked' })).toBeTruthy()
  })

  it('click inspects and marks the tile current', () => {
    renderCard()
    const tile = screen.getByRole('button', { name: /Tokyo Tower Sunset/ })
    fireEvent.click(tile)
    expect(useUiStore.getState().inspectedHash).toBe(HASH)
    expect(tile.getAttribute('aria-current')).toBe('true')
  })

  it('double-click opens the viewer at its index', () => {
    renderCard()
    fireEvent.doubleClick(screen.getByRole('button', { name: /Tokyo Tower Sunset/ }))
    expect(useUiStore.getState().lightboxIndex).toBe(7)
  })

  it('the checkbox and Ctrl-click toggle the selection, not the inspected photo', () => {
    renderCard()
    const checkbox = screen.getByRole('checkbox', { name: 'Select DSC04928_Tokyo_Tower_Sunset.ARW' })
    fireEvent.click(checkbox)
    expect(useSelectionStore.getState().selectedHashes.has(HASH)).toBe(true)
    expect(checkbox.getAttribute('aria-checked')).toBe('true')

    fireEvent.click(screen.getByRole('button', { name: /Tokyo Tower Sunset/ }), { ctrlKey: true })
    expect(useSelectionStore.getState().selectedHashes.has(HASH)).toBe(false)
    expect(useUiStore.getState().inspectedHash).toBeNull()
  })

  it('keeps the aspect-ratio size it is given', () => {
    const { container } = renderCard()
    const tile = container.querySelector('.tile') as HTMLElement
    expect(tile.style.width).toBe('300px')
    expect(tile.style.height).toBe('200px')
  })
})
