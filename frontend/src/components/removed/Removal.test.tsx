import { afterEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { RemovedFile } from '../../types/metadata'
import { removedKey } from '../../hooks/useRemoval'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { ConfirmDialog } from '../common/ConfirmDialog'
import { SelectionDock } from '../collections/SelectionDock'
import { RemovedDialog } from './RemovedDialog'

function serve(routes: Record<string, unknown>) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${url}`
      calls.push(init?.body ? `${key} ${init.body}` : key)
      const body = routes[key]
      if (body === undefined) return new Response('[]', { status: 200 })
      return new Response(JSON.stringify(body), { status: 200 })
    })
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  useSelectionStore.getState().clearSelection()
  useUiStore.setState({ removedDialogOpen: false, toastMessage: null, toastAction: null })
})

describe('toast action', () => {
  it('a toast can carry a button, and showing another toast replaces it', () => {
    const run = vi.fn()
    act(() => useUiStore.getState().showToast('Removed', 'success', { label: 'Undo', run }))
    expect(useUiStore.getState().toastAction?.label).toBe('Undo')
    act(() => useUiStore.getState().showToast('Saved'))
    expect(useUiStore.getState().toastAction).toBeNull()
  })
})

describe('ConfirmDialog', () => {
  it('asks first: nothing happens until confirmed, and Escape cancels', () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(<ConfirmDialog title="Remove 2 photos?" message="Files stay on disk." confirmLabel="Remove 2 photos" onConfirm={onConfirm} onClose={onClose} />)
    expect(screen.getByRole('dialog', { name: 'Remove 2 photos?' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove 2 photos' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})

describe('removing the selection', () => {
  it('confirms with the count, removes through the API, and offers Undo that restores', async () => {
    renderWithQuery(<SelectionDock />, testQueryClient())
    act(() => {
      useSelectionStore.getState().toggleSelect('h1', 10)
      useSelectionStore.getState().toggleSelect('h2', 20)
    })
    const calls = serve({
      'POST /api/photos/batch': { updated_count: 0, deleted_count: 2, undo_seconds: 30, action: 'delete', message: 'x' },
      'POST /api/photos/restore': { restored_count: 2 },
    })
    fireEvent.click(screen.getByRole('button', { name: /Remove/ }))
    expect(screen.getByRole('dialog').textContent).toContain('Remove 2 photos from the library?')
    expect(calls).toEqual([]) // nothing yet: it asked first
    fireEvent.click(screen.getByRole('button', { name: 'Remove 2 photos' }))
    await waitFor(() => expect(calls[0]).toMatch(/^POST \/api\/photos\/batch .*"action":"delete"/))
    await waitFor(() => expect(useUiStore.getState().toastAction?.label).toBe('Undo'))
    expect(useUiStore.getState().toastMessage).toMatch(/Removed 2 photos from the library/)
    expect(useSelectionStore.getState().selectedHashes.size).toBe(0)

    act(() => useUiStore.getState().toastAction?.run())
    await waitFor(() => expect(calls.some((c) => c.startsWith('POST /api/photos/restore'))).toBe(true))
    await waitFor(() => expect(useUiStore.getState().toastMessage).toBe('Restored 2 photos'))
  })

  it('cancelling the confirmation removes nothing', () => {
    renderWithQuery(<SelectionDock />, testQueryClient())
    act(() => useSelectionStore.getState().toggleSelect('h1', 10))
    const calls = serve({})
    fireEvent.click(screen.getByRole('button', { name: /Remove/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(calls).toEqual([])
    expect(useSelectionStore.getState().selectedHashes.size).toBe(1)
  })
})

describe('RemovedDialog', () => {
  const files: RemovedFile[] = [
    { path: 'D:\\photos\\a.jpg', name: 'a.jpg', size_bytes: 2_000_000, removed_at: '2026-10-25T09:00:00' },
  ]

  function open(list: RemovedFile[]) {
    useUiStore.setState({ removedDialogOpen: true })
    const qc = testQueryClient()
    qc.setQueryData(removedKey, list)
    renderWithQuery(<RemovedDialog />, qc)
  }

  it('lists the files and says nothing on disk is deleted', () => {
    open(files)
    expect(screen.getByText('D:\\photos\\a.jpg')).toBeTruthy()
    expect(screen.getByText(/still on\s+your disk/)).toBeTruthy()
  })

  it('Restore asks the server to forget the file and scan its folder', async () => {
    open(files)
    const calls = serve({ 'POST /api/removed/restore': { restored_count: 1, job_ids: ['j1'] } })
    fireEvent.click(screen.getByRole('button', { name: 'Restore D:\\photos\\a.jpg' }))
    await waitFor(() => expect(calls[0]).toBe('POST /api/removed/restore {"paths":["D:\\\\photos\\\\a.jpg"]}'))
  })

  it('says so when nothing has been removed, and Escape closes it', () => {
    open([])
    expect(screen.getByText('Nothing has been removed.')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(useUiStore.getState().removedDialogOpen).toBe(false)
  })
})
