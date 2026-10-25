import React, { useEffect, useId, useRef, useState } from 'react'
import { FolderOpen, FolderPlus, X } from 'lucide-react'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useRootActions, useRoots } from '../../hooks/useRoots'
import { useUiStore } from '../../stores/useUiStore'

/**
 * The folders the library rescans when the app starts (ADR-003 R11): add one, or stop watching one.
 * Removing a folder keeps its photos. A folder that cannot be read (an unplugged drive) is marked
 * offline and skipped quietly. Mounted once; open state is in the UI store.
 */
export const FoldersDialog: React.FC = () => {
  const open = useUiStore((s) => s.foldersDialogOpen)
  const setOpen = useUiStore((s) => s.setFoldersDialogOpen)
  if (!open) return null
  return <DialogBody onClose={() => setOpen(false)} />
}

const DialogBody: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const roots = useRoots()
  const { addRoot, isAdding, removeRoot } = useRootActions()
  const [folder, setFolder] = useState('')
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  useDialogFocus(dialogRef, inputRef)
  const titleId = useId()
  const canBrowse = Boolean(window.electronAPI?.openDirectory)

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

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    const path = folder.trim()
    if (!path) return
    try {
      await addRoot(path)
      setFolder('')
    } catch {
      // useRootActions showed why; keep the path to fix it.
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <FolderPlus size={18} />
          <h2 id={titleId}>Watched folders</h2>
          <button type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="dialog-intro">
          These folders are scanned whenever the app starts, so new and edited photos appear on their own. Stopping
          watching a folder keeps its photos in the library.
        </p>

        {roots.length === 0 ? (
          <p className="dialog-note">No folders are watched yet.</p>
        ) : (
          <ul className="dialog-options" style={{ listStyle: 'none', padding: 0 }}>
            {roots.map((r) => (
              <li key={r.path} style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span style={{ flex: 1, overflowWrap: 'anywhere' }}>
                  {r.path}
                  {!r.online && <em> (offline)</em>}
                </span>
                <button type="button" className="btn btn-secondary" onClick={() => removeRoot(r.path)} aria-label={`Stop watching ${r.path}`}>
                  Stop watching
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={add}>
          <label className="dialog-label" htmlFor={`${titleId}-path`}>
            Add a folder
          </label>
          <div className="dialog-row">
            <input
              id={`${titleId}-path`}
              ref={inputRef}
              className="dialog-input"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="D:\Photos\2024"
              spellCheck={false}
              autoComplete="off"
            />
            {canBrowse && (
              <button type="button" className="btn btn-secondary" onClick={browse}>
                <FolderOpen size={14} />
                <span>Browse…</span>
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={!folder.trim() || isAdding}>
              {isAdding ? 'Adding…' : 'Add and scan'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
