import React, { useEffect, useId, useRef } from 'react'
import { useDialogFocus } from '../../hooks/useDialogFocus'

interface ConfirmDialogProps {
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onClose: () => void
}

/** Asks before something that is hard to notice undoing. Mounted only while open (focus in, trapped, restored). */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({ title, message, confirmLabel, onConfirm, onClose }) => {
  const dialogRef = useRef<HTMLDivElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useDialogFocus(dialogRef, confirmRef)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <h2 id={titleId}>{title}</h2>
        </div>
        <p className="dialog-intro">{message}</p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            className="btn btn-primary"
            onClick={() => {
              onConfirm()
              onClose()
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
