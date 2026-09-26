import React from 'react'
import { Loader2, X } from 'lucide-react'
import type { Job } from '../../api/client'
import { useJobActions } from '../../hooks/useJobs'

function label(job: Job): string {
  const verb = job.kind === 'sync' ? 'Syncing' : 'Indexing'
  if (job.cancel_requested) return 'Cancelling…'
  if (job.total === null) return `${verb}: finding files…`
  return `${verb} ${job.processed.toLocaleString()} / ${job.total.toLocaleString()}`
}

/** Header strip for the running job: what, how far, failures so far, and Cancel. */
export const JobProgress: React.FC<{ job: Job }> = ({ job }) => {
  const { cancelJob } = useJobActions()
  const pct = job.total ? Math.min(100, Math.round((job.processed / job.total) * 100)) : null

  return (
    <div className="job-progress" role="status" aria-live="polite" title={job.folder_path}>
      <Loader2 size={14} className="spin" />
      <div className="job-progress-body">
        <span className="job-progress-label">
          {label(job)}
          {job.failed_count > 0 && <span className="job-progress-failed"> · {job.failed_count} failed</span>}
        </span>
        <div
          className="job-progress-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct ?? undefined}
          aria-label={label(job)}
        >
          <div
            className={`job-progress-fill${pct === null ? ' indeterminate' : ''}`}
            style={pct === null ? undefined : { width: `${pct}%` }}
          />
        </div>
      </div>
      <button
        className="btn btn-secondary job-progress-cancel"
        onClick={() => cancelJob(job.id)}
        disabled={job.cancel_requested}
        title="Stop after the files in progress; photos saved so far are kept"
        aria-label="Cancel job"
      >
        <X size={13} />
      </button>
    </div>
  )
}
