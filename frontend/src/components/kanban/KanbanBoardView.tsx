import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl } from '../../api/client'
import { useCuration } from '../../hooks/usePhotoMutations'
import { swapToPlaceholder } from '../../utils/placeholder'
import { Inbox, Star, CheckCircle } from 'lucide-react'

interface KanbanBoardViewProps {
  photos: PhotoMetadata[]
}

export const KanbanBoardView: React.FC<KanbanBoardViewProps> = ({ photos }) => {
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const { patchPhoto } = useCuration()

  // Columns:
  // 1. Inbox (unrated or rating <= 2)
  // 2. Picks & Flagged (flagged or rating >= 4)
  // 3. Export Ready (rating === 5 or tagged 'export')
  const inbox = photos.filter((p) => !p.flagged && (p.rating || 0) < 4)
  const picks = photos.filter((p) => p.flagged || (p.rating || 0) === 4)
  const exportQueue = photos.filter((p) => (p.rating || 0) === 5 || p.labels.includes('export'))

  // The card moves only once the server has confirmed the save; a failure shows an error toast instead.
  const handlePromoteToPick = (photo: PhotoMetadata) =>
    patchPhoto(photo.file_hash, { flagged: true, rating: 4 }, `Moved ${photo.file_info.name} to Picks`)

  const handlePromoteToExport = (photo: PhotoMetadata) =>
    patchPhoto(photo.file_hash, { rating: 5, add_tags: ['export'] }, `Moved ${photo.file_info.name} to Export Ready`)

  const columns = [
    {
      id: 'inbox',
      title: 'Inbox / Unsorted',
      icon: <Inbox size={16} color="var(--text-muted)" />,
      count: inbox.length,
      items: inbox,
      actionText: 'Promote to Pick',
      onAction: handlePromoteToPick,
    },
    {
      id: 'picks',
      title: 'Picks & Flagged',
      icon: <Star size={16} color="var(--accent-warning)" />,
      count: picks.length,
      items: picks,
      actionText: 'Ready for Export',
      onAction: handlePromoteToExport,
    },
    {
      id: 'export',
      title: 'Export Ready',
      icon: <CheckCircle size={16} color="var(--accent-success)" />,
      count: exportQueue.length,
      items: exportQueue,
    },
  ]

  return (
    <div
      style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '20px',
        padding: '24px',
        background: 'var(--bg-primary)',
        overflowY: 'auto',
      }}
    >
      {columns.map((col) => (
        <div
          key={col.id}
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Column Header */}
          <div
            style={{
              padding: '14px 18px',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'var(--bg-surface)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '0.9rem' }}>
              {col.icon}
              <span>{col.title}</span>
            </div>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                background: 'rgba(148, 163, 184, 0.2)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
              }}
            >
              {col.count}
            </span>
          </div>

          {/* Cards List */}
          <div
            style={{
              flex: 1,
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              overflowY: 'auto',
            }}
          >
            {col.items.map((item) => (
              <button
                type="button"
                className="btn-reset"
                aria-label={`Inspect ${item.file_info.name}`}
                key={item.file_hash}
                onClick={() => setInspectedHash(item.file_hash)}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: '10px',
                  display: 'flex',
                  gap: '12px',
                  cursor: 'pointer',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                }}
              >
                <img
                  src={getThumbnailUrl(item.file_hash)}
                  alt={item.file_info.name}
                  style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: 'var(--radius-sm)',
                    objectFit: 'cover',
                    flexShrink: 0,
                  }}
                  onError={swapToPlaceholder}
                />
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.file_info.name}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {item.exif.camera_make} • {((item.file_info.size_bytes) / 1048576).toFixed(1)} MB
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '4px' }}>
                    <span style={{ fontSize: '0.72rem', color: 'var(--accent-warning)' }}>
                      {item.rating ? '★'.repeat(item.rating) : ''}
                    </span>
                    {col.onAction && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          col.onAction!(item)
                        }}
                        className="btn btn-secondary"
                        style={{ padding: '2px 8px', fontSize: '0.68rem' }}
                      >
                        {col.actionText}
                      </button>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
