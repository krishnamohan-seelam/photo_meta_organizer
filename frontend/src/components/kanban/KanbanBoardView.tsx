import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl, patchPhotoApi } from '../../api/client'
import { Inbox, Star, CheckCircle } from 'lucide-react'

interface KanbanBoardViewProps {
  photos: PhotoMetadata[]
  onRefresh?: () => void
}

export const KanbanBoardView: React.FC<KanbanBoardViewProps> = ({ photos, onRefresh }) => {
  const { setInspectedPhoto, showToast } = useUiStore()

  // Columns:
  // 1. Inbox (unrated or rating <= 2)
  // 2. Picks & Flagged (flagged or rating >= 4)
  // 3. Export Ready (rating === 5 or tagged 'export')
  const inbox = photos.filter((p) => !p.flagged && (p.rating || 0) < 4)
  const picks = photos.filter((p) => p.flagged || (p.rating || 0) === 4)
  const exportQueue = photos.filter((p) => (p.rating || 0) === 5 || p.labels.includes('export'))

  const handlePromoteToPick = async (photo: PhotoMetadata) => {
    try {
      await patchPhotoApi(photo.file_hash, { flagged: true, rating: 4 })
      showToast(`Moved ${photo.file_info.name} to Picks`)
      if (onRefresh) onRefresh()
    } catch {
      showToast(`Moved ${photo.file_info.name} to Picks (local)`)
    }
  }

  const handlePromoteToExport = async (photo: PhotoMetadata) => {
    try {
      await patchPhotoApi(photo.file_hash, { rating: 5, add_tags: ['export'] })
      showToast(`Moved ${photo.file_info.name} to Export Ready`)
      if (onRefresh) onRefresh()
    } catch {
      showToast(`Moved ${photo.file_info.name} to Export Ready (local)`)
    }
  }

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
              <div
                key={item.file_hash}
                onClick={() => setInspectedPhoto(item)}
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
                  onError={(e) => {
                    e.currentTarget.src =
                      'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=200&auto=format&fit=crop&q=80'
                  }}
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
                      {'★'.repeat(item.rating || 3)}
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
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
