import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { getThumbnailUrl } from '../../api/client'
import { Flag, Check } from 'lucide-react'

interface PhotoCardProps {
  photo: PhotoMetadata
  onOpenLightbox?: () => void
}

export const PhotoCard: React.FC<PhotoCardProps> = ({ photo, onOpenLightbox }) => {
  const { inspectedPhoto, setInspectedPhoto } = useUiStore()
  const { isSelected, toggleSelect } = useSelectionStore()

  const selected = isSelected(photo.file_hash)
  const inspected = inspectedPhoto?.file_hash === photo.file_hash

  return (
    <div
      onClick={() => setInspectedPhoto(photo)}
      onDoubleClick={onOpenLightbox}
      style={{
        background: 'var(--bg-card)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        border: `1px solid ${
          inspected
            ? 'var(--accent-secondary)'
            : selected
            ? 'var(--accent-primary)'
            : 'var(--border-color)'
        }`,
        boxShadow: inspected || selected ? 'var(--shadow-glow)' : '0 1px 3px rgba(0,0,0,0.05)',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.2s',
      }}
      onMouseEnter={(e) => {
        if (!inspected && !selected) {
          e.currentTarget.style.borderColor = 'var(--accent-primary)'
          e.currentTarget.style.transform = 'translateY(-2px)'
        }
      }}
      onMouseLeave={(e) => {
        if (!inspected && !selected) {
          e.currentTarget.style.borderColor = 'var(--border-color)'
          e.currentTarget.style.transform = 'translateY(0)'
        }
      }}
    >
      {/* Thumbnail Wrap */}
      <div
        style={{
          position: 'relative',
          aspectRatio: '4 / 3',
          background: 'var(--box-bg)',
          overflow: 'hidden',
        }}
      >
        {/* Selection Checkbox */}
        <div
          onClick={(e) => {
            e.stopPropagation()
            toggleSelect(photo.file_hash)
          }}
          style={{
            position: 'absolute',
            top: '8px',
            left: '8px',
            width: '22px',
            height: '22px',
            background: selected ? 'var(--accent-primary)' : 'rgba(15, 23, 42, 0.75)',
            border: `1px solid ${selected ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.4)'}`,
            borderRadius: '4px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            zIndex: 10,
            cursor: 'pointer',
          }}
        >
          {selected && <Check size={14} strokeWidth={3} />}
        </div>

        {/* Flag Badge */}
        {photo.flagged && (
          <div
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              background: 'var(--bg-card)',
              backdropFilter: 'blur(4px)',
              padding: '2px 6px',
              borderRadius: '4px',
              fontSize: '0.72rem',
              color: 'var(--accent-warning)',
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
              zIndex: 10,
            }}
          >
            <Flag size={12} fill="var(--accent-warning)" />
          </div>
        )}

        <img
          src={getThumbnailUrl(photo.file_hash)}
          alt={photo.file_info.name}
          loading="lazy"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
          }}
          onError={(e) => {
            // Fallback placeholder
            e.currentTarget.src =
              'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=600&auto=format&fit=crop&q=80'
          }}
        />
      </div>

      {/* Card Info */}
      <div style={{ padding: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div
          style={{
            fontSize: '0.8rem',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            color: 'var(--text-primary)',
          }}
        >
          {photo.file_info.name}
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.72rem',
            color: 'var(--text-muted)',
          }}
        >
          <span>{photo.exif.camera_make || 'Unknown'}</span>
          <span>{photo.exif.f_stop ? `f/${photo.exif.f_stop}` : ''} {photo.exif.exposure_time || ''}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '2px' }}>
          <div style={{ display: 'flex', gap: '4px' }}>
            {photo.labels.slice(0, 2).map((tag) => (
              <span key={tag} className="badge badge-tag" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>
                #{tag}
              </span>
            ))}
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--accent-warning)' }}>
            {'★'.repeat(photo.rating || 4)}
          </span>
        </div>
      </div>
    </div>
  )
}
