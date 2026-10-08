import React, { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import { useUiStore } from '../../stores/useUiStore'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { SHORTCUTS } from '../../utils/shortcuts'

/** The keyboard map (FR-1d.5), opened with `?`, the rail or the command palette. */
export const ShortcutsOverlay: React.FC = () => {
  const open = useUiStore((s) => s.shortcutsOpen)
  return open ? <Shortcuts /> : null
}

const Shortcuts: React.FC = () => {
  const close = () => useUiStore.getState().setShortcutsOpen(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useDialogFocus(dialogRef, closeRef)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') useUiStore.getState().setShortcutsOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="palette-backdrop" onClick={close}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="shortcuts">
          <h2 id={titleId}>
            Keyboard shortcuts
            <button ref={closeRef} type="button" className="btn icon-btn" onClick={close} aria-label="Close">
              <X size={16} />
            </button>
          </h2>
          <table>
            <tbody>
              {SHORTCUTS.map((s) => (
                <tr key={s.action}>
                  <td>
                    {s.keys.map((k) => (
                      <kbd key={k} className="kbd-chip">
                        {k}
                      </kbd>
                    ))}
                  </td>
                  <td>
                    <div>{s.action}</div>
                  </td>
                  <td>{s.scope}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
