import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { waitFor } from '@testing-library/react'
import type { Job } from '../types/metadata'
import { useUiStore } from '../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../test/render'
import { jobsKey, useJobCompletionNotices } from './useJobs'

const job = (over: Partial<Job>): Job => ({
  id: 'j1',
  kind: 'sync',
  status: 'running',
  folder_path: 'D:\photos',
  total: 10,
  processed: 4,
  failed_count: 0,
  counts: {},
  errors: [],
  message: '',
  cancel_requested: false,
  created_at: '2026-10-24T09:00:00',
  started_at: '2026-10-24T09:00:00',
  finished_at: null,
  ...over,
})

function Notices() {
  useJobCompletionNotices()
  return null
}

describe('useJobCompletionNotices', () => {
  it('says an interrupted job was interrupted, not that it succeeded', async () => {
    const qc = testQueryClient()
    qc.setQueryData(jobsKey, [job({})])
    renderWithQuery(<Notices />, qc)
    act(() => {
      qc.setQueryData(jobsKey, [job({ status: 'interrupted', message: 'Interrupted: the app stopped.' })])
    })
    await waitFor(() => expect(useUiStore.getState().toastMessage).toMatch(/interrupted.*Resume/i))
    expect(useUiStore.getState().toastKind).toBe('error')
  })
})
