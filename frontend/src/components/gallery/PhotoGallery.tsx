import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { PhotoCard } from './PhotoCard'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { SlidersHorizontal, CheckSquare } from 'lucide-react'

interface PhotoGalleryProps {
  photos: PhotoMetadata[]
  isLoading?: boolean
}

export const PhotoGallery: React.FC<PhotoGalleryProps> = ({ photos, isLoading }) => {
  const { gridItemSize, setGridItemSize, setLightboxIndex, showToast } = useUiStore()
  const { selectAll } = useSelectionStore()

  const handleSelectAll = () => {
    selectAll(photos.map((p) => p.file_hash))
    showToast(`Selected all ${photos.length} photos`)
  }

  return (
    <main
      style={{
        flex: 1,
        background: 'var(--bg-primary)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
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

      {/* Grid Container */}
      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading photos from index...
        </div>
      ) : photos.length === 0 ? (
        <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <h3>No photos found</h3>
          <p style={{ fontSize: '0.85rem', marginTop: '6px' }}>Try resetting or modifying your active search filters.</p>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(auto-fill, minmax(${gridItemSize}px, 1fr))`,
            gap: '16px',
            padding: '18px',
          }}
        >
          {photos.map((photo, index) => (
            <PhotoCard
              key={photo.file_hash}
              photo={photo}
              onOpenLightbox={() => setLightboxIndex(index)}
            />
          ))}
        </div>
      )}
    </main>
  )
}
