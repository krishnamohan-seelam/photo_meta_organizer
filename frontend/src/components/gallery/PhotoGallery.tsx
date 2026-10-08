import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { PhotoCard } from './PhotoCard'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { useLibraryHotkeys } from '../../hooks/useLibraryHotkeys'
import { justifiedRows } from '../../utils/justifiedLayout'
import { photoAspectRatio } from '../../utils/photoFormat'

// Start loading the next page when the viewport is this many rows from the end of what is loaded.
const PREFETCH_ROWS = 4
/** Gap between tiles and rows (Appendix A). */
const GAP = 4
/** Side padding of the scroll area (`.gallery-scroll`). */
const PADDING = 16

/** Square thumbnail box requested for a row height: one of two sizes, so the server cache stays warm. */
function thumbBox(rowHeight: number): number {
  return rowHeight <= 220 ? 320 : 640
}

/** Justified rows of photos (FR-1c), virtualized with exact row heights (G-4). */
export const PhotoGallery: React.FC = () => {
  const gridItemSize = useUiStore((s) => s.gridItemSize)
  const selecting = useSelectionStore((s) => s.selectedHashes.size > 0)
  const { photos, hasNextPage, isFetchingNextPage, fetchNextPage } = usePhotoSearch()

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

  // Layout depends only on stored dimensions, never on images having loaded (G-4).
  const ratios = useMemo(() => photos.map((p) => ({ ratio: photoAspectRatio(p) })), [photos])
  const contentWidth = Math.max(0, width - PADDING * 2)
  const rows = useMemo(() => justifiedRows(ratios, contentWidth, gridItemSize, GAP), [ratios, contentWidth, gridItemSize])

  // Only the rows near the viewport exist in the DOM; their heights are exact, so nothing is measured.
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (i) => rows[i].height + GAP,
    overscan: 4,
  })

  useEffect(() => {
    virtualizer.measure()
  }, [rows, virtualizer])

  const rowOf = useCallback((index: number) => rows.findIndex((r) => index >= r.start && index < r.end), [rows])

  // Come back to the photo that was at the top (switching from the table, FR-2c.1).
  const restored = useRef(false)
  useEffect(() => {
    if (restored.current || rows.length === 0) return
    restored.current = true
    const row = rowOf(useUiStore.getState().topPhotoIndex)
    if (row > 0) virtualizer.scrollToIndex(row, { align: 'start' })
  }, [rows, rowOf, virtualizer])

  // Infinite scroll: fetch the next page before the user reaches the end of the loaded rows.
  const virtualRows = virtualizer.getVirtualItems()
  const lastVisibleRow = virtualRows.length > 0 ? virtualRows[virtualRows.length - 1].index : -1
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && lastVisibleRow >= rows.length - PREFETCH_ROWS) {
      void fetchNextPage()
    }
  }, [lastVisibleRow, rows.length, hasNextPage, isFetchingNextPage, fetchNextPage])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el || !restored.current) return
    const first = virtualRows.find((r) => r.end > el.scrollTop)
    if (first && rows[first.index]) useUiStore.getState().setTopPhotoIndex(rows[first.index].start)
  }

  const reveal = useCallback(
    (index: number) => {
      const row = rowOf(index)
      if (row >= 0) virtualizer.scrollToIndex(row, { align: 'auto' })
    },
    [rowOf, virtualizer]
  )
  useLibraryHotkeys({
    photos,
    reveal,
    loadMore: hasNextPage && !isFetchingNextPage ? () => void fetchNextPage() : null,
  })

  const thumbSize = thumbBox(gridItemSize)

  return (
    // Always mounted so its width can be observed
    <div ref={scrollRef} className={`gallery-scroll${selecting ? ' selecting' : ''}`} onScroll={onScroll}>
      {photos.length === 0 ? (
        <div className="gallery-empty">
          <b>No photos match</b>
          Remove a filter or search for something else.
        </div>
      ) : (
        <>
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualRows.map((vRow) => {
              const row = rows[vRow.index]
              return (
                <div key={vRow.key} className="jrow" style={{ height: row.height, transform: `translateY(${vRow.start}px)` }}>
                  {photos.slice(row.start, row.end).map((photo, i) => (
                    <PhotoCard
                      key={photo.file_hash}
                      photo={photo}
                      index={row.start + i}
                      width={ratios[row.start + i].ratio * row.height}
                      height={row.height}
                      thumbSize={thumbSize}
                    />
                  ))}
                </div>
              )
            })}
          </div>
          {isFetchingNextPage && (
            <div role="status" className="gallery-status">
              Loading more photos…
            </div>
          )}
        </>
      )}
    </div>
  )
}
