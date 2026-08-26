import React from 'react'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { HardDrive, MapPin, Camera, Zap } from 'lucide-react'

interface DashboardViewProps {
  photos: PhotoMetadata[]
}

export const DashboardView: React.FC<DashboardViewProps> = ({ photos }) => {
  const { toggleCameraFilter, setActiveView, showToast } = useUiStore()

  // Compute analytics
  const totalPhotos = photos.length
  const totalBytes = photos.reduce((acc, p) => acc + p.file_info.size_bytes, 0)
  const geotaggedCount = photos.filter((p) => p.exif.location && p.exif.location.latitude).length
  const avgMp =
    totalPhotos > 0
      ? (
          photos.reduce((acc, p) => acc + (p.dimensions.width * p.dimensions.height) / 1000000, 0) /
          totalPhotos
        ).toFixed(1)
      : '0.0'

  // Camera make counts
  const cameraCounts: Record<string, number> = {}
  photos.forEach((p) => {
    const make = p.exif.camera_make || 'Unknown'
    cameraCounts[make] = (cameraCounts[make] || 0) + 1
  })

  // ISO speed counts
  const isoCounts: Record<string, number> = {}
  photos.forEach((p) => {
    const iso = p.exif.iso ? `ISO ${p.exif.iso}` : 'Auto / Other'
    isoCounts[iso] = (isoCounts[iso] || 0) + 1
  })

  return (
    <div style={{ flex: 1, padding: '28px', background: 'var(--bg-primary)', overflowY: 'auto' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Header */}
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Library & EXIF Analytics Dashboard
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Comprehensive breakdown of your photo repository, camera gear, and exposure telemetry.
          </p>
        </div>

        {/* 4 KPI Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>TOTAL PHOTOS</span>
              <Camera size={16} color="var(--accent-primary)" />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {totalPhotos}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--accent-success)' }}>100% indexed</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>STORAGE FOOTPRINT</span>
              <HardDrive size={16} color="var(--accent-secondary)" />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {(totalBytes / 1048576).toFixed(1)} <span style={{ fontSize: '0.9rem' }}>MB</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Raw & WebP cache</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>GEOTAGGED GPS</span>
              <MapPin size={16} color="var(--accent-warning)" />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {totalPhotos > 0 ? Math.round((geotaggedCount / totalPhotos) * 100) : 0}%
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{geotaggedCount} locations mapped</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>AVG RESOLUTION</span>
              <Zap size={16} color="var(--accent-success)" />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {avgMp} <span style={{ fontSize: '0.9rem' }}>MP</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Sensor fidelity</span>
          </div>
        </div>

        {/* Charts Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Camera Make Distribution */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>Camera Make Distribution</h3>
              <span style={{ fontSize: '0.72rem', color: 'var(--accent-primary)' }}>Click bar to filter</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {Object.entries(cameraCounts).map(([make, count]) => {
                const pct = totalPhotos > 0 ? Math.round((count / totalPhotos) * 100) : 0
                return (
                  <div
                    key={make}
                    onClick={() => {
                      toggleCameraFilter(make)
                      setActiveView('studio')
                      showToast(`Filtered gallery by ${make}`)
                    }}
                    style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '4px' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                      <span style={{ fontWeight: 600 }}>{make}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{count} ({pct}%)</span>
                    </div>
                    <div style={{ height: '8px', background: 'var(--bg-surface)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${pct}%`,
                          background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
                          borderRadius: '4px',
                        }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* ISO Speed Breakdown */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700 }}>ISO Sensitivity Breakdown</h3>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Exposure telemetry</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {Object.entries(isoCounts).map(([iso, count]) => {
                const pct = totalPhotos > 0 ? Math.round((count / totalPhotos) * 100) : 0
                return (
                  <div key={iso} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                      <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{iso}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{count} ({pct}%)</span>
                    </div>
                    <div style={{ height: '8px', background: 'var(--bg-surface)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${pct}%`,
                          background: 'var(--accent-warning)',
                          borderRadius: '4px',
                        }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
