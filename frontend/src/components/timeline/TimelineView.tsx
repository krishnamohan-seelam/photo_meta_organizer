import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl } from '../../api/client'
import { Calendar } from 'lucide-react'

interface TimelineViewProps {
  photos: PhotoMetadata[]
}

export const TimelineView: React.FC<TimelineViewProps> = ({ photos }) => {
  const { filterTimeframe, setTimeframeFilter, setLightboxIndex } = useUiStore()

  // Group photos by Month / Year
  const groups: Record<string, PhotoMetadata[]> = {}
  photos.forEach((p) => {
    const d = p.exif.captured_at ? new Date(p.exif.captured_at) : new Date(p.added_at)
    const monthYear = d.toLocaleString('default', { month: 'long', year: 'numeric' })
    if (!groups[monthYear]) groups[monthYear] = []
    groups[monthYear].push(p)
  })

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
      {/* Top Scrubber */}
      <div
        style={{
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          position: 'sticky',
          top: 0,
          zIndex: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)' }}>
          <Calendar size={15} />
          <span>TIMELINE</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {['all', '2026', '2025', '2024'].map((yr) => (
            <button
              key={yr}
              onClick={() => setTimeframeFilter(yr)}
              className={`btn ${filterTimeframe === yr ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '4px 12px', fontSize: '0.75rem', borderRadius: 'var(--radius-full)' }}
            >
              {yr === 'all' ? 'All Years' : yr}
            </button>
          ))}
        </div>
      </div>

      {/* Grouped Sections */}
      <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '28px' }}>
        {Object.entries(groups).map(([month, items]) => (
          <div key={month} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>{month}</h3>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{items.length} photos</span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
                gap: '12px',
              }}
            >
              {items.map((item) => (
                <div
                  key={item.file_hash}
                  onClick={() => {
                    const idx = photos.findIndex((p) => p.file_hash === item.file_hash)
                    if (idx >= 0) setLightboxIndex(idx)
                  }}
                  style={{
                    aspectRatio: '1',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                    position: 'relative',
                    cursor: 'pointer',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <img
                    src={getThumbnailUrl(item.file_hash)}
                    alt={item.file_info.name}
                    loading="lazy"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      e.currentTarget.src =
                        'https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=600&auto=format&fit=crop&q=80'
                    }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: 'linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 60%)',
                      opacity: 0,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'flex-end',
                      padding: '10px',
                      color: '#fff',
                      transition: 'opacity 0.2s',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
                    onMouseLeave={(e) => (e.currentTarget.style.opacity = '0')}
                  >
                    <div style={{ fontWeight: 600, fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.file_info.name}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#e2e8f0' }}>
                      {item.exif.camera_make} • {'★'.repeat(item.rating || 4)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
