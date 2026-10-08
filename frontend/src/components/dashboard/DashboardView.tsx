import React from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useUiStore } from '../../stores/useUiStore'
import { useFacets } from '../../hooks/useFacets'
import { HardDrive, MapPin, Camera, Zap } from 'lucide-react'

export const DashboardView: React.FC = () => {
  const { toggleCameraFilter, setActiveView, showToast } = useUiStore(useShallow((s) => ({ toggleCameraFilter: s.toggleCameraFilter, setActiveView: s.setActiveView, showToast: s.showToast })))

  // Whole-library analytics from the server (PMO-27): the browser no longer holds every photo.
  const { stats, cameras, isos } = useFacets()
  const totalPhotos = stats.total_count
  const totalBytes = stats.total_bytes
  const geotaggedCount = stats.geotagged_count
  const avgMp = stats.avg_megapixels.toFixed(1)

  const cameraCounts: Record<string, number> = Object.fromEntries(cameras.map((c) => [c.name, c.count]))

  const isoCounts: Record<string, number> = Object.fromEntries(isos.map((i) => [`ISO ${i.name}`, i.count]))
  const withoutIso = totalPhotos - isos.reduce((sum, i) => sum + i.count, 0)
  if (withoutIso > 0) isoCounts['Auto / Other'] = withoutIso

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
              <Camera size={16} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {totalPhotos}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--accent-success)' }}>100% indexed</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>STORAGE FOOTPRINT</span>
              <HardDrive size={16} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {(totalBytes / 1048576).toFixed(1)} <span style={{ fontSize: '0.9rem' }}>MB</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Raw & WebP cache</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>GEOTAGGED GPS</span>
              <MapPin size={16} />
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
              {totalPhotos > 0 ? Math.round((geotaggedCount / totalPhotos) * 100) : 0}%
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{geotaggedCount} locations mapped</span>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>AVG RESOLUTION</span>
              <Zap size={16} />
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
                  <button
                    type="button"
                    className="btn-reset"
                    aria-label={`Filter the gallery by ${make}: ${count} photos`}
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
                          background: 'var(--text-secondary)',
                          borderRadius: '4px',
                        }}
                      />
                    </div>
                  </button>
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
                          background: 'var(--text-muted)',
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
