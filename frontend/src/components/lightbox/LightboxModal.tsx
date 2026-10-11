import React, { useEffect, useRef } from 'react'
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
import { useSemanticPhotos } from '../../hooks/useAnalysis'
import { displayTitle, exposureLine } from '../../utils/photoFormat'
import { X, ChevronLeft, ChevronRight, Flag } from 'lucide-react'

export const LightboxModal: React.FC = () => {
  const { lightboxIndex, setLightboxIndex } = useUiStore(useShallow((s) => ({ lightboxIndex: s.lightboxIndex, setLightboxIndex: s.setLightboxIndex })))
  const library = usePhotoSearch()
  // While a search by meaning is on screen the viewer pages through its matches, not the library.
  const semantic = useSemanticPhotos()
  const inSemantic = semantic.semantic !== null
  const photos = inSemantic ? semantic.photos : library.photos
  const totalCount = inSemantic ? semantic.photos.length : library.totalCount
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = library
  if (lightboxIndex === null || photos.length === 0) return null
  // Next on the last loaded photo asks for the index one past it: show the last one until that page arrives.
  const index = Math.min(lightboxIndex, photos.length - 1)
  const currentPhoto = photos[index]
  // Past the last loaded photo: load the next page (and stay) rather than wrap to the first.
  const loadMore = !inSemantic && hasNextPage ? () => { if (!isFetchingNextPage) void fetchNextPage() } : null
  return <Lightbox photos={photos} total={totalCount} index={index} currentPhoto={currentPhoto} setIndex={setLightboxIndex} loadMore={loadMore} />
}

/** Thumbnails in the filmstrip: a window around the current photo, never the whole library. */
const FILMSTRIP_SIZE = 13

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
  useDialogFocus(dialogRef, closeRef)

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
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  const exif = currentPhoto.exif
  const [stripStart, stripEnd] = filmstripWindow(lightboxIndex, photos.length, FILMSTRIP_SIZE)
  const camera = [exif.camera_make, exif.camera_model].filter(Boolean).join(' ')
  const exposure = exposureLine(exif)

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Photo viewer: ${currentPhoto.file_info.name}, ${lightboxIndex + 1} of ${total}`}
      aria-keyshortcuts="ArrowLeft ArrowRight P 0 1 2 3 4 5 Escape"
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

      <div className="lb-stage" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="btn-reset lb-nav lb-prev" onClick={showPrevious} aria-label="Previous photo">
          <ChevronLeft size={24} />
        </button>
        <img src={getPreviewUrl(currentPhoto.file_hash)} alt={currentPhoto.file_info.name} onError={swapToPlaceholder} />
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
