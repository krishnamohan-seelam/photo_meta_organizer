import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { Job } from '../../types/metadata'
import { jobsKey } from '../../hooks/useJobs'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { JobStatusPill } from './JobStatusPill'

const job = (over: Partial<Job>): Job => ({
  id: 'j1',
  kind: 'sync',
  status: 'succeeded',
  folder_path: 'D:\\photos',
  total: 10,
  processed: 10,
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

function show(jobs: Job[]) {
  const qc = testQueryClient()
  qc.setQueryData(jobsKey, jobs)
  renderWithQuery(<JobStatusPill />, qc)
  return qc
}

function answer(body: Job) {
  const spy = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
  vi.stubGlobal('fetch', spy)
  return spy
}

afterEach(() => vi.unstubAllGlobals())

describe('JobStatusPill', () => {
  it('says the library is up to date when nothing runs or waits', () => {
    show([job({})])
    expect(screen.getByText('Library up to date')).toBeTruthy()
  })

  it('offers Resume and Dismiss for an interrupted job, and never resumes on its own', () => {
    show([job({ status: 'interrupted', message: 'Interrupted: the app stopped while this job was running.' })])
    expect(screen.getByText(/Interrupted/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Resume' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeTruthy()
  })

  it('Resume asks the server to run the job again', async () => {
    show([job({ status: 'interrupted' })])
    const spy = answer(job({ status: 'queued', total: null, processed: 0 }))
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(String((spy.mock.calls[0] as unknown[])[0])).toContain('/jobs/j1/resume')
    expect(await screen.findByText(/Syncing/)).toBeTruthy()
  })

  it('Dismiss gives the job up and the pill goes idle', async () => {
    show([job({ status: 'interrupted' })])
    const spy = answer(job({ status: 'cancelled' }))
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(String((spy.mock.calls[0] as unknown[])[0])).toContain('/jobs/j1/dismiss')
    expect(await screen.findByText('Library up to date')).toBeTruthy()
  })

  it('a running job takes precedence over an interrupted one', () => {
    show([job({ id: 'j2', status: 'running', processed: 3 }), job({ status: 'interrupted' })])
    expect(screen.getByText(/Syncing 3/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull()
  })
})
