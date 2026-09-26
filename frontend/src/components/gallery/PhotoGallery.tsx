import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useShallow } from 'zustand/react/shallow'
import type { PhotoMetadata } from '../../types/metadata'
import { PhotoCard } from './PhotoCard'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { SlidersHorizontal, CheckSquare } from 'lucide-react'

interface PhotoGalleryProps {
  photos: PhotoMetadata[]
}

const GAP = 16
const PADDING = 18
// Height of the text block under the 4:3 thumbnail (measured: 76px + 2px border). Only an estimate: rows are
// measured after they render, so a wrong guess costs nothing but a tiny scrollbar shift.
const CARD_INFO_HEIGHT = 78

/** Columns of an `auto-fill, minmax(min, 1fr)` grid for a given content width. */
function columnCount(contentWidth: number, minItemWidth: number): number {
  return Math.max(1, Math.floor((contentWidth + GAP) / (minItemWidth + GAP)))
}

export const PhotoGallery: React.FC<PhotoGalleryProps> = ({ photos }) => {
  const { gridItemSize, setGridItemSize, showToast } = useUiStore(
    useShallow((s) => ({ gridItemSize: s.gridItemSize, setGridItemSize: s.setGridItemSize, showToast: s.showToast })),
  )
  const selectAll = useSelectionStore((s) => s.selectAll)

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

  const handleSelectAll = () => {
    selectAll(photos.map((p) => p.file_hash))
    showToast(`Selected all ${photos.length} photos`)
  }

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
          Showing <span style={{ color: 'var(--text-primary)' }}>{photos.length}</span> photos
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

          <button className="btn btn-secondary" onClick={handleSelectAll} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
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
              {virtualizer.getVirtualItems().map((row) => {
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
          </div>
        )}
      </div>
    </main>
  )
}
