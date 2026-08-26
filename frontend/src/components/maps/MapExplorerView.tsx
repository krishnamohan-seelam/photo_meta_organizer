import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { MapPin, Sliders } from 'lucide-react'

interface MapExplorerViewProps {
  photos: PhotoMetadata[]
}

export const MapExplorerView: React.FC<MapExplorerViewProps> = ({ photos }) => {
  const { radiusKm, setRadiusKm, setInspectedPhoto, setLightboxIndex, showToast } = useUiStore()

  // Find photos with GPS coordinates
  const geoPhotos = photos.filter((p) => p.exif.location && p.exif.location.latitude)

  const clusters = [
    { city: 'Tokyo, Japan', lat: 35.6762, lon: 139.6503, count: 12, top: '42%', left: '78%' },
    { city: 'Kyoto, Japan', lat: 35.0116, lon: 135.7681, count: 6, top: '46%', left: '76%' },
    { city: 'San Francisco, USA', lat: 37.7749, lon: -122.4194, count: 4, top: '38%', left: '22%' },
    { city: 'London, UK', lat: 51.5074, lon: -0.1278, count: 2, top: '30%', left: '48%' },
  ]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {/* Top Map Filter Controls */}
      <div
        style={{
          position: 'absolute',
          top: '20px',
          left: '20px',
          zIndex: 30,
          background: 'var(--header-bg)',
          backdropFilter: 'blur(12px)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 18px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem' }}>
          <MapPin size={16} color="var(--accent-primary)" />
          <span>Geospatial Search</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <Sliders size={14} />
          <span>Radius:</span>
          <input
            type="range"
            min="5"
            max="100"
            value={radiusKm}
            onChange={(e) => setRadiusKm(parseInt(e.target.value))}
            style={{ width: '90px', accentColor: 'var(--accent-primary)' }}
          />
          <span style={{ color: 'var(--accent-primary)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
            {radiusKm} km
          </span>
        </div>

        <div className="badge badge-camera">
          {geoPhotos.length} geotagged photos
        </div>
      </div>

      {/* Map Graphic Canvas */}
      <div
        style={{
          flex: 1,
          background: '#0a0f1d',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* World Map SVG Vector */}
        <svg
          viewBox="0 0 1000 500"
          style={{ width: '100%', height: '100%', opacity: 0.35, filter: 'drop-shadow(0 0 10px rgba(56,189,248,0.2))' }}
        >
          <path
            d="M150,150 Q180,100 260,110 T350,220 T200,340 Z M420,120 Q500,80 580,130 T600,280 T480,260 Z M650,120 Q780,100 860,180 T800,340 T670,260 Z M750,380 Q850,360 880,440 T760,450 Z"
            fill="var(--bg-surface)"
            stroke="var(--accent-primary)"
            strokeWidth="1.5"
          />
        </svg>

        {/* GPS Cluster Markers */}
        {clusters.map((c) => (
          <div
            key={c.city}
            onClick={() => {
              showToast(`Focused on ${c.city} (${c.count} photos within ${radiusKm}km)`)
              const matched = geoPhotos[0]
              if (matched) {
                setInspectedPhoto(matched)
                setLightboxIndex(0)
              }
            }}
            style={{
              position: 'absolute',
              top: c.top,
              left: c.left,
              transform: 'translate(-50%, -50%)',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              zIndex: 10,
            }}
          >
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '50%',
                background: 'rgba(56, 189, 248, 0.25)',
                border: '2px solid var(--accent-primary)',
                boxShadow: '0 0 15px var(--accent-glow)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontWeight: 700,
                fontSize: '0.85rem',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {c.count}
            </div>
            <div
              style={{
                marginTop: '4px',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.72rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
                boxShadow: 'var(--shadow-lg)',
              }}
            >
              {c.city}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
