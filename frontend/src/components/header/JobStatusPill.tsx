import React from 'react'
import { X } from 'lucide-react'
import type { Job } from '../../types/metadata'
import { useJobActions, useJobs } from '../../hooks/useJobs'
import { useUiStore } from '../../stores/useUiStore'

function jobLabel(job: Job): string {
  const verb = job.kind === 'sync' ? 'Syncing' : 'Indexing'
  if (job.cancel_requested) return 'Cancelling…'
  if (job.total === null) return `${verb}: finding files…`
  return `${verb} ${job.processed.toLocaleString()} / ${job.total.toLocaleString()}`
}

/**
 * Job status in the top bar (FR-1b.6). Idle: "Library up to date". Running: what, how far,
 * failures so far and Cancel; clicking it shows the job's folder and counts.
 */
export const JobStatusPill: React.FC = () => {
  const { activeJob } = useJobs()
  const { cancelJob } = useJobActions()
  const showToast = useUiStore((s) => s.showToast)

  if (!activeJob) {
    return (
      <div className="job-pill" role="status">
        <span className="job-pill-dot" aria-hidden="true" />
        <span className="job-pill-label">Library up to date</span>
      </div>
    )
  }

  const job = activeJob
  const label = jobLabel(job)
  const pct = job.total ? Math.min(100, Math.round((job.processed / job.total) * 100)) : null
  const details = () =>
    showToast(
      `${label} in ${job.folder_path}${job.failed_count > 0 ? ` · ${job.failed_count} failed` : ''}`
    )

  return (
    <div className="job-pill busy" role="status" aria-live="polite">
      <button type="button" className="btn-reset job-pill-main" onClick={details} title={job.folder_path}>
        <span className="job-pill-dot" aria-hidden="true" />
        <span className="job-pill-label">
          {label}
          {job.failed_count > 0 && <span className="job-pill-failed"> · {job.failed_count} failed</span>}
        </span>
        <span
          className="job-pill-track"
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct ?? undefined}
        >
          <span
            className={`job-pill-fill${pct === null ? ' indeterminate' : ''}`}
            style={pct === null ? undefined : { width: `${pct}%` }}
          />
        </span>
      </button>
      <button
        type="button"
        className="btn-reset job-pill-cancel"
        onClick={() => cancelJob(job.id)}
        disabled={job.cancel_requested}
        aria-label="Cancel job"
        title="Stop after the files in progress; photos saved so far are kept"
      >
        <X size={13} />
      </button>
    </div>
  )
}
