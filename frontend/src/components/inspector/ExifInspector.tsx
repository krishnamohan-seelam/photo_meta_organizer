import React, { useEffect, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Copy, Flag, Plus, Star, X } from 'lucide-react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useInspectedPhoto, usePhotoSearch } from '../../hooks/usePhotos'
import { useCuration } from '../../hooks/usePhotoMutations'
import { useHistogram } from '../../hooks/useHistogram'
import { getThumbnailUrl } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { BINS, histogramScale, type RgbHistogram } from '../../utils/histogram'
import {
  displayTitle,
  exposureParts,
  fileFormat,
  formatBytes,
  formatCapturedAt,
  lensModel,
  shortHash,
} from '../../utils/photoFormat'
import { NameDialog } from '../collections/NameDialog'
import { AiTagsSection } from '../ai/AiTagsSection'

/** Inspector preview: a 640 px box, the same size the gallery asks for at large rows. */
const PREVIEW_BOX = 640

/** Three filled channel areas, blended additively so overlaps read as white (FR-1e.2). */
const HistogramCanvas: React.FC<{ histogram: RgbHistogram }> = ({ histogram }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const dpr = window.devicePixelRatio || 1
    const w = (canvas.width = Math.round((canvas.clientWidth || 288) * dpr))
    const h = (canvas.height = Math.round((canvas.clientHeight || 72) * dpr))
    ctx.clearRect(0, 0, w, h)
    const scale = histogramScale(histogram)
    const styles = getComputedStyle(canvas)
    ctx.globalCompositeOperation = 'lighter'
    for (const channel of ['r', 'g', 'b'] as const) {
      const bins = histogram[channel]
      ctx.fillStyle = styles.getPropertyValue(`--histo-${channel}`).trim() || 'gray'
      ctx.beginPath()
      ctx.moveTo(0, h)
      for (let i = 0; i < BINS; i++) {
        ctx.lineTo((i / (BINS - 1)) * w, h - Math.min(1, bins[i] / scale) * h * 0.95)
      }
      ctx.lineTo(w, h)
      ctx.closePath()
      ctx.fill()
    }
  }, [histogram])

  return <canvas ref={canvasRef} className="histo" role="img" aria-label="RGB histogram of the photo" />
}

export const ExifInspector: React.FC = () => {
  const photo = useInspectedPhoto()
  const inspectorOpen = useUiStore((s) => s.inspectorOpen)
  if (!inspectorOpen) return null
  if (!photo) {
    return (
      <aside className="inspector-pane inspector-empty" aria-label="Details">
        Select a photo to see its details
      </aside>
    )
  }
  return <Inspector photo={photo} />
}

const Inspector: React.FC<{ photo: PhotoMetadata }> = ({ photo }) => {
  const { showToast, setLightboxIndex } = useUiStore(useShallow((s) => ({ showToast: s.showToast, setLightboxIndex: s.setLightboxIndex })))
  const { photos } = usePhotoSearch()
  const { patchPhoto } = useCuration()
  const [addingTag, setAddingTag] = useState(false)

  const previewUrl = getThumbnailUrl(photo.file_hash, PREVIEW_BOX, PREVIEW_BOX)
  const histogram = useHistogram(photo.file_hash, previewUrl)
  const index = photos.findIndex((p) => p.file_hash === photo.file_hash)
  const exif = photo.exif
  const expo = exposureParts(exif)
  const lens = lensModel(exif)
  const camera = [exif.camera_make, exif.camera_model].filter(Boolean).join(' ')
  const title = displayTitle(photo.file_info.name)

  // The cached record updates at once and rolls back with an error toast if the save fails.
  const setRating = (rating: number) =>
    patchPhoto(photo.file_hash, { rating: photo.rating === rating ? null : rating }, photo.rating === rating ? 'Rating cleared' : `Rated ${rating} ★`)
  const togglePick = () => {
    const next = !photo.flagged
    return patchPhoto(photo.file_hash, { flagged: next }, next ? 'Picked' : 'Pick removed')
  }

  const copy = (text: string, what: string) =>
    navigator.clipboard.writeText(text).then(
      () => showToast(`Copied ${what}`),
      () => showToast('Could not copy to the clipboard', 'error')
    )

  return (
    <aside className="inspector-pane" aria-label="Details">
      <button
        type="button"
        className="btn-reset insp-preview"
        onClick={() => index >= 0 && setLightboxIndex(index)}
        disabled={index < 0}
        aria-label={`Open ${photo.file_info.name} in the viewer`}
      >
        <img src={previewUrl} alt="" onError={swapToPlaceholder} />
      </button>

      <div className="insp-title">{title}</div>
      <div className="insp-file">{photo.file_info.name}</div>

      <div className="curate">
        <div className="stars" role="radiogroup" aria-label="Rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={photo.rating === n}
              aria-label={`${n} star${n > 1 ? 's' : ''}`}
              aria-keyshortcuts={String(n)}
              className={`btn-reset${(photo.rating ?? 0) >= n ? ' on' : ''}`}
              onClick={() => void setRating(n)}
            >
              <Star size={17} />
            </button>
          ))}
        </div>
        <button type="button" className="btn-reset pick-btn" aria-pressed={photo.flagged} aria-keyshortcuts="P" onClick={() => void togglePick()}>
          <Flag size={13} />
          <span>{photo.flagged ? 'Picked' : 'Pick'}</span>
          <span className="key-hint">P</span>
        </button>
      </div>

      {histogram !== null && (
        <section className="insp-sec" aria-label="Histogram">
          <h3>
            Histogram <span>{histogram === 'loading' ? 'reading pixels…' : 'from pixels'}</span>
          </h3>
          {histogram === 'loading' ? <div className="histo-placeholder" /> : <HistogramCanvas histogram={histogram} />}
        </section>
      )}

      <section className="insp-sec" aria-label="Exposure">
        <h3>Exposure</h3>
        <div className="expo">
          <div>
            <b>{expo.aperture}</b>
            <small>Aperture</small>
          </div>
          <div>
            <b>{expo.shutter}</b>
            <small>Shutter</small>
          </div>
          <div>
            <b>{expo.iso}</b>
            <small>ISO</small>
          </div>
          <div>
            <b>{expo.focal}</b>
            <small>mm</small>
          </div>
        </div>
      </section>

      <section className="insp-sec" aria-label="Details">
        <h3>
          Details
          <button type="button" className="btn-reset link-btn" onClick={() => void copy(JSON.stringify(photo, null, 2), 'the raw JSON')}>
            <Copy size={11} /> JSON
          </button>
        </h3>
        <dl className="kv">
          <dt>Camera</dt>
          <dd>{camera || '—'}</dd>
          {lens && (
            <>
              <dt>Lens</dt>
              <dd>{lens}</dd>
            </>
          )}
          <dt>Captured</dt>
          <dd className="num">{formatCapturedAt(exif.captured_at)}</dd>
          <dt>Location</dt>
          <dd className="num">
            {exif.location ? `${exif.location.latitude.toFixed(2)}, ${exif.location.longitude.toFixed(2)}` : 'Not geotagged'}
          </dd>
          <dt>Size</dt>
          <dd className="num">
            {photo.dimensions.width && photo.dimensions.height
              ? `${photo.dimensions.width} × ${photo.dimensions.height} · ${((photo.dimensions.width * photo.dimensions.height) / 1e6).toFixed(1)} MP`
              : '—'}
          </dd>
          <dt>File</dt>
          <dd className="num">
            {fileFormat(photo.file_info.name)} · {formatBytes(photo.file_info.size_bytes)}
          </dd>
          <dt>Hash</dt>
          <dd className="hash" title={photo.file_hash}>
            <span>{shortHash(photo.file_hash)}</span>
            <button type="button" className="btn-reset" onClick={() => void copy(photo.file_hash, 'the hash')} aria-label="Copy hash">
              <Copy size={12} />
            </button>
          </dd>
        </dl>
      </section>

      <section className="insp-sec" aria-label="Tags">
        <h3>Tags</h3>
        <div className="insp-tags">
          {photo.labels.map((tag) => (
            <span key={tag} className="chip">
              {tag}
              <button
                type="button"
                className="btn-reset"
                aria-label={`Remove tag ${tag}`}
                onClick={() => void patchPhoto(photo.file_hash, { remove_tags: [tag] }, `Removed #${tag}`)}
              >
                <X size={12} />
              </button>
            </span>
          ))}
          <button type="button" className="btn-reset pill pill-add" onClick={() => setAddingTag(true)}>
            <Plus size={12} /> Add
          </button>
        </div>
      </section>

      <AiTagsSection hash={photo.file_hash} name={photo.file_info.name} />

      {addingTag && (
        <NameDialog
          title="Add a tag"
          label="Tag"
          placeholder="e.g. sunset"
          submitLabel="Add tag"
          onSubmit={(tag) => patchPhoto(photo.file_hash, { add_tags: [tag] }, `Added #${tag}`)}
          onClose={() => setAddingTag(false)}
        />
      )}
    </aside>
  )
}
