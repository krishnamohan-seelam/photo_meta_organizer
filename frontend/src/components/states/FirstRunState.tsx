import React, { useState } from 'react'
import { FolderOpen, FolderPlus, Loader2, Sparkles } from 'lucide-react'
import { useJobs } from '../../hooks/useJobs'
import { useRootActions } from '../../hooks/useRoots'
import { useUiStore } from '../../stores/useUiStore'
import { loadRecentFolders } from '../../utils/recentFolders'

const centred: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '12px',
  padding: '40px',
  textAlign: 'center',
  color: 'var(--text-muted)',
}

/**
 * The empty library's one path (ADR-003 R11): choose a folder, watch it scan, optionally set up
 * search by meaning. The folder becomes a root, so it is rescanned whenever the app starts.
 * While the scan runs the progress is live (event stream); the library replaces this panel as
 * soon as the first photos are in.
 */
export const FirstRunState: React.FC = () => {
  const { activeJob } = useJobs()
  const { addRoot, isAdding } = useRootActions()
  const setAiDialogOpen = useUiStore((s) => s.setAiDialogOpen)
  const [folder, setFolder] = useState(() => loadRecentFolders()[0] ?? '')
  const canBrowse = Boolean(window.electronAPI?.openDirectory)

  const browse = async () => {
    const picked = await window.electronAPI?.openDirectory()
    if (picked) setFolder(picked)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const path = folder.trim()
    if (!path) return
    try {
      await addRoot(path)
    } catch {
      // useRootActions already showed the server's reason; keep the path to fix it.
    }
  }

  if (activeJob) {
    const known = activeJob.total !== null
    return (
      <div style={centred} role="status" aria-live="polite">
        <Loader2 size={32} className="spin" />
        <h3 style={{ color: 'var(--text-primary)' }}>Reading your photos…</h3>
        <p style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
          {known
            ? `${activeJob.processed.toLocaleString()} of ${activeJob.total?.toLocaleString()} photos in ${activeJob.folder_path}`
            : `Looking through ${activeJob.folder_path}…`}
        </p>
        <button type="button" className="btn btn-secondary" onClick={() => setAiDialogOpen(true)}>
          <Sparkles size={14} />
          <span>Set up search by meaning (optional)</span>
        </button>
      </div>
    )
  }

  return (
    <form style={centred} onSubmit={submit}>
      <FolderPlus size={36} color="var(--accent-primary)" />
      <h3 style={{ color: 'var(--text-primary)' }}>Your library is empty</h3>
      <p style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
        Choose the folder your photos are in. It is read once, and again whenever the app starts, so new photos
        appear on their own.
      </p>
      <div className="dialog-row" style={{ width: 'min(480px, 100%)' }}>
        <input
          className="dialog-input"
          aria-label="Photo folder"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          placeholder="D:\Photos"
          spellCheck={false}
          autoComplete="off"
        />
        {canBrowse && (
          <button type="button" className="btn btn-secondary" onClick={browse}>
            <FolderOpen size={14} />
            <span>Browse…</span>
          </button>
        )}
      </div>
      <button type="submit" className="btn btn-primary" disabled={!folder.trim() || isAdding}>
        <FolderPlus size={14} />
        <span>{isAdding ? 'Starting…' : 'Scan this folder'}</span>
      </button>
    </form>
  )
}
