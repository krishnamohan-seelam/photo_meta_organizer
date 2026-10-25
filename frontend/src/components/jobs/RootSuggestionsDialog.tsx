import React, { useEffect, useId, useRef, useState } from 'react'
import { FolderSearch } from 'lucide-react'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useRootActions, useRootSuggestions } from '../../hooks/useRoots'
import type { RootSuggestions } from '../../types/metadata'

type Suggestion = RootSuggestions['suggestions'][number]

/**
 * Offered once to a library that already has photos but no watched folders (ADR-003 R11): the
 * folders its files lie in, as a checkbox list. Nothing is watched unless the user confirms;
 * "Not now" is remembered, watching stays off, and scanning a folder by hand still works.
 */
export const RootSuggestionsDialog: React.FC = () => {
  const suggestions = useRootSuggestions()
  if (suggestions.length === 0) return null
  return <DialogBody suggestions={suggestions} />
}

const DialogBody: React.FC<{ suggestions: Suggestion[] }> = ({ suggestions }) => {
  const { addRoot, skipSuggestions } = useRootActions()
  const [chosen, setChosen] = useState(() => new Set(suggestions.filter((s) => s.online).map((s) => s.path)))
  const [saving, setSaving] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const actionRef = useRef<HTMLButtonElement>(null)
  useDialogFocus(dialogRef, actionRef)
  const titleId = useId()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') skipSuggestions()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [skipSuggestions])

  const toggle = (path: string) =>
    setChosen((prev) => {
      const next = new Set(prev)
      if (!next.delete(path)) next.add(path)
      return next
    })

  const watch = async () => {
    setSaving(true)
    try {
      for (const path of chosen) await addRoot(path)
      // With roots stored the offer ends by itself; with none ticked it is the same as skipping.
      if (chosen.size === 0) skipSuggestions()
    } catch {
      // useRootActions showed why; stay open so the choice can be changed.
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <FolderSearch size={18} />
          <h2 id={titleId}>Keep these folders up to date?</h2>
        </div>
        <p className="dialog-intro">
          Your library holds photos from these folders. Tick the ones to rescan whenever the app starts, so new photos
          appear on their own. Nothing is watched unless you choose it.
        </p>
        <fieldset className="dialog-options">
          <legend>Folders</legend>
          {suggestions.map((s) => (
            <label key={s.path} title={s.online ? undefined : 'This folder cannot be read right now'}>
              <input type="checkbox" checked={chosen.has(s.path)} onChange={() => toggle(s.path)} />
              {s.path} ({s.file_count.toLocaleString()} {s.file_count === 1 ? 'photo' : 'photos'}
              {s.online ? '' : ', offline'})
            </label>
          ))}
        </fieldset>
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={skipSuggestions} disabled={saving}>
            Not now
          </button>
          <button ref={actionRef} type="button" className="btn btn-primary" onClick={watch} disabled={saving || chosen.size === 0}>
            {saving ? 'Saving…' : `Watch ${chosen.size} ${chosen.size === 1 ? 'folder' : 'folders'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
