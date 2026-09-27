import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useShallow } from 'zustand/react/shallow'
import type { SortField } from '../../types/metadata'
import { PhotoCard } from './PhotoCard'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { isDemoMode, usePhotoSearch } from '../../hooks/usePhotos'
import { errorMessage, searchPhotoIdsApi } from '../../api/client'
import { demoSearchIds } from '../../demo/demoLibrary'
import { SlidersHorizontal, CheckSquare } from 'lucide-react'

/** Sort choices, all applied by the server (PMO-27). Unknown capture dates always sort last. */
const SORTS: { value: string; label: string; field: SortField; order: 'asc' | 'desc' }[] = [
  { value: 'captured_at:desc', label: 'Newest first', field: 'captured_at', order: 'desc' },
  { value: 'captured_at:asc', label: 'Oldest first', field: 'captured_at', order: 'asc' },
  { value: 'file_name:asc', label: 'File name', field: 'file_name', order: 'asc' },
  { value: 'size_bytes:desc', label: 'Largest first', field: 'size_bytes', order: 'desc' },
  { value: 'camera_model:asc', label: 'Camera model', field: 'camera_model', order: 'asc' },
]

// Start loading the next page when the viewport is this many rows from the end of what is loaded.
const PREFETCH_ROWS = 4

const GAP = 16
const PADDING = 18
// Height of the text block under the 4:3 thumbnail (measured: 76px + 2px border). Only an estimate: rows are
// measured after they render, so a wrong guess costs nothing but a tiny scrollbar shift.
const CARD_INFO_HEIGHT = 78

/** Columns of an `auto-fill, minmax(min, 1fr)` grid for a given content width. */
function columnCount(contentWidth: number, minItemWidth: number): number {
  return Math.max(1, Math.floor((contentWidth + GAP) / (minItemWidth + GAP)))
}

export const PhotoGallery: React.FC = () => {
  const { gridItemSize, setGridItemSize, showToast, sortBy, sortOrder, setSort } = useUiStore(
    useShallow((s) => ({ gridItemSize: s.gridItemSize, setGridItemSize: s.setGridItemSize, showToast: s.showToast, sortBy: s.sortBy, sortOrder: s.sortOrder, setSort: s.setSort })),
  )
  const selectAll = useSelectionStore((s) => s.selectAll)
  const { photos, totalCount, request, hasNextPage, isFetchingNextPage, fetchNextPage, isPlaceholderData } = usePhotoSearch()
  const [selecting, setSelecting] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const update = () => setWidth(el.clientWidth)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const contentWidth = Math.max(0, width - PADDING * 2)
  const columns = columnCount(contentWidth, gridItemSize)
  const rowCount = Math.ceil(photos.length / columns)
  const cardWidth = (contentWidth - (columns - 1) * GAP) / columns
  const estimatedRowHeight = Math.max(1, cardWidth * 0.75 + CARD_INFO_HEIGHT + GAP)

  // Only the rows near the viewport exist in the DOM, so cost no longer grows with library size.
  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 3,
  })

  // Column count or card size changed: previously measured row heights are stale.
  useEffect(() => {
    virtualizer.measure()
  }, [columns, gridItemSize, virtualizer])

  // Infinite scroll: fetch the next page before the user reaches the end of the loaded rows.
  const virtualRows = virtualizer.getVirtualItems()
  const lastVisibleRow = virtualRows.length > 0 ? virtualRows[virtualRows.length - 1].index : -1
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && lastVisibleRow >= rowCount - PREFETCH_ROWS) {
      void fetchNextPage()
    }
  }, [lastVisibleRow, rowCount, hasNextPage, isFetchingNextPage, fetchNextPage])

  // Every match of the current filters, including pages not loaded yet.
  const handleSelectAll = async () => {
    setSelecting(true)
    try {
      const ids = await (isDemoMode() ? demoSearchIds(request) : searchPhotoIdsApi(request))
      selectAll(ids)
      showToast(`Selected all ${ids.length} photos`)
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setSelecting(false)
    }
  }

  const sortValue = `${sortBy}:${sortOrder}`

  return (
    <main
      style={{
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        background: 'var(--bg-primary)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Gallery Toolbar */}
      <div
        style={{
          padding: '10px 18px',
          borderBottom: '1px solid var(--border-color)',
          background: 'var(--bg-secondary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-primary)' }}>{totalCount}</span> photos
          {photos.length < totalCount && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · {photos.length} loaded</span>}
          {isPlaceholderData && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }} role="status"> · updating…</span>}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {/* Zoom Slider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <SlidersHorizontal size={14} />
            <span>Size:</span>
            <input
              type="range"
              min="160"
              max="320"
              value={gridItemSize}
              aria-label="Thumbnail size"
              onChange={(e) => setGridItemSize(parseInt(e.target.value))}
              style={{ width: '90px', accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
            />
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span>Sort:</span>
            <select
              value={sortValue}
              onChange={(e) => {
                const choice = SORTS.find((s) => s.value === e.target.value)
                if (choice) setSort(choice.field, choice.order)
              }}
              style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '3px 6px', fontSize: '0.78rem' }}
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          <button className="btn btn-secondary" onClick={() => void handleSelectAll()} disabled={selecting || totalCount === 0} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
            <CheckSquare size={13} />
            <span>Select All</span>
          </button>
        </div>
      </div>

      {/* Scroll area: always mounted so its width can be observed */}
      <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {photos.length === 0 ? (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <h3>No photos found</h3>
            <p style={{ fontSize: '0.85rem', marginTop: '6px' }}>Try resetting or modifying your active search filters.</p>
          </div>
        ) : (
          <div style={{ padding: `${PADDING}px`, paddingBottom: `${PADDING - GAP}px` }}>
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
              {virtualRows.map((row) => {
                const first = row.index * columns
                const cards = photos.slice(first, first + columns)
                return (
                  <div
                    key={row.key}
                    data-index={row.index}
                    ref={virtualizer.measureElement}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${row.start}px)`,
                      paddingBottom: `${GAP}px`,
                      display: 'grid',
                      gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                      gap: `${GAP}px`,
                      alignContent: 'start',
                    }}
                  >
                    {cards.map((photo, i) => (
                      <PhotoCard key={photo.file_hash} photo={photo} index={first + i} />
                    ))}
                  </div>
                )
              })}
            </div>
            {isFetchingNextPage && (
              <div role="status" style={{ textAlign: 'center', padding: '12px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Loading more photos…
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  )
}
