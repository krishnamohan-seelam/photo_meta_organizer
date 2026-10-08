import React from 'react'
import { Check, Flag } from 'lucide-react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { getThumbnailUrl } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { displayTitle, exposureLine } from '../../utils/photoFormat'

interface PhotoCardProps {
  photo: PhotoMetadata
  /** Position of this photo in the list the lightbox pages through. */
  index: number
  width: number
  height: number
  /** Edge of the square thumbnail requested from the server (it keeps the aspect ratio). */
  thumbSize: number
}

// memo + narrow selectors: the grid can hold thousands of tiles, and a tile must re-render
// only when its own photo, selection state or inspected state changes, never on every store update.
export const PhotoCard = React.memo(function PhotoCard({ photo, index, width, height, thumbSize }: PhotoCardProps) {
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const setLightboxIndex = useUiStore((s) => s.setLightboxIndex)
  const inspected = useUiStore((s) => s.inspectedHash === photo.file_hash)
  const selected = useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))
  const toggleSelect = useSelectionStore((s) => s.toggleSelect)

  const name = photo.file_info.name
  const title = displayTitle(name)
  const exposure = exposureLine(photo.exif)
  const description = [
    title === name ? name : `${title}, ${name}`,
    photo.rating ? `${photo.rating} star${photo.rating > 1 ? 's' : ''}` : null,
    photo.flagged ? 'picked' : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div className={`tile${selected ? ' sel' : ''}${inspected ? ' cur' : ''}`} style={{ width, height }}>
      {/* The whole tile is one button: click inspects, Ctrl/⌘-click selects, double-click opens (FR-1c.8). */}
      <button
        type="button"
        className="btn-reset tile-hit"
        aria-label={description}
        aria-current={inspected ? 'true' : undefined}
        title={`${name} · double-click or Enter to open`}
        data-photo-index={index}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) toggleSelect(photo.file_hash, photo.file_info.size_bytes)
          else setInspectedHash(photo.file_hash)
        }}
        onDoubleClick={() => setLightboxIndex(index)}
      />

      {/* Selection checkbox: a sibling of the tile button, never nested in it */}
      <button
        type="button"
        role="checkbox"
        aria-checked={selected}
        aria-label={`Select ${name}`}
        className="btn-reset tile-check"
        onClick={() => toggleSelect(photo.file_hash, photo.file_info.size_bytes)}
      >
        <Check size={13} strokeWidth={3} />
      </button>

      <img src={getThumbnailUrl(photo.file_hash, thumbSize, thumbSize)} alt="" loading="lazy" decoding="async" onError={swapToPlaceholder} />

      {(photo.flagged || photo.rating) && (
        <div className="tile-badges" aria-hidden="true">
          {photo.flagged && (
            <span className="tile-badge pick">
              <Flag size={11} fill="currentColor" />
            </span>
          )}
          {photo.rating ? <span className="tile-badge num">{photo.rating}★</span> : null}
        </div>
      )}

      <div className="tile-scrim" aria-hidden="true">
        <div className="tile-title">{title}</div>
        {exposure && <div className="tile-exposure">{exposure}</div>}
      </div>
    </div>
  )
})
