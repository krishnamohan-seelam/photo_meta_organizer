import React from 'react'
import { FolderInput, RefreshCw, Sparkles } from 'lucide-react'
import { useUiStore } from '../../stores/useUiStore'
import { useJobs } from '../../hooks/useJobs'
import { JobStatusPill } from './JobStatusPill'
import { QueryBar } from './QueryBar'

/** Slim top bar (FR-1b.4): the query bar (FR-2b), job status, Sync and Import. Everything else lives in the rail and palette. */
export const TopBar: React.FC = () => {
  const setJobDialog = useUiStore((s) => s.setJobDialog)
  const setAiDialogOpen = useUiStore((s) => s.setAiDialogOpen)
  const { activeJob } = useJobs()
  const busy = activeJob !== null

  return (
    <header className="topbar">
      <QueryBar />
      <div className="topbar-actions">
        <JobStatusPill />
        <button
          type="button"
          className="btn icon-btn"
          onClick={() => setAiDialogOpen(true)}
          aria-label="Search by meaning: set up and analyze"
          title="Search by meaning: download the model and analyze the library"
        >
          <Sparkles size={16} />
        </button>
        <button
          type="button"
          className="btn icon-btn"
          onClick={() => setJobDialog('sync')}
          disabled={busy}
          aria-label="Sync a folder"
          title={busy ? 'Wait for the running job to finish' : 'Re-check a scanned folder for new, edited and deleted photos'}
        >
          <RefreshCw size={16} />
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setJobDialog('index')}
          disabled={busy}
          title={busy ? 'Wait for the running job to finish' : 'Scan and index photos from a folder'}
        >
          <FolderInput size={15} />
          <span>Import</span>
        </button>
      </div>
    </header>
  )
}
