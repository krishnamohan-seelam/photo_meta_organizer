import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Job } from '../types/metadata'
import { isDemoMode, photosKey } from './usePhotos'
import { duplicatesKey } from './useDuplicates'
import { facetsKey } from './useFacets'
import { eventsLiveKey, jobsKey, upsertJob } from './useJobs'

/** After this many failed (re)connections in a row the stream counts as down and polling takes over. */
export const MAX_RECONNECT_FAILURES = 3
const RECONNECT_MS = 3000

/**
 * Mount once (App): one `EventSource` on `GET /api/events` (ADR-003 R5b). Job events update the
 * jobs list; `library_changed` and `resync` reload photos and facets. The browser reconnects
 * with `Last-Event-ID` by itself; the server replays what was missed or sends `resync`. If
 * reconnecting keeps failing the stream is marked down and job polling takes over until it is back.
 */
export function useEventStream() {
  const qc = useQueryClient()

  useEffect(() => {
    if (isDemoMode() || typeof EventSource === 'undefined') return
    let source: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0

    const setLive = (live: boolean) => qc.setQueryData(eventsLiveKey, live)
    const reloadLibrary = () => {
      void qc.invalidateQueries({ queryKey: photosKey })
      void qc.invalidateQueries({ queryKey: facetsKey })
      void qc.invalidateQueries({ queryKey: duplicatesKey })
    }
    const reloadAll = () => {
      reloadLibrary()
      void qc.invalidateQueries({ queryKey: jobsKey })
    }
    const onJob = (e: Event) => {
      const job = JSON.parse((e as MessageEvent<string>).data) as Job
      qc.setQueryData<Job[]>(jobsKey, (jobs) => upsertJob(jobs, job))
    }

    const connect = () => {
      const es = new EventSource('/api/events')
      source = es
      es.onopen = () => {
        // Anything could have happened while polling stood in, so reload once on the way back.
        if (failures >= MAX_RECONNECT_FAILURES) reloadAll()
        failures = 0
        setLive(true)
      }
      es.onerror = () => {
        failures += 1
        if (failures >= MAX_RECONNECT_FAILURES) setLive(false)
        // The browser retries a dropped connection itself, but gives up on an error response.
        if (es.readyState === EventSource.CLOSED) {
          es.close()
          timer = setTimeout(connect, RECONNECT_MS)
        }
      }
      es.addEventListener('job_progress', onJob)
      es.addEventListener('job_finished', onJob)
      es.addEventListener('library_changed', reloadLibrary)
      es.addEventListener('resync', reloadAll)
    }

    connect()
    return () => {
      clearTimeout(timer)
      source?.close()
      setLive(false)
    }
  }, [qc])
}
