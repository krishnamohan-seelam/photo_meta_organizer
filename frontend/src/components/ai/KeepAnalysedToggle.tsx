import React, { useId } from 'react'
import { useKeepAnalysed, useSetKeepAnalysed } from '../../hooks/useKeepAnalysed'
import type { KeepAnalysed } from '../../types/metadata'

/** What the setting is doing right now, in words (null when there is nothing to add). */
export function keepAnalysedNote(k: KeepAnalysed): string | null {
  const photos = (n: number) => `${n.toLocaleString()} photo${n === 1 ? '' : 's'}`
  switch (k.state) {
    case 'off':
      return null
    case 'up_to_date':
      return 'Everything is analysed.'
    case 'waiting_for_model':
      return 'Waiting for the model: download it above first. Nothing is downloaded on its own.'
    case 'busy':
      return 'Working on it; progress is in the top bar.'
    case 'paused':
      return 'Paused. Resume or dismiss it from the top bar.'
    case 'needs_approval':
      return `${photos(k.pending)} are waiting, more than the ${k.threshold.toLocaleString()} it does without asking. Analyse them yourself when you are ready.`
    case 'waiting_for_idle':
      return `${photos(k.pending)} waiting. It starts once you have been still for a little while.`
    case 'on_battery':
      return `${photos(k.pending)} waiting. It starts when the computer is plugged in.`
    case 'stalled':
      return 'Some photos could not be read, so it stopped. It tries again when new photos arrive.'
    case 'ready':
      return `${photos(k.pending)} waiting. Starting shortly.`
  }
}

/**
 * "Keep the library analysed": off until chosen. Even when on, analysis starts by itself only when the
 * model is installed, not too many photos wait, the app is idle and (desktop) the computer is plugged in.
 */
export const KeepAnalysedToggle: React.FC = () => {
  const { data } = useKeepAnalysed()
  const set = useSetKeepAnalysed()
  const id = useId()
  if (!data) return null
  const note = keepAnalysedNote(data)
  return (
    <div className="ai-keep">
      <label htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={data.enabled}
          disabled={set.isPending}
          onChange={(e) => set.mutate(e.target.checked)}
        />{' '}
        Keep the library analysed automatically
      </label>
      <p className="dialog-note">
        New photos are analysed in the background, only while you are not busy, and never without the model you already
        downloaded. You can pause or cancel it from the top bar.
      </p>
      {note && (
        <p className="dialog-note" role="status">
          {note}
        </p>
      )}
    </div>
  )
}
