import React, { useEffect, useReducer, useRef } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getPreviewUrl, getThumbnailUrl } from '../../api/client'
import { useCuration } from '../../hooks/usePhotoMutations'
import { swapToPlaceholder } from '../../utils/placeholder'
import { shouldIgnoreHotkey } from '../../utils/hotkeys'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { filmstripWindow } from '../../utils/filmstrip'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { displayTitle, exposureLine } from '../../utils/photoFormat'
import { X, ChevronLeft, ChevronRight, Flag, ZoomIn, ZoomOut } from 'lucide-react'

export const LightboxModal: React.FC = () => {
  const { lightboxIndex, setLightboxIndex } = useUiStore(useShallow((s) => ({ lightboxIndex: s.lightboxIndex, setLightboxIndex: s.setLightboxIndex })))
  // A search by meaning is a ranking of the same list, so the viewer pages through it like any other.
  const { photos, totalCount, hasNextPage, isFetchingNextPage, fetchNextPage } = usePhotoSearch()
  if (lightboxIndex === null || photos.length === 0) return null
  // Next on the last loaded photo asks for the index one past it: show the last one until that page arrives.
  const index = Math.min(lightboxIndex, photos.length - 1)
  const currentPhoto = photos[index]
  // Past the last loaded photo: load the next page (and stay) rather than wrap to the first.
  const loadMore = hasNextPage ? () => { if (!isFetchingNextPage) void fetchNextPage() } : null
  return <Lightbox photos={photos} total={totalCount} index={index} currentPhoto={currentPhoto} setIndex={setLightboxIndex} loadMore={loadMore} />
}

/** Thumbnails in the filmstrip: a window around the current photo, never the whole library. */
const FILMSTRIP_SIZE = 13
const ZOOM_STEP = 1.35
const MAX_ZOOM = 8

type ZoomState = { zoom: number; panX: number; panY: number }
type ZoomAction =
  | { type: 'scale'; factor: number; cursorDx?: number; cursorDy?: number }
  | { type: 'reset' }
  | { type: 'pan'; dx: number; dy: number }

function zoomReducer(state: ZoomState, action: ZoomAction): ZoomState {
  switch (action.type) {
    case 'reset':
      return { zoom: 1, panX: 0, panY: 0 }
    case 'scale': {
      const { factor, cursorDx = 0, cursorDy = 0 } = action
      const nextZoom = Math.max(1, Math.min(MAX_ZOOM, state.zoom * factor))
      if (nextZoom === state.zoom) return state
      const ratio = nextZoom / state.zoom
      const panX = cursorDx * (1 - ratio) + state.panX * ratio
      const panY = cursorDy * (1 - ratio) + state.panY * ratio
      // At zoom=1 (clamped back to fit), snap pan to zero.
      return nextZoom === 1 ? { zoom: 1, panX: 0, panY: 0 } : { zoom: nextZoom, panX, panY }
    }
    case 'pan':
      return { ...state, panX: state.panX + action.dx, panY: state.panY + action.dy }
  }
}

interface LightboxProps {
  photos: PhotoMetadata[]
  /** All matches, loaded or not. */
  total: number
  index: number
  currentPhoto: PhotoMetadata
  setIndex: (idx: number | null) => void
  /** Loads the next page; null when every match is loaded. */
  loadMore: (() => void) | null
}

/** Mounted only while open, so focus moves in on open and back to the card on close. */
const Lightbox: React.FC<LightboxProps> = ({ photos, total, index: lightboxIndex, currentPhoto, setIndex: setLightboxIndex, loadMore }) => {
  const { patchPhoto } = useCuration()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ lastX: number; lastY: number } | null>(null)
  useDialogFocus(dialogRef, closeRef)

  const [{ zoom, panX, panY }, dispatch] = useReducer(zoomReducer, { zoom: 1, panX: 0, panY: 0 })

  // Reset zoom when the photo changes.
  useEffect(() => {
    dispatch({ type: 'reset' })
  }, [currentPhoto.file_hash])

  // Non-passive wheel listener so we can preventDefault and zoom without page scroll.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = stage.getBoundingClientRect()
      const cursorDx = e.clientX - (rect.left + rect.width / 2)
      const cursorDy = e.clientY - (rect.top + rect.height / 2)
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP
      dispatch({ type: 'scale', factor, cursorDx, cursorDy })
    }
    stage.addEventListener('wheel', onWheel, { passive: false })
    return () => stage.removeEventListener('wheel', onWheel)
  }, [])

  const showNext = () => {
    if (lightboxIndex + 1 < photos.length) setLightboxIndex(lightboxIndex + 1)
    else if (loadMore) {
      // One past the loaded photos: the viewer moves there as soon as the next page arrives.
      loadMore()
      setLightboxIndex(photos.length)
    } else setLightboxIndex(0)
  }
  const showPrevious = () => {
    if (lightboxIndex > 0) setLightboxIndex(lightboxIndex - 1)
    else if (!loadMore) setLightboxIndex(photos.length - 1) // wrap only when everything is loaded
  }

  // Keep a page ahead while stepping through, so Next rarely has to wait.
  useEffect(() => {
    if (loadMore && lightboxIndex >= photos.length - 5) loadMore()
  }, [lightboxIndex, photos.length, loadMore])

  const togglePick = () => {
    const next = !currentPhoto.flagged
    void patchPhoto(currentPhoto.file_hash, { flagged: next }, next ? 'Picked' : 'Pick removed')
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setLightboxIndex(null)
        return
      }
      if (shouldIgnoreHotkey(e)) return
      if (e.key === 'ArrowRight') {
        showNext()
      } else if (e.key === 'ArrowLeft') {
        showPrevious()
      } else if (e.key.toLowerCase() === 'p') {
        // Toggle Pick: the cache updates at once and rolls back with an error toast if the save fails
        togglePick()
      } else if (/^[0-5]$/.test(e.key)) {
        const rating = parseInt(e.key, 10)
        void patchPhoto(currentPhoto.file_hash, { rating: rating === 0 ? null : rating }, rating === 0 ? 'Rating cleared' : `Rated ${rating} ★`)
      } else if (e.key === '+' || e.key === '=') {
        dispatch({ type: 'scale', factor: ZOOM_STEP })
      } else if (e.key === '-') {
        dispatch({ type: 'scale', factor: 1 / ZOOM_STEP })
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  const handleDoubleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = stageRef.current?.getBoundingClientRect()
    if (!rect) return
    const cursorDx = e.clientX - (rect.left + rect.width / 2)
    const cursorDy = e.clientY - (rect.top + rect.height / 2)
    if (zoom > 1) {
      dispatch({ type: 'reset' })
    } else {
      dispatch({ type: 'scale', factor: 2.5, cursorDx, cursorDy })
    }
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (zoom <= 1) return
    e.currentTarget.setPointerCapture(e.pointerId)
    dragRef.current = { lastX: e.clientX, lastY: e.clientY }
  }
  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.lastX
    const dy = e.clientY - dragRef.current.lastY
    dragRef.current = { lastX: e.clientX, lastY: e.clientY }
    dispatch({ type: 'pan', dx, dy })
  }
  const handlePointerUp = () => { dragRef.current = null }

  const exif = currentPhoto.exif
  const [stripStart, stripEnd] = filmstripWindow(lightboxIndex, photos.length, FILMSTRIP_SIZE)
  const camera = [exif.camera_make, exif.camera_model].filter(Boolean).join(' ')
  const exposure = exposureLine(exif)

  const imgStyle: React.CSSProperties = zoom === 1
    ? {}
    : { transform: `translate(${panX}px, ${panY}px) scale(${zoom})` }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Photo viewer: ${currentPhoto.file_info.name}, ${lightboxIndex + 1} of ${total}`}
      aria-keyshortcuts="ArrowLeft ArrowRight P 0 1 2 3 4 5 Escape + -"
      className="lightbox"
      onClick={() => setLightboxIndex(null)}
    >
      <div className="lb-top" onClick={(e) => e.stopPropagation()}>
        <div className="lb-title">
          <span className="lb-name">{displayTitle(currentPhoto.file_info.name)}</span>
          <span className="lb-meta">{currentPhoto.file_info.name}</span>
          {camera && <span className="lb-meta">{camera}</span>}
          <span className="lb-meta num">
            {lightboxIndex + 1} of {total}
          </span>
        </div>
        <div className="lb-actions">
          <div className="lb-zoom-controls" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="btn-reset lb-icon lb-zoom-btn" onClick={() => dispatch({ type: 'scale', factor: 1 / ZOOM_STEP })} aria-label="Zoom out (-)">
              <ZoomOut size={16} />
            </button>
            <button type="button" className="btn-reset lb-zoom-level num" onClick={() => dispatch({ type: 'reset' })} aria-label="Reset zoom" title="Click to reset">
              {Math.round(zoom * 100)}%
            </button>
            <button type="button" className="btn-reset lb-icon lb-zoom-btn" onClick={() => dispatch({ type: 'scale', factor: ZOOM_STEP })} aria-label="Zoom in (+)">
              <ZoomIn size={16} />
            </button>
          </div>
          <span className="lb-stars num" aria-label={currentPhoto.rating ? `${currentPhoto.rating} stars` : 'Not rated'}>
            {currentPhoto.rating ? '★'.repeat(currentPhoto.rating) : ''}
          </span>
          <button type="button" className="btn-reset pick-btn lb-pick" onClick={togglePick} aria-pressed={currentPhoto.flagged} aria-keyshortcuts="P">
            <Flag size={14} />
            <span>{currentPhoto.flagged ? 'Picked' : 'Pick'}</span>
            <span className="key-hint">P</span>
          </button>
          <button ref={closeRef} type="button" className="btn-reset lb-icon" onClick={() => setLightboxIndex(null)} aria-label="Close viewer (Esc)">
            <X size={18} />
          </button>
        </div>
      </div>

      <div
        ref={stageRef}
        className={`lb-stage${zoom > 1 ? ' lb-stage--zoomed' : ''}`}
        onClick={(e) => e.stopPropagation()}
        onDoubleClick={handleDoubleClick}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <button type="button" className="btn-reset lb-nav lb-prev" onClick={showPrevious} aria-label="Previous photo">
          <ChevronLeft size={24} />
        </button>
        <img
          src={getPreviewUrl(currentPhoto.file_hash)}
          alt={currentPhoto.file_info.name}
          onError={swapToPlaceholder}
          style={imgStyle}
          draggable={false}
        />
        <button type="button" className="btn-reset lb-nav lb-next" onClick={showNext} aria-label="Next photo">
          <ChevronRight size={24} />
        </button>
      </div>

      {exposure && <div className="lb-exposure num">{exposure}</div>}

      <div className="lb-strip" onClick={(e) => e.stopPropagation()}>
        {photos.slice(stripStart, stripEnd).map((p, offset) => {
          const idx = stripStart + offset
          return (
            <button
              key={p.file_hash}
              type="button"
              className="btn-reset lb-thumb"
              onClick={() => setLightboxIndex(idx)}
              aria-label={`Show ${p.file_info.name}`}
              aria-current={idx === lightboxIndex ? 'true' : undefined}
            >
              <img src={getThumbnailUrl(p.file_hash, 100, 100)} alt="" onError={swapToPlaceholder} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
