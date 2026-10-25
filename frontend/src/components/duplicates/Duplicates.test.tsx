import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Duplicates } from '../../types/metadata'
import { duplicatesKey } from '../../hooks/useDuplicates'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { FilesSection } from '../inspector/FilesSection'
import { DuplicatesDialog } from './DuplicatesDialog'

const file = (path: string, over: Partial<Duplicates['groups'][number]['files'][number]> = {}) => ({
  path,
  name: path.split('/').pop() ?? path,
  size_bytes: 2_000_000,
  missing: false,
  hidden: false,
  ...over,
})

const data: Duplicates = {
  total_groups: 2,
  total_listed: 2,
  reclaimable_bytes: 6_000_000,
  groups: [
    {
      file_hash: 'a'.repeat(64),
      size_bytes: 2_000_000,
      reclaimable_bytes: 4_000_000,
      copies: 3,
      files: [file('/p/a.jpg'), file('/q/a.jpg'), file('/r/a.jpg', { hidden: true })],
    },
    {
      file_hash: 'b'.repeat(64),
      size_bytes: 1_000_000,
      reclaimable_bytes: 1_000_000,
      copies: 2,
      files: [file('/p/b.jpg'), file('/q/b.jpg', { missing: true })],
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
  useUiStore.setState({ duplicatesDialogOpen: false })
})

function open() {
  useUiStore.setState({ duplicatesDialogOpen: true })
  const qc = testQueryClient()
  qc.setQueryData([...duplicatesKey, 25], data)
  renderWithQuery(<DuplicatesDialog />, qc)
  return qc
}

describe('DuplicatesDialog', () => {
  it('says how many photos are duplicated, the space the extra copies take, and that nothing is deleted', () => {
    open()
    expect(screen.getByText(/2 photos are kept in more than one place/)).toBeTruthy()
    expect(screen.getByText(/Nothing here deletes a file/)).toBeTruthy()
    expect(screen.getByText(/3 copies/)).toBeTruthy()
  })

  it('lists every path of a group and marks hidden and missing ones', () => {
    open()
    expect(screen.getAllByText('/p/a.jpg').length).toBe(1)
    expect(screen.getByText('hidden')).toBeTruthy()
    expect(screen.getByText('missing')).toBeTruthy()
  })

  it('hides a copy through the API, and offers Show again for a hidden one', async () => {
    open()
    const spy = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', spy)
    fireEvent.click(screen.getByRole('button', { name: 'Hide this copy: /q/a.jpg' }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/files/hide')
    expect(JSON.parse(init.body as string)).toEqual({ path: '/q/a.jpg', hidden: true })
    expect(screen.getByRole('button', { name: 'Show again: /r/a.jpg' })).toBeTruthy()
  })

  it('offers no action on a missing file', () => {
    open()
    expect(screen.queryByRole('button', { name: /\/q\/b\.jpg/ })).toBeNull()
  })

  it('closes on Escape', () => {
    open()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(useUiStore.getState().duplicatesDialogOpen).toBe(false)
  })
})

describe('FilesSection', () => {
  it('lists every file, primary first, and says the photo is stored in several places', () => {
    render(<FilesSection paths={[file('/p/a.jpg'), file('/q/a.jpg', { missing: true })]} />)
    expect(screen.getByText('Stored in 2 places')).toBeTruthy()
    const items = screen.getAllByRole('listitem')
    expect(items[0].textContent).toContain('/p/a.jpg')
    expect(items[0].textContent).toContain('shown')
    expect(items[1].textContent).toContain('missing')
  })

  it('a photo with one file is just File', () => {
    render(<FilesSection paths={[file('/p/a.jpg')]} />)
    expect(screen.getByText('File')).toBeTruthy()
  })
})
