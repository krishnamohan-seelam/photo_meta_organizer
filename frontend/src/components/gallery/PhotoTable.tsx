import React, { useCallback, useEffect, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useShallow } from 'zustand/react/shallow'
import { ArrowDown, ArrowUp, Check, Flag, Minus } from 'lucide-react'
import type { PhotoMetadata, SortField } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { useLibraryHotkeys, type StepKeys } from '../../hooks/useLibraryHotkeys'
import { useSelectAllMatches } from '../../hooks/useSelectAllMatches'
import { getThumbnailUrl } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { displayTitle, exposureParts, formatBytes, formatCapturedAt, lensModel } from '../../utils/photoFormat'

/** Fixed row height (FR-2c.4): rows are never measured. */
export const ROW_HEIGHT = 38
/** Start loading the next page this many rows before the end of what is loaded. */
const PREFETCH_ROWS = 20
/** ISO from which the value is highlighted as high (FR-2c.2). */
const HIGH_ISO = 3200

const TABLE_STEP_KEYS: StepKeys = { previous: ['ArrowUp', 'k', 'K'], next: ['ArrowDown', 'j', 'J'] }

/** The four columns the API can sort by (FR-2c.3), with their natural first-click order. */
const SORTABLE: Record<string, { field: SortField; natural: 'asc' | 'desc' }> = {
  name: { field: 'file_name', natural: 'asc' },
  camera: { field: 'camera_model', natural: 'asc' },
  captured: { field: 'captured_at', natural: 'desc' },
  size: { field: 'size_bytes', natural: 'desc' },
}

const COLUMNS: { id: string; label: string; className?: string; numeric?: boolean }[] = [
  { id: 'thumb', label: '' },
  { id: 'name', label: 'Name' },
  { id: 'camera', label: 'Camera' },
  { id: 'lens', label: 'Lens', className: 'col-lens' },
  { id: 'mm', label: 'mm', numeric: true },
  { id: 'f', label: 'ƒ', numeric: true },
  { id: 'shutter', label: 'Shutter', numeric: true },
  { id: 'iso', label: 'ISO', numeric: true },
  { id: 'captured', label: 'Captured', numeric: true },
  { id: 'rating', label: 'Rating' },
  { id: 'size', label: 'Size', className: 'col-size', numeric: true },
]

const SortHeader: React.FC<{ id: string; label: string; className?: string; numeric?: boolean }> = ({ id, label, className, numeric }) => {
  const { sortBy, sortOrder, setSort } = useUiStore(useShallow((s) => ({ sortBy: s.sortBy, sortOrder: s.sortOrder, setSort: s.setSort })))
  const sortable = SORTABLE[id]
  const cls = `tcell${numeric ? ' num-cell' : ''}${className ? ` ${className}` : ''}`
  if (!sortable) {
    return (
      <div role="columnheader" className={cls}>
        {label}
      </div>
    )
  }
  const active = sortBy === sortable.field
  const ariaSort = active ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'
  // First click: the natural order; clicking the sorted column again reverses it.
  const onClick = () => setSort(sortable.field, active ? (sortOrder === 'asc' ? 'desc' : 'asc') : sortable.natural)
  return (
    <div role="columnheader" aria-sort={ariaSort} className={cls}>
      <button type="button" className={`btn-reset th-sort${active ? ' active' : ''}`} onClick={onClick}>
        {label}
        {active && (sortOrder === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
      </button>
    </div>
  )
}

interface RowProps {
  photo: PhotoMetadata
  index: number
  start: number
  onActivate: (index: number, e: React.MouseEvent) => void
}

const TableRow = React.memo(function TableRow({ photo, index, start, onActivate }: RowProps) {
  const inspected = useUiStore((s) => s.inspectedHash === photo.file_hash)
  const selected = useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))
  const toggleSelect = useSelectionStore((s) => s.toggleSelect)
  const setLightboxIndex = useUiStore((s) => s.setLightboxIndex)
  const exif = photo.exif
  const expo = exposureParts(exif)
  const lens = lensModel(exif)
  const name = photo.file_info.name
  const captured = exif.captured_at ? exif.captured_at.slice(0, 10) : '—'

  return (
    <div
      role="row"
      aria-rowindex={index + 2}
      aria-selected={selected}
      className={`trow${selected ? ' sel' : ''}${inspected ? ' cur' : ''}`}
      style={{ transform: `translateY(${start}px)` }}
      onClick={(e) => onActivate(index, e)}
      onDoubleClick={() => setLightboxIndex(index)}
    >
      <div role="gridcell" className="tcell tcheck">
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-label={`Select ${name}`}
          className="btn-reset tbox"
          onClick={(e) => {
            e.stopPropagation()
            toggleSelect(photo.file_hash, photo.file_info.size_bytes)
          }}
        >
          <Check size={11} strokeWidth={3} />
        </button>
      </div>
      <div role="gridcell" className="tcell">
        <img className="tthumb" src={getThumbnailUrl(photo.file_hash, 100, 100)} alt="" loading="lazy" onError={swapToPlaceholder} />
      </div>
      <div role="gridcell" className="tcell tname">
        <button type="button" className="btn-reset tname-btn" data-photo-index={index} aria-current={inspected ? 'true' : undefined} title={name}>
          <span className="tname-title">{displayTitle(name)}</span>
          <span className="tname-file">{name}</span>
        </button>
      </div>
      <div role="gridcell" className="tcell" title={[exif.camera_make, exif.camera_model].filter(Boolean).join(' ')}>
        <span className="ellipsis">
          {exif.camera_model || '—'} {exif.camera_make && <span className="tmuted">{exif.camera_make}</span>}
        </span>
      </div>
      <div role="gridcell" className="tcell col-lens">
        <span className="ellipsis">{lens ?? '—'}</span>
      </div>
      <div role="gridcell" className="tcell num-cell">{expo.focal}</div>
      <div role="gridcell" className="tcell num-cell">{expo.aperture === '—' ? '—' : expo.aperture.slice(2)}</div>
      <div role="gridcell" className="tcell num-cell">{expo.shutter}</div>
      <div role="gridcell" className={`tcell num-cell${exif.iso && exif.iso >= HIGH_ISO ? ' iso-high' : ''}`}>{expo.iso}</div>
      <div role="gridcell" className="tcell num-cell" title={formatCapturedAt(exif.captured_at)}>
        {captured}
      </div>
      <div role="gridcell" className="tcell trating" aria-label={`${photo.rating ? `${photo.rating} stars` : 'Not rated'}${photo.flagged ? ', picked' : ''}`}>
        <span aria-hidden="true">{photo.rating ? '★'.repeat(photo.rating) : ''}</span>
        {photo.flagged && <Flag size={12} className="tpick" aria-hidden="true" />}
      </div>
      <div role="gridcell" className="tcell num-cell col-size">{formatBytes(photo.file_info.size_bytes)}</div>
    </div>
  )
})

/**
 * Dense, sortable table layout of the Library (FR-2c): sticky header, 38 px virtualized rows,
 * click/Ctrl/Shift selection, and J/K keyboard culling.
 */
export const PhotoTable: React.FC = () => {
  const { photos, totalCount, hasNextPage, isFetchingNextPage, fetchNextPage } = usePhotoSearch()
  const selectedCount = useSelectionStore((s) => s.selectedHashes.size)
  const { selectAllMatches, busy } = useSelectAllMatches()
  const scrollRef = useRef<HTMLDivElement>(null)
  const anchor = useRef<number | null>(null)

  const virtualizer = useVirtualizer({
    count: photos.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  })

  // Come back to the photo that was at the top (switching from the grid, FR-2c.1).
  useEffect(() => {
    const top = useUiStore.getState().topPhotoIndex
    if (top > 0) virtualizer.scrollToIndex(top, { align: 'start' })
    // Once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const items = virtualizer.getVirtualItems()
  const last = items.length > 0 ? items[items.length - 1].index : -1
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && last >= photos.length - PREFETCH_ROWS) void fetchNextPage()
  }, [last, photos.length, hasNextPage, isFetchingNextPage, fetchNextPage])

  const onScroll = () => {
    const el = scrollRef.current
    if (el) useUiStore.getState().setTopPhotoIndex(Math.floor(el.scrollTop / ROW_HEIGHT))
  }

  const selectRange = useCallback(
    (from: number, to: number) => {
      const [a, b] = from <= to ? [from, to] : [to, from]
      useSelectionStore.getState().addToSelection(photos.slice(a, b + 1).map((p) => ({ file_hash: p.file_hash, size_bytes: p.file_info.size_bytes })))
    },
    [photos]
  )

  // Click inspects and sets the anchor; Ctrl/⌘ toggles; Shift selects the range from the anchor (FR-2c.5).
  const onActivate = useCallback(
    (index: number, e: React.MouseEvent) => {
      const photo = photos[index]
      if (!photo) return
      if (e.shiftKey && anchor.current !== null) {
        selectRange(anchor.current, index)
      } else if (e.ctrlKey || e.metaKey) {
        useSelectionStore.getState().toggleSelect(photo.file_hash, photo.file_info.size_bytes)
        anchor.current = index
      } else {
        anchor.current = index
      }
      useUiStore.getState().setInspectedHash(photo.file_hash)
    },
    [photos, selectRange]
  )

  const reveal = useCallback((index: number) => virtualizer.scrollToIndex(index, { align: 'auto' }), [virtualizer])
  useLibraryHotkeys({
    photos,
    reveal,
    loadMore: hasNextPage && !isFetchingNextPage ? () => void fetchNextPage() : null,
    stepKeys: TABLE_STEP_KEYS,
    spaceSelects: true,
    onShiftStep: (from, to) => {
      if (anchor.current === null) anchor.current = from
      selectRange(anchor.current, to)
    },
  })

  const allSelected = totalCount > 0 && selectedCount >= totalCount
  const headerChecked = allSelected ? 'true' : selectedCount > 0 ? 'mixed' : 'false'
  const onHeaderCheck = () => {
    if (allSelected) useSelectionStore.getState().clearSelection()
    else void selectAllMatches()
  }

  return (
    <div className="ptable" role="grid" aria-label="Photos" aria-rowcount={totalCount + 1} aria-multiselectable="true">
      <div className="thead" role="rowgroup">
        <div className="trow-head" role="row" aria-rowindex={1}>
          <div role="columnheader" className="tcell tcheck">
            <button
              type="button"
              role="checkbox"
              aria-checked={headerChecked}
              aria-label={allSelected ? 'Clear the selection' : 'Select all matching photos'}
              className={`btn-reset tbox${headerChecked !== 'false' ? ' on' : ''}`}
              onClick={onHeaderCheck}
              disabled={busy || totalCount === 0}
            >
              {headerChecked === 'mixed' ? <Minus size={11} strokeWidth={3} /> : <Check size={11} strokeWidth={3} />}
            </button>
          </div>
          {COLUMNS.map((c) => (
            <SortHeader key={c.id} {...c} />
          ))}
        </div>
      </div>
      <div ref={scrollRef} className="tbody-scroll" role="rowgroup" onScroll={onScroll}>
        {photos.length === 0 ? (
          <div className="gallery-empty">
            <b>No photos match</b>
            Remove a filter or search for something else.
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {items.map((item) => (
              <TableRow key={photos[item.index].file_hash} photo={photos[item.index]} index={item.index} start={item.start} onActivate={onActivate} />
            ))}
          </div>
        )}
        {isFetchingNextPage && (
          <div role="status" className="gallery-status">
            Loading more photos…
          </div>
        )}
      </div>
    </div>
  )
}
