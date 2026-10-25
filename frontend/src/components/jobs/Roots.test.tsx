import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { Job, Root, RootSuggestions } from '../../types/metadata'
import { jobsKey } from '../../hooks/useJobs'
import { rootsKey, rootSuggestionsKey, useRecheckRootsOnFocus } from '../../hooks/useRoots'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { FirstRunState } from '../states/FirstRunState'
import { FoldersDialog } from './FoldersDialog'
import { RootSuggestionsDialog } from './RootSuggestionsDialog'

const root = (over: Partial<Root> = {}): Root => ({
  path: 'D:\\photos',
  added_at: '2026-10-25T09:00:00',
  online: true,
  job_id: null,
  ...over,
})

const job = (over: Partial<Job> = {}): Job => ({
  id: 'j1',
  kind: 'sync',
  status: 'running',
  folder_path: 'D:\\photos',
  total: 20,
  processed: 5,
  failed_count: 0,
  counts: {},
  errors: [],
  message: '',
  cancel_requested: false,
  created_at: '2026-10-25T09:00:00',
  started_at: '2026-10-25T09:00:01',
  finished_at: null,
  ...over,
})

/** Answer fetches by "METHOD /path"; every call is recorded. */
function serve(routes: Record<string, unknown>) {
  const calls: string[] = []
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`
    calls.push(init?.body ? `${key} ${init.body}` : key)
    const body = routes[key]
    if (body === undefined) return new Response('{}', { status: 404 })
    return body === null ? new Response(null, { status: 204 }) : new Response(JSON.stringify(body), { status: 200 })
  })
  vi.stubGlobal('fetch', spy)
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  useUiStore.setState({ foldersDialogOpen: false, aiDialogOpen: false })
})

describe('FirstRunState', () => {
  it('asks for a folder and adds it as a root, which starts the scan', async () => {
    const qc = testQueryClient()
    renderWithQuery(<FirstRunState />, qc)
    const calls = serve({
      'POST /api/roots': root({ job_id: 'j1' }),
      'GET /api/jobs/j1': job(),
      'GET /api/roots': [root()],
    })
    fireEvent.change(screen.getByLabelText('Photo folder'), { target: { value: 'D:\\photos' } })
    fireEvent.click(screen.getByRole('button', { name: 'Scan this folder' }))
    await waitFor(() => expect(qc.getQueryData<Job[]>(jobsKey)?.[0]?.id).toBe('j1'))
    expect(calls[0]).toBe('POST /api/roots {"folder_path":"D:\\\\photos","scan":true}')
  })

  it('shows the scan live and offers the optional AI setup', () => {
    const qc = testQueryClient()
    qc.setQueryData(jobsKey, [job()])
    renderWithQuery(<FirstRunState />, qc)
    expect(screen.getByText(/5 of 20 photos/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Set up search by meaning/ }))
    expect(useUiStore.getState().aiDialogOpen).toBe(true)
  })
})

describe('RootSuggestionsDialog', () => {
  const suggestions: RootSuggestions = {
    suggestions: [
      { path: 'D:\\photos', file_count: 120, online: true },
      { path: 'E:\\old', file_count: 1, online: false },
    ],
    dismissed: false,
  }

  it('offers the folders as a checkbox list and watches only the ticked ones', async () => {
    const qc = testQueryClient()
    qc.setQueryData(rootSuggestionsKey, suggestions)
    renderWithQuery(<RootSuggestionsDialog />, qc)
    const calls = serve({ 'POST /api/roots': root(), 'GET /api/roots': [root()] })
    expect(screen.getByLabelText(/D:\\photos \(120 photos\)/)).toHaveProperty('checked', true)
    expect(screen.getByLabelText(/E:\\old \(1 photo, offline\)/)).toHaveProperty('checked', false)
    fireEvent.click(screen.getByRole('button', { name: 'Watch 1 folder' }))
    await waitFor(() => expect(calls.some((c) => c.startsWith('POST /api/roots'))).toBe(true))
    expect(calls.filter((c) => c.startsWith('POST /api/roots'))).toHaveLength(1)
  })

  it('"Not now" skips the offer for good and watches nothing', async () => {
    const qc = testQueryClient()
    qc.setQueryData(rootSuggestionsKey, suggestions)
    renderWithQuery(<RootSuggestionsDialog />, qc)
    const calls = serve({ 'POST /api/roots/suggestions/dismiss': null })
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }))
    await waitFor(() => expect(calls).toContain('POST /api/roots/suggestions/dismiss'))
    expect(calls.some((c) => c.startsWith('POST /api/roots '))).toBe(false)
  })

  it('shows nothing when there is nothing to offer', () => {
    const qc = testQueryClient()
    qc.setQueryData(rootSuggestionsKey, { suggestions: [], dismissed: false })
    renderWithQuery(<RootSuggestionsDialog />, qc)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('FoldersDialog', () => {
  it('lists the roots, marks an offline one, and stops watching on request', async () => {
    useUiStore.setState({ foldersDialogOpen: true })
    const qc = testQueryClient()
    qc.setQueryData(rootsKey, [root(), root({ path: 'E:\\usb', online: false })])
    renderWithQuery(<FoldersDialog />, qc)
    const calls = serve({ 'DELETE /api/roots?path=E%3A%5Cusb': null, 'GET /api/roots': [root()] })
    expect(screen.getByText(/offline/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Stop watching E:\\usb' }))
    await waitFor(() => expect(calls).toContain('DELETE /api/roots?path=E%3A%5Cusb'))
  })
})

describe('useRecheckRootsOnFocus', () => {
  function Mount() {
    useRecheckRootsOnFocus()
    return null
  }

  it('asks the server to look at the roots when the window regains focus, at most every few seconds', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    try {
      const qc = testQueryClient()
      renderWithQuery(<Mount />, qc)
      const calls = serve({ 'POST /api/roots/recheck': null, 'GET /api/roots': [] })
      fireEvent.focus(window)
      fireEvent.focus(window)
      await waitFor(() => expect(calls).toContain('POST /api/roots/recheck'))
      expect(calls.filter((c) => c === 'POST /api/roots/recheck')).toHaveLength(1)
      vi.setSystemTime(Date.now() + 11_000)
      fireEvent.focus(window)
      await waitFor(() => expect(calls.filter((c) => c === 'POST /api/roots/recheck')).toHaveLength(2))
    } finally {
      vi.useRealTimers()
    }
  })
})
