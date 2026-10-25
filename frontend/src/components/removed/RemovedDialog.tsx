import React, { useEffect, useId, useRef } from 'react'
import { Trash2, X } from 'lucide-react'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useRemovedFiles, useRestoreRemoved } from '../../hooks/useRemoval'
import { useUiStore } from '../../stores/useUiStore'
import { formatBytes } from '../../utils/photoFormat'

/**
 * Files removed from the library for good (ticket 12). Scans skip them while they are unchanged on disk;
 * Restore forgets one and scans its folder so it is recorded again. Nothing here touches a file on disk.
 */
export const RemovedDialog: React.FC = () => {
  const open = useUiStore((s) => s.removedDialogOpen)
  const setOpen = useUiStore((s) => s.setRemovedDialogOpen)
  if (!open) return null
  return <DialogBody onClose={() => setOpen(false)} />
}

const DialogBody: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { data } = useRemovedFiles(true)
  const restore = useRestoreRemoved()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useDialogFocus(dialogRef, closeRef)
  const titleId = useId()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const files = data ?? []
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <Trash2 size={18} />
          <h2 id={titleId}>Removed from library</h2>
          <button ref={closeRef} type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="dialog-intro">
          These files are skipped when folders are scanned, so removed photos stay removed. Nothing here deletes a file: they are still on
          your disk. Restore one to have it added back.
        </p>
        {files.length === 0 ? (
          <p className="dialog-note">Nothing has been removed.</p>
        ) : (
          <ul className="removed-list">
            {files.map((f) => (
              <li key={f.path}>
                <span className="removed-path" title={f.path}>
                  {f.path}
                </span>
                <span className="removed-meta">{formatBytes(f.size_bytes)}</span>
                <button type="button" className="btn-reset link-btn" disabled={restore.isPending} onClick={() => restore.mutate([f.path])} aria-label={`Restore ${f.path}`}>
                  Restore
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
