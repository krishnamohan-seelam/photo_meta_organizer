import React, { useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl } from '../../api/client'
import { useCuration } from '../../hooks/usePhotoMutations'
import { swapToPlaceholder } from '../../utils/placeholder'
import { X, ChevronLeft, ChevronRight, Flag } from 'lucide-react'

interface LightboxModalProps {
  photos: PhotoMetadata[]
}

export const LightboxModal: React.FC<LightboxModalProps> = ({ photos }) => {
  const { lightboxIndex, setLightboxIndex } = useUiStore(useShallow((s) => ({ lightboxIndex: s.lightboxIndex, setLightboxIndex: s.setLightboxIndex })))
  const { patchPhoto } = useCuration()

  const currentPhoto = lightboxIndex !== null && photos[lightboxIndex] ? photos[lightboxIndex] : null

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (lightboxIndex === null || !currentPhoto) return

      if (e.key === 'Escape') {
        setLightboxIndex(null)
      } else if (e.key === 'ArrowRight') {
        setLightboxIndex((lightboxIndex + 1) % photos.length)
      } else if (e.key === 'ArrowLeft') {
        setLightboxIndex((lightboxIndex - 1 + photos.length) % photos.length)
      } else if (e.key.toLowerCase() === 'p') {
        // Toggle Flag Pick: the cache updates at once and rolls back with an error toast if the save fails
        const nextFlag = !currentPhoto.flagged
        void patchPhoto(currentPhoto.file_hash, { flagged: nextFlag }, nextFlag ? '🚩 Flagged as Pick' : 'Unflagged photo')
      } else if (['1', '2', '3', '4', '5'].includes(e.key)) {
        const rating = parseInt(e.key)
        void patchPhoto(currentPhoto.file_hash, { rating }, `Rated ${rating} ★`)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [lightboxIndex, currentPhoto, photos, setLightboxIndex, patchPhoto])

  if (lightboxIndex === null || !currentPhoto) return null

  const exif = currentPhoto.exif

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(5, 7, 12, 0.96)',
        backdropFilter: 'blur(16px)',
        zIndex: 99999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px',
      }}
      onClick={() => setLightboxIndex(null)}
    >
      {/* Top HUD Bar */}
      <div
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: '#fff',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>{currentPhoto.file_info.name}</span>
          <span className="badge badge-camera">{exif.camera_make} {exif.camera_model}</span>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            {lightboxIndex + 1} of {photos.length}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            className="btn btn-secondary"
            onClick={() => {
              const next = !currentPhoto.flagged
              void patchPhoto(currentPhoto.file_hash, { flagged: next }, next ? '🚩 Flagged as Pick' : 'Unflagged photo')
            }}
            style={{ color: currentPhoto.flagged ? 'var(--accent-warning)' : '#fff' }}
          >
            <Flag size={15} fill={currentPhoto.flagged ? 'currentColor' : 'none'} />
            <span>{currentPhoto.flagged ? 'Flagged (P)' : 'Pick (P)'}</span>
          </button>

          <button className="btn btn-secondary" onClick={() => setLightboxIndex(null)}>
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Main Image Stage & Nav Chevrons */}
      <div
        style={{
          position: 'relative',
          flex: 1,
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          padding: '20px 0',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Left Chevron */}
        <button
          onClick={() => setLightboxIndex((lightboxIndex - 1 + photos.length) % photos.length)}
          style={{
            position: 'absolute',
            left: '20px',
            background: 'rgba(255, 255, 255, 0.1)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            borderRadius: '50%',
            width: '44px',
            height: '44px',
            color: '#fff',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            transition: 'background 0.2s',
          }}
        >
          <ChevronLeft size={24} />
        </button>

        {/* Center Image */}
        <img
          src={getThumbnailUrl(currentPhoto.file_hash, 1200, 1200)}
          alt={currentPhoto.file_info.name}
          style={{
            maxHeight: '70vh',
            maxWidth: '85vw',
            objectFit: 'contain',
            borderRadius: 'var(--radius-md)',
            boxShadow: '0 20px 50px rgba(0,0,0,0.8)',
          }}
          onError={swapToPlaceholder}
        />

        {/* Right Chevron */}
        <button
          onClick={() => setLightboxIndex((lightboxIndex + 1) % photos.length)}
          style={{
            position: 'absolute',
            right: '20px',
            background: 'rgba(255, 255, 255, 0.1)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            borderRadius: '50%',
            width: '44px',
            height: '44px',
            color: '#fff',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            transition: 'background 0.2s',
          }}
        >
          <ChevronRight size={24} />
        </button>

        {/* Overlay Telemetry HUD */}
        <div
          style={{
            position: 'absolute',
            bottom: '30px',
            background: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: 'var(--radius-full)',
            padding: '8px 24px',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            color: '#fff',
            fontSize: '0.82rem',
            fontFamily: 'var(--font-mono)',
          }}
        >
          <span>{exif.f_stop ? `f/${exif.f_stop}` : 'f/—'}</span>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>{exif.exposure_time || '—'}</span>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>ISO {exif.iso || '—'}</span>
          <span style={{ opacity: 0.4 }}>|</span>
          <span>{exif.focal_length || '—'}</span>
        </div>
      </div>

      {/* Bottom Filmstrip */}
      <div
        style={{
          width: '100%',
          maxWidth: '800px',
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          padding: '6px',
          justifyContent: 'center',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {photos.map((p, idx) => (
          <img
            key={p.file_hash}
            src={getThumbnailUrl(p.file_hash, 100, 100)}
            alt={p.file_info.name}
            onClick={() => setLightboxIndex(idx)}
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '4px',
              objectFit: 'cover',
              cursor: 'pointer',
              opacity: idx === lightboxIndex ? 1 : 0.4,
              border: idx === lightboxIndex ? '2px solid var(--accent-primary)' : '1px solid transparent',
              transition: 'all 0.15s ease',
            }}
            onError={swapToPlaceholder}
          />
        ))}
      </div>
    </div>
  )
}
