import React, { useEffect, useId, useRef, useState } from 'react'
import { useDialogFocus } from '../../hooks/useDialogFocus'

interface NameDialogProps {
  title: string
  label: string
  placeholder?: string
  submitLabel: string
  /** Resolves to whether it worked; the dialog stays open (with what was typed) when it did not. */
  onSubmit: (value: string) => Promise<boolean> | boolean
  onClose: () => void
}

/** A small modal asking for one name or tag. Mounted only while open (focus in, trapped, restored). */
export const NameDialog: React.FC<NameDialogProps> = ({ title, label, placeholder, submitLabel, onSubmit, onClose }) => {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const titleId = useId()
  useDialogFocus(dialogRef, inputRef)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = async () => {
    if (!value.trim() || busy) return
    setBusy(true)
    const ok = await onSubmit(value.trim())
    setBusy(false)
    if (ok) onClose()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal" onClick={(e) => e.stopPropagation()}>
        <div id={titleId} className="modal-title">
          {title}
        </div>
        <input
          ref={inputRef}
          type="text"
          className="text-input"
          aria-label={label}
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
        />
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void submit()} disabled={!value.trim() || busy}>
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
