import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '../types/metadata'
import { renderWithQuery, testQueryClient } from '../test/render'
import { MAX_RECONNECT_FAILURES, useEventStream } from './useEventStream'
import { eventsLiveKey, jobsKey } from './useJobs'
import { photosKey } from './usePhotos'
import { facetsKey } from './useFacets'

class FakeEventSource {
  static CLOSED = 2
  static instances: FakeEventSource[] = []
  readyState = 1
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  private listeners = new Map<string, (e: Event) => void>()
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: (e: Event) => void) {
    this.listeners.set(type, fn)
  }
  close() {
    this.closed = true
  }
  emit(type: string, data?: unknown) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(data ?? {}) }))
  }
}

const job = (over: Partial<Job>): Job => ({
  id: 'j1',
  kind: 'sync',
  status: 'running',
  folder_path: 'D:\\photos',
  total: 10,
  processed: 1,
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

function Stream() {
  useEventStream()
  return null
}

function mount() {
  const qc = testQueryClient()
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  renderWithQuery(<Stream />, qc)
  return { qc, invalidate, source: FakeEventSource.instances[FakeEventSource.instances.length - 1] }
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => vi.unstubAllGlobals())

describe('useEventStream', () => {
  it('opens one stream on /api/events and marks it live once connected', () => {
    const { qc, source } = mount()
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(source.url).toBe('/api/events')
    expect(qc.getQueryData(eventsLiveKey)).toBeUndefined()
    act(() => source.onopen?.())
    expect(qc.getQueryData(eventsLiveKey)).toBe(true)
  })

  it('puts pushed job progress into the jobs list, in place', () => {
    const { qc, source } = mount()
    qc.setQueryData(jobsKey, [job({ id: 'new' }), job({ id: 'old', status: 'succeeded' })])
    act(() => source.emit('job_progress', job({ id: 'old', status: 'running', processed: 5 })))
    const jobs = qc.getQueryData<Job[]>(jobsKey) ?? []
    expect(jobs.map((j) => j.id)).toEqual(['new', 'old'])
    expect(jobs[1].processed).toBe(5)
    act(() => source.emit('job_progress', job({ id: 'fresh' })))
    expect((qc.getQueryData<Job[]>(jobsKey) ?? [])[0].id).toBe('fresh')
  })

  it('reloads photos and facets on library_changed, and the jobs too on resync', () => {
    const { invalidate, source } = mount()
    act(() => source.emit('library_changed', { reason: 'edit' }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: photosKey })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: facetsKey })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: jobsKey })
    act(() => source.emit('resync'))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobsKey })
  })

  it('falls back to polling after repeated failures and reloads when the stream is back', () => {
    const { qc, invalidate, source } = mount()
    act(() => source.onopen?.())
    for (let i = 0; i < MAX_RECONNECT_FAILURES; i++) act(() => source.onerror?.())
    expect(qc.getQueryData(eventsLiveKey)).toBe(false)
    invalidate.mockClear()
    act(() => source.onopen?.())
    expect(qc.getQueryData(eventsLiveKey)).toBe(true)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobsKey })
  })

  it('opens a new connection itself when the browser gave up on an error response', () => {
    vi.useFakeTimers()
    try {
      const { source } = mount()
      source.readyState = FakeEventSource.CLOSED
      act(() => source.onerror?.())
      expect(source.closed).toBe(true)
      act(() => {
        vi.advanceTimersByTime(3000)
      })
      expect(FakeEventSource.instances).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes the stream when the app unmounts', () => {
    const qc = testQueryClient()
    const { unmount } = renderWithQuery(<Stream />, qc)
    unmount()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })
})
