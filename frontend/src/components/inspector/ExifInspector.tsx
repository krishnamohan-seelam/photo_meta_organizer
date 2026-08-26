import React, { useEffect, useRef } from 'react'
import { useUiStore } from '../../stores/useUiStore'
import { patchPhotoApi } from '../../api/client'
import { Star, Flag, Copy } from 'lucide-react'

export const ExifInspector: React.FC = () => {
  const { inspectedPhoto, setInspectedPhoto, inspectorOpen, showToast } = useUiStore()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Draw simulated multi-channel RGB histogram on the canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const w = (canvas.width = canvas.offsetWidth || 300)
    const h = (canvas.height = canvas.offsetHeight || 60)
    ctx.clearRect(0, 0, w, h)

    // Red wave
    ctx.fillStyle = 'rgba(244, 63, 94, 0.4)'
    ctx.beginPath()
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 10) {
      const y = h - Math.sin(x / 20) * 20 - Math.cos(x / 40) * 15 - 10
      ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h)
    ctx.fill()

    // Green wave
    ctx.fillStyle = 'rgba(52, 211, 153, 0.4)'
    ctx.beginPath()
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 10) {
      const y = h - Math.sin((x + 30) / 25) * 25 - 8
      ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h)
    ctx.fill()

    // Blue wave
    ctx.fillStyle = 'rgba(56, 189, 248, 0.45)'
    ctx.beginPath()
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 10) {
      const y = h - Math.cos((x + 10) / 18) * 30 - 5
      ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h)
    ctx.fill()
  }, [inspectedPhoto])

  if (!inspectorOpen) return null

  if (!inspectedPhoto) {
    return (
      <aside
        className="inspector-pane"
        style={{
          width: '320px',
          background: 'var(--bg-secondary)',
          borderLeft: '1px solid var(--border-color)',
          padding: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: '0.85rem',
        }}
      >
        Select a photo to view EXIF details
      </aside>
    )
  }

  const handleRatingChange = async (newRating: number) => {
    try {
      const updated = await patchPhotoApi(inspectedPhoto.file_hash, { rating: newRating })
      setInspectedPhoto(updated)
      showToast(`Set rating to ${newRating} ★`)
    } catch {
      showToast(`Updated rating to ${newRating} ★ (local)`)
      setInspectedPhoto({ ...inspectedPhoto, rating: newRating })
    }
  }

  const handleFlagToggle = async () => {
    const nextFlag = !inspectedPhoto.flagged
    try {
      const updated = await patchPhotoApi(inspectedPhoto.file_hash, { flagged: nextFlag })
      setInspectedPhoto(updated)
      showToast(nextFlag ? '🚩 Flagged as Pick' : 'Unflagged photo')
    } catch {
      showToast(nextFlag ? '🚩 Flagged as Pick (local)' : 'Unflagged photo (local)')
      setInspectedPhoto({ ...inspectedPhoto, flagged: nextFlag })
    }
  }

  const copyRawJson = () => {
    navigator.clipboard.writeText(JSON.stringify(inspectedPhoto, null, 2))
    showToast('Copied raw JSON metadata to clipboard')
  }

  const exif = inspectedPhoto.exif

  return (
    <aside
      className="inspector-pane"
      style={{
        width: '330px',
        background: 'var(--bg-secondary)',
        borderLeft: '1px solid var(--border-color)',
        padding: '16px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px' }}>
        <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>Deep EXIF Inspector</div>
        <span className="badge badge-camera">{exif.camera_profile.toUpperCase()}</span>
      </div>

      {/* RGB Histogram */}
      <div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
          Luminance & RGB Histogram
        </div>
        <div
          style={{
            background: 'var(--box-bg)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          <canvas ref={canvasRef} style={{ width: '100%', height: '55px', borderRadius: '4px' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: 'var(--text-muted)' }}>
            <span>Shadows</span>
            <span>Midtones</span>
            <span>Highlights</span>
          </div>
        </div>
      </div>

      {/* Exposure Triangle Dials */}
      <div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
          Exposure Triangle
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700 }}>⭕ APERTURE</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
              {exif.f_stop ? `f/${exif.f_stop}` : '—'}
            </span>
          </div>
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700 }}>⏱️ SHUTTER</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
              {exif.exposure_time || '—'}
            </span>
          </div>
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700 }}>⚡ ISO SPEED</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
              {exif.iso || '—'}
            </span>
          </div>
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', padding: '8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 700 }}>🔍 FOCAL LENGTH</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-primary)' }}>
              {exif.focal_length || '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Curation Ratings & Flags */}
      <div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
          Rating & Curation
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: '4px' }}>
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                onClick={() => handleRatingChange(star)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px' }}
              >
                <Star
                  size={18}
                  fill={(inspectedPhoto.rating || 0) >= star ? 'var(--accent-warning)' : 'none'}
                  color={(inspectedPhoto.rating || 0) >= star ? 'var(--accent-warning)' : 'var(--text-muted)'}
                />
              </button>
            ))}
          </div>

          <button
            onClick={handleFlagToggle}
            className={`btn ${inspectedPhoto.flagged ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
          >
            <Flag size={13} fill={inspectedPhoto.flagged ? 'currentColor' : 'none'} />
            <span>{inspectedPhoto.flagged ? 'Flagged (P)' : 'Pick (P)'}</span>
          </button>
        </div>
      </div>

      {/* Technical Details Table */}
      <div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
          File & Technical Details
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
          <tbody>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ color: 'var(--text-muted)', padding: '6px 0', width: '38%' }}>File Name</td>
              <td style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
                {inspectedPhoto.file_info.name}
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ color: 'var(--text-muted)', padding: '6px 0' }}>Dimensions</td>
              <td style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                {inspectedPhoto.dimensions.width} x {inspectedPhoto.dimensions.height} ({((inspectedPhoto.dimensions.width * inspectedPhoto.dimensions.height) / 1000000).toFixed(1)} MP)
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ color: 'var(--text-muted)', padding: '6px 0' }}>File Size</td>
              <td style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                {(inspectedPhoto.file_info.size_bytes / 1048576).toFixed(1)} MB
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ color: 'var(--text-muted)', padding: '6px 0' }}>Camera</td>
              <td style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                {exif.camera_make} {exif.camera_model}
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <td style={{ color: 'var(--text-muted)', padding: '6px 0' }}>SHA-256 Hash</td>
              <td style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', wordBreak: 'break-all' }}>
                {inspectedPhoto.file_hash}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Raw JSON viewer */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Raw JSON Payload
          </span>
          <button onClick={copyRawJson} style={{ background: 'transparent', border: 'none', color: 'var(--accent-primary)', fontSize: '0.72rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '3px' }}>
            <Copy size={11} />
            <span>Copy</span>
          </button>
        </div>
        <pre
          style={{
            background: 'var(--box-bg)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.68rem',
            color: 'var(--text-secondary)',
            maxHeight: '140px',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
          }}
        >
          {JSON.stringify(inspectedPhoto, null, 2)}
        </pre>
      </div>
    </aside>
  )
}
