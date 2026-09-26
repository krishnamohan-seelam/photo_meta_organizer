import React, { useEffect, useId, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { FolderOpen, FolderPlus, RefreshCw, X } from 'lucide-react'
import { useJobActions } from '../../hooks/useJobs'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useUiStore } from '../../stores/useUiStore'
import type { JobDialogKind } from '../../stores/useUiStore'
import { loadRecentFolders, rememberFolder } from '../../utils/recentFolders'

const COPY: Record<JobDialogKind, { title: string; intro: string; submit: string }> = {
  index: {
    title: 'Scan a folder',
    intro: 'Read the EXIF data of every photo in the folder (and its subfolders) and add it to the library.',
    submit: 'Start scan',
  },
  sync: {
    title: 'Sync a folder',
    intro:
      'Re-check a folder you already scanned: add new photos and re-read edited ones. Photos from other folders are not touched.',
    submit: 'Start sync',
  },
}

/** In-app folder dialog for Scan and Sync (replaces `window.prompt`). Mounted once; open state is in the UI store. */
export const FolderJobDialog: React.FC = () => {
  const { kind, setJobDialog } = useUiStore(useShallow((s) => ({ kind: s.jobDialog, setJobDialog: s.setJobDialog })))
  if (!kind) return null
  // Keyed so every opening starts from fresh state.
  return <DialogBody key={kind} kind={kind} onClose={() => setJobDialog(null)} />
}

const DialogBody: React.FC<{ kind: JobDialogKind; onClose: () => void }> = ({ kind, onClose }) => {
  const [recent] = useState(loadRecentFolders)
  const [folder, setFolder] = useState(recent[0] ?? '')
  const [cleanupDeleted, setCleanupDeleted] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [rehash, setRehash] = useState(false)
  const { startJob, isStarting } = useJobActions()
  const inputRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  useDialogFocus(formRef, inputRef)
  const titleId = useId()
  const listId = useId()
  const copy = COPY[kind]
  const canBrowse = Boolean(window.electronAPI?.openDirectory)

  useEffect(() => {
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const browse = async () => {
    const picked = await window.electronAPI?.openDirectory()
    if (picked) setFolder(picked)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const folderPath = folder.trim()
    if (!folderPath) return
    try {
      await startJob({
        kind,
        folderPath,
        sync: kind === 'sync' ? { cleanup_deleted: cleanupDeleted, dry_run: dryRun, rehash } : undefined,
      })
      rememberFolder(folderPath)
      onClose()
    } catch {
      // useJobActions already showed the server's reason; keep the dialog open to fix the path.
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form ref={formRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onSubmit={submit}>
        <div className="dialog-header">
          {kind === 'index' ? <FolderPlus size={18} /> : <RefreshCw size={18} />}
          <h2 id={titleId}>{copy.title}</h2>
          <button type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="dialog-intro">{copy.intro}</p>

        <label className="dialog-label" htmlFor={`${titleId}-path`}>
          Folder path
        </label>
        <div className="dialog-row">
          <input
            id={`${titleId}-path`}
            ref={inputRef}
            className="dialog-input"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            placeholder="D:\Photos\2024"
            list={recent.length ? listId : undefined}
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
        {recent.length > 0 && (
          <datalist id={listId}>
            {recent.map((f) => (
              <option key={f} value={f} />
            ))}
          </datalist>
        )}

        {kind === 'sync' && (
          <fieldset className="dialog-options">
            <legend>Options</legend>
            <label>
              <input type="checkbox" checked={cleanupDeleted} onChange={(e) => setCleanupDeleted(e.target.checked)} />
              Remove photos whose files are gone from this folder
            </label>
            <label>
              <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
              Preview only: report what would change, change nothing
            </label>
            <label>
              <input type="checkbox" checked={rehash} onChange={(e) => setRehash(e.target.checked)} />
              Re-hash every file (slow; catches edits that kept size and date)
            </label>
          </fieldset>
        )}

        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!folder.trim() || isStarting}>
            {isStarting ? 'Starting…' : copy.submit}
          </button>
        </div>
      </form>
    </div>
  )
}
