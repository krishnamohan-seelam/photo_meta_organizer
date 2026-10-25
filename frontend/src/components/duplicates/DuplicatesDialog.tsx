import React, { useEffect, useId, useRef, useState } from 'react'
import { Copy, X } from 'lucide-react'
import { getThumbnailUrl } from '../../api/client'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useDuplicates, useHideCopy } from '../../hooks/useDuplicates'
import { useUiStore } from '../../stores/useUiStore'
import type { DuplicateGroup } from '../../types/metadata'
import { formatBytes } from '../../utils/photoFormat'

const PAGE = 25

/**
 * Photos kept at more than one path, biggest saving first (ADR-003 R11). It reports and hides
 * only: "Hide this copy" takes a copy out of the count, "Show again" puts it back. No file on disk
 * is deleted or moved; freeing the space is left to the user outside the app. Mounted once.
 */
export const DuplicatesDialog: React.FC = () => {
  const open = useUiStore((s) => s.duplicatesDialogOpen)
  const setOpen = useUiStore((s) => s.setDuplicatesDialogOpen)
  if (!open) return null
  return <DialogBody onClose={() => setOpen(false)} />
}

const DialogBody: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [limit, setLimit] = useState(PAGE)
  const { data } = useDuplicates(limit)
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

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <Copy size={18} />
          <h2 id={titleId}>Duplicates</h2>
          <button ref={closeRef} type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="dialog-intro">
          {data
            ? `${data.total_groups.toLocaleString()} photos are kept in more than one place; the extra copies take ${formatBytes(data.reclaimable_bytes)}. `
            : 'Looking for duplicates… '}
          Nothing here deletes a file. Hiding a copy only removes it from this count.
        </p>

        {data && data.groups.length === 0 && <p className="dialog-note">No duplicates. Every photo is kept in one place.</p>}

        <ul className="dupe-list">
          {data?.groups.map((g) => <GroupRow key={g.file_hash} group={g} />)}
        </ul>

        {data && data.groups.length < data.total_listed && (
          <div className="dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setLimit(limit + PAGE)}>
              Show more
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

const GroupRow: React.FC<{ group: DuplicateGroup }> = ({ group }) => {
  const hide = useHideCopy()
  return (
    <li className="dupe-group">
      <img className="dupe-thumb" src={getThumbnailUrl(group.file_hash, 96, 96)} alt="" loading="lazy" />
      <div className="dupe-body">
        <div className="dupe-head">
          {group.copies} {group.copies === 1 ? 'copy' : 'copies'} · {formatBytes(group.size_bytes)} each · {formatBytes(group.reclaimable_bytes)} extra
        </div>
        <ul className="dupe-files">
          {group.files.map((f) => (
            <li key={f.path} className={f.hidden || f.missing ? 'dupe-file dupe-file-off' : 'dupe-file'}>
              <span className="dupe-path" title={f.path}>
                {f.path}
              </span>
              {f.missing && <em>missing</em>}
              {f.hidden && <em>hidden</em>}
              {!f.missing && (
                <button
                  type="button"
                  className="btn-reset link-btn"
                  disabled={hide.isPending}
                  onClick={() => hide.mutate({ path: f.path, hidden: !f.hidden })}
                  aria-label={`${f.hidden ? 'Show again' : 'Hide this copy'}: ${f.path}`}
                >
                  {f.hidden ? 'Show again' : 'Hide this copy'}
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    </li>
  )
}
