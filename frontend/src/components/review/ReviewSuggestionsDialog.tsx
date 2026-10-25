import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Check, Sparkles, X } from 'lucide-react'
import { getPreviewUrl } from '../../api/client'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useAcceptAbove, useReviewCount, useReviewDecision, useReviewItems, useReviewLabels } from '../../hooks/useReview'
import { useUiStore } from '../../stores/useUiStore'
import { shouldIgnoreHotkey } from '../../utils/hotkeys'

/** Where "accept all" starts: confident enough to take without looking at each photo. */
export const DEFAULT_BULK_CONFIDENCE = 0.3

const percent = (confidence: number) => `${Math.round(confidence * 100)}%`

/**
 * Work through the AI's suggested tags in bulk (ticket 18): one label at a time, the most confident
 * photos first. A accepts, R rejects, J / K move on and back. "Accept all" takes every suggestion
 * of the label over a confidence in one go, after showing how many that is.
 * Mounted once; open state is in the UI store.
 */
export const ReviewSuggestionsDialog: React.FC = () => {
  const open = useUiStore((s) => s.reviewDialogOpen)
  const setOpen = useUiStore((s) => s.setReviewDialogOpen)
  if (!open) return null
  return <DialogBody onClose={() => setOpen(false)} />
}

const DialogBody: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const labels = useReviewLabels(true).data ?? []
  const [chosen, setChosen] = useState<string | null>(null)
  const label = chosen && labels.some((l) => l.label === chosen) ? chosen : (labels[0]?.label ?? null)
  const [index, setIndex] = useState(0)
  // Decided in this session: hidden at once, before the server round trip finishes.
  const [decided, setDecided] = useState<Set<string>>(() => new Set())
  const { data: page } = useReviewItems(label)
  const decide = useReviewDecision()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  useDialogFocus(dialogRef, closeRef)
  const titleId = useId()

  const items = useMemo(() => (page?.items ?? []).filter((i) => !decided.has(i.file_hash)), [page, decided])
  const at = Math.min(index, Math.max(items.length - 1, 0))
  const current = items[at]

  const choose = (next: string) => {
    setChosen(next)
    setIndex(0)
    setDecided(new Set())
  }

  const resolve = (action: 'accept' | 'reject') => {
    if (!current || !label) return
    const hash = current.file_hash
    setDecided((prev) => new Set(prev).add(hash))
    decide.mutate(
      { hash, label, action },
      {
        onError: () =>
          setDecided((prev) => {
            const next = new Set(prev)
            next.delete(hash)
            return next
          }),
      }
    )
  }
  const step = (by: number) => setIndex(Math.min(Math.max(at + by, 0), Math.max(items.length - 1, 0)))

  // One listener for the dialog's lifetime; it always calls the latest handlers.
  const latest = useRef({ resolve, step, onClose })
  latest.current = { resolve, step, onClose }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') return latest.current.onClose()
      if (shouldIgnoreHotkey(e)) return
      const key = e.key.toLowerCase()
      if (key === 'a') latest.current.resolve('accept')
      else if (key === 'r') latest.current.resolve('reject')
      else if (key === 'j' || e.key === 'ArrowRight') latest.current.step(1)
      else if (key === 'k' || e.key === 'ArrowLeft') latest.current.step(-1)
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog dialog-wide review" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <Sparkles size={18} />
          <h2 id={titleId}>Review suggestions</h2>
          <button ref={closeRef} type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        {labels.length === 0 ? (
          <p className="dialog-note">Nothing to review. Suggestions appear after the library has been analysed.</p>
        ) : (
          <div className="review-body">
            <ul className="review-labels" aria-label="Labels">
              {labels.map((l) => (
                <li key={l.label}>
                  <button type="button" className="btn-reset review-label" aria-pressed={l.label === label} onClick={() => choose(l.label)}>
                    <span>{l.label}</span>
                    <span className="review-label-meta">
                      {l.count} · up to {percent(l.top_confidence)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            <div className="review-main">
              {current ? (
                <figure className="review-card">
                  <img src={getPreviewUrl(current.file_hash)} alt={current.name} />
                  <figcaption>
                    <strong>{label}</strong> · {percent(current.confidence)} sure · {current.name}
                    <span className="review-position">
                      {at + 1} of {items.length}
                      {page && page.total > items.length ? ` (+${page.total - items.length} more)` : ''}
                    </span>
                  </figcaption>
                </figure>
              ) : (
                <p className="dialog-note">Every suggestion of this label has been reviewed.</p>
              )}

              <div className="review-actions">
                <button type="button" className="btn btn-primary" disabled={!current} onClick={() => resolve('accept')}>
                  <Check size={14} /> Accept <kbd>A</kbd>
                </button>
                <button type="button" className="btn btn-secondary" disabled={!current} onClick={() => resolve('reject')}>
                  <X size={14} /> Reject <kbd>R</kbd>
                </button>
                <button type="button" className="btn btn-secondary" disabled={at === 0} onClick={() => step(-1)}>
                  Previous <kbd>K</kbd>
                </button>
                <button type="button" className="btn btn-secondary" disabled={at >= items.length - 1} onClick={() => step(1)}>
                  Next <kbd>J</kbd>
                </button>
              </div>

              {label && <BulkAccept key={label} label={label} />}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/** "Accept all at or above N" with the count shown first, and a second click to confirm. */
const BulkAccept: React.FC<{ label: string }> = ({ label }) => {
  const [text, setText] = useState(String(DEFAULT_BULK_CONFIDENCE))
  const [confirming, setConfirming] = useState(false)
  const parsed = Number(text)
  const valid = text.trim() !== '' && Number.isFinite(parsed) && parsed >= 0 && parsed <= 1
  const { data } = useReviewCount(valid ? label : null, parsed)
  const acceptAbove = useAcceptAbove()
  const inputId = useId()
  const count = valid ? (data?.count ?? null) : null

  const apply = async () => {
    if (count === null) return
    await acceptAbove(label, parsed, count)
    setConfirming(false)
  }

  return (
    <div className="review-bulk">
      <label htmlFor={inputId}>Accept “{label}” on every photo at or above</label>
      <input
        id={inputId}
        className="dialog-input review-threshold"
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setConfirming(false)
        }}
        aria-invalid={!valid}
      />
      {!confirming ? (
        <button type="button" className="btn btn-secondary" disabled={!valid || !count} onClick={() => setConfirming(true)}>
          {count === null ? 'Accept all…' : `Accept all (${count.toLocaleString()} ${count === 1 ? 'photo' : 'photos'})…`}
        </button>
      ) : (
        <>
          <span role="alert">
            Add “{label}” to {count?.toLocaleString()} {count === 1 ? 'photo' : 'photos'}?
          </span>
          <button type="button" className="btn btn-primary" onClick={() => void apply()}>
            Accept {count?.toLocaleString()}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      )}
    </div>
  )
}
