import React, { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Check, Flag, ListChecks, MapPin } from 'lucide-react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { getThumbnailUrl } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { useFacets } from '../../hooks/useFacets'
import { UNKNOWN_DATE } from '../../utils/captureDate'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { displayTitle, formatCapturedAt, photoAspectRatio } from '../../utils/photoFormat'
import {
  GAP_PRESETS,
  chapterHero,
  chapterLabel,
  chapterSubtitle,
  groupIntoChapters,
  tileSpan,
  type Chapter,
} from '../../utils/chapters'
import { LoadMore } from '../states/LoadMore'

/** Grid row height and gap of the mosaic (FR-3.4), used to estimate an off-screen chapter's height. */
const MOSAIC_ROW = 170
const MOSAIC_GAP = 12

interface TileProps {
  photo: PhotoMetadata
  index: number
  hero: boolean
}

/** A mosaic tile: same states and actions as a Library tile (FR-3.5), cropped on purpose. */
const TimelineTile = React.memo(function TimelineTile({ photo, index, hero }: TileProps) {
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const setLightboxIndex = useUiStore((s) => s.setLightboxIndex)
  const selected = useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))
  const toggleSelect = useSelectionStore((s) => s.toggleSelect)
  const span = hero ? 'hero' : tileSpan(photoAspectRatio(photo))
  const name = photo.file_info.name
  const title = displayTitle(name)
  const time = photo.exif.captured_at ? formatCapturedAt(photo.exif.captured_at).split(' · ')[1] : null

  return (
    <div className={`tile mtile span-${span}${selected ? ' sel' : ''}`}>
      <button
        type="button"
        className="btn-reset tile-hit"
        aria-label={[title === name ? name : `${title}, ${name}`, photo.rating ? `${photo.rating} stars` : null, photo.flagged ? 'picked' : null].filter(Boolean).join(', ')}
        title={`${name} · double-click or Enter to open`}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) toggleSelect(photo.file_hash, photo.file_info.size_bytes)
          else setInspectedHash(photo.file_hash)
        }}
        onDoubleClick={() => setLightboxIndex(index)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            setLightboxIndex(index)
          }
        }}
      />
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
      <img src={getThumbnailUrl(photo.file_hash, hero ? 640 : 320, hero ? 640 : 320)} alt="" loading="lazy" decoding="async" onError={swapToPlaceholder} />
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
        {time && <div className="tile-exposure">{time}</div>}
      </div>
    </div>
  )
})

/** Rough height of a chapter that is not rendered yet (`contain-intrinsic-size`, FR-3.9). */
function estimatedHeight(count: number): number {
  const rows = Math.ceil((count * 1.3) / 5)
  return 80 + rows * (MOSAIC_ROW + MOSAIC_GAP)
}

const ChapterSection: React.FC<{ chapter: Chapter; indexOf: Map<string, number>; headed: boolean }> = ({ chapter, indexOf, headed }) => {
  const setActiveView = useUiStore((s) => s.setActiveView)
  const hero = chapterHero(chapter.photos)
  const geotagged = chapter.photos.filter((p) => p.exif.location).length
  const title = !headed ? 'Photos' : chapter.undated || !chapter.start || !chapter.end ? 'Unknown date' : chapterLabel(chapter.start, chapter.end)
  const selectChapter = () =>
    useSelectionStore.getState().addToSelection(chapter.photos.map((p) => ({ file_hash: p.file_hash, size_bytes: p.file_info.size_bytes })))

  return (
    <section className="chapter" aria-label={title} style={{ containIntrinsicSize: `auto ${estimatedHeight(chapter.photos.length)}px` }}>
      {headed && (
        <header className="chapter-head">
          <div>
            <h2 className="chapter-title">{title}</h2>
            <p className="chapter-sub">{chapterSubtitle(chapter.photos)}</p>
          </div>
          <div className="chapter-actions">
            {geotagged > 0 && (
              <button type="button" className="btn btn-sm" onClick={() => setActiveView('map')} title="Show on the map (same filters)">
                <MapPin size={14} />
                <span className="num">{geotagged}</span>
              </button>
            )}
            <button type="button" className="btn btn-sm chapter-select" onClick={selectChapter}>
              <ListChecks size={14} />
              Select chapter
            </button>
          </div>
        </header>
      )}
      <div className="mosaic">
        {chapter.photos.map((p) => (
          <TimelineTile key={p.file_hash} photo={p} index={indexOf.get(p.file_hash) ?? 0} hero={p.file_hash === hero} />
        ))}
      </div>
    </section>
  )
}

/** The Timeline as a photo book (FR-3): trip-like chapters with a mosaic, over the loaded pages. */
export const TimelineView: React.FC = () => {
  const { photos, totalCount, hasNextPage, isFetchingNextPage, fetchNextPage } = usePhotoSearch()
  const { filterTimeframe, setTimeframeFilter, sortBy, setSort, chapterGapHours, setChapterGapHours } = useUiStore(
    useShallow((s) => ({
      filterTimeframe: s.filterTimeframe,
      setTimeframeFilter: s.setTimeframeFilter,
      sortBy: s.sortBy,
      setSort: s.setSort,
      chapterGapHours: s.chapterGapHours,
      setChapterGapHours: s.setChapterGapHours,
    }))
  )
  const { years } = useFacets()
  const byDate = sortBy === 'captured_at'

  // Regrouping is local: changing the gap never refetches (FR-3.10).
  const chapters = useMemo(
    () => (byDate ? groupIntoChapters(photos, { gapHours: chapterGapHours }) : [{ id: 'flat', photos, start: null, end: null, undated: false }]),
    [photos, byDate, chapterGapHours]
  )
  const indexOf = useMemo(() => new Map(photos.map((p, i) => [p.file_hash, i])), [photos])
  const timeframes = ['all', ...years.map((y) => y.name).sort().reverse(), UNKNOWN_DATE]

  return (
    <div className="timeline">
      <div className="timeline-bar">
        <div className="chip-row" role="group" aria-label="Year">
          {timeframes.map((yr) => (
            <button key={yr} type="button" className="btn-reset pill" aria-pressed={filterTimeframe === yr} onClick={() => setTimeframeFilter(yr)}>
              {yr === 'all' ? 'All years' : yr === UNKNOWN_DATE ? 'Unknown date' : yr}
            </button>
          ))}
        </div>
        <span className="toolbar-spacer" />
        {byDate && (
          <label className="gap-control">
            <span>Chapter gap</span>
            <select className="select" value={chapterGapHours} onChange={(e) => setChapterGapHours(Number(e.target.value))}>
              {GAP_PRESETS.map((p) => (
                <option key={p.hours} value={p.hours}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {!byDate && (
        <div className="timeline-notice" role="status">
          Chapters follow capture date.
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => setSort('captured_at', 'desc')}>
            Sort by date
          </button>
        </div>
      )}

      <div className="chapters">
        {photos.length === 0 ? (
          <div className="gallery-empty">
            <b>No photos match</b>
            Remove a filter or pick another year.
          </div>
        ) : (
          chapters.map((c) => <ChapterSection key={c.id} chapter={c} indexOf={indexOf} headed={byDate} />)
        )}
        <LoadMore loaded={photos.length} total={totalCount} hasMore={Boolean(hasNextPage)} loading={isFetchingNextPage} onLoadMore={() => void fetchNextPage()} />
      </div>
    </div>
  )
}
