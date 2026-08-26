import React, { useEffect, useState } from 'react'
import type { PhotoMetadata } from './types/metadata'
import { fetchPhotos } from './api/client'
import { useUiStore } from './stores/useUiStore'
import { AppHeader } from './components/header/AppHeader'
import { CommandPalette } from './components/header/CommandPalette'
import { FilterSidebar } from './components/filters/FilterSidebar'
import { PhotoGallery } from './components/gallery/PhotoGallery'
import { ExifInspector } from './components/inspector/ExifInspector'
import { SelectionDock } from './components/collections/SelectionDock'
import { TimelineView } from './components/timeline/TimelineView'
import { MapExplorerView } from './components/maps/MapExplorerView'
import { KanbanBoardView } from './components/kanban/KanbanBoardView'
import { DashboardView } from './components/dashboard/DashboardView'
import { LightboxModal } from './components/lightbox/LightboxModal'
import { CheckCircle2, EyeOff } from 'lucide-react'

// Demo Fallback Data for seamless out-of-the-box experience
const SAMPLE_PHOTOS: PhotoMetadata[] = [
  {
    file_hash: '3f8b9a1c4d2e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4',
    file_info: {
      name: 'DSC04928_Tokyo_Tower_Sunset.ARW',
      path: '/media/raw/DSC04928_Tokyo_Tower_Sunset.ARW',
      size_bytes: 25345678,
      mime_type: 'image/x-sony-arw',
    },
    dimensions: { width: 7008, height: 4672 },
    exif: {
      camera_make: 'Sony',
      camera_model: 'ILCE-7M4 (A7 IV)',
      f_stop: 2.8,
      exposure_time: '1/250s',
      iso: 400,
      focal_length: '35.0 mm',
      captured_at: '2026-05-14T18:42:10Z',
      camera_profile: 'raw',
      location: { latitude: 35.6586, longitude: 139.7454, datum: 'WGS84' },
      flash_fired: false,
      orientation: 1,
      raw_tags: { LensModel: 'FE 35mm F1.4 GM', WhiteBalance: 'Auto' },
    },
    labels: ['travel', 'japan', 'architecture', 'sunset'],
    rating: 5,
    flagged: true,
    added_at: '2026-05-15T09:00:00Z',
  },
  {
    file_hash: '9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b',
    file_info: {
      name: 'IMG_8392_Kyoto_Bamboo_Path.CR3',
      path: '/media/raw/IMG_8392_Kyoto_Bamboo_Path.CR3',
      size_bytes: 38920140,
      mime_type: 'image/x-canon-cr3',
    },
    dimensions: { width: 8192, height: 5464 },
    exif: {
      camera_make: 'Canon',
      camera_model: 'EOS R5',
      f_stop: 4.0,
      exposure_time: '1/125s',
      iso: 800,
      focal_length: '24.0 mm',
      captured_at: '2026-05-16T08:15:30Z',
      camera_profile: 'raw',
      location: { latitude: 35.0167, longitude: 135.6713, datum: 'WGS84' },
      flash_fired: false,
      orientation: 1,
      raw_tags: { LensModel: 'RF 24-70mm F2.8 L IS USM' },
    },
    labels: ['travel', 'nature', 'landscape', 'green'],
    rating: 4,
    flagged: true,
    added_at: '2026-05-17T11:20:00Z',
  },
  {
    file_hash: '1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d',
    file_info: {
      name: 'iPhone_15Pro_Shibuya_Night.HEIC',
      path: '/media/raw/iPhone_15Pro_Shibuya_Night.HEIC',
      size_bytes: 4892100,
      mime_type: 'image/heic',
    },
    dimensions: { width: 4032, height: 3024 },
    exif: {
      camera_make: 'Apple',
      camera_model: 'iPhone 15 Pro',
      f_stop: 1.78,
      exposure_time: '1/40s',
      iso: 1250,
      focal_length: '24.0 mm',
      captured_at: '2026-05-16T22:30:15Z',
      camera_profile: 'standard',
      location: { latitude: 35.6595, longitude: 139.7005, datum: 'WGS84' },
      flash_fired: false,
      orientation: 1,
      raw_tags: { LensModel: 'iPhone 15 Pro back camera 6.86mm f/1.78' },
    },
    labels: ['travel', 'urban', 'night', 'street'],
    rating: 4,
    flagged: false,
    added_at: '2026-05-17T14:00:00Z',
  },
  {
    file_hash: '7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f',
    file_info: {
      name: '_DSC9102_Fuji_Sunrise.NEF',
      path: '/media/raw/_DSC9102_Fuji_Sunrise.NEF',
      size_bytes: 45210980,
      mime_type: 'image/x-nikon-nef',
    },
    dimensions: { width: 8256, height: 5504 },
    exif: {
      camera_make: 'Nikon',
      camera_model: 'Z8',
      f_stop: 8.0,
      exposure_time: '1/500s',
      iso: 100,
      focal_length: '70.0 mm',
      captured_at: '2026-05-18T05:10:00Z',
      camera_profile: 'raw',
      location: { latitude: 35.3606, longitude: 138.7274, datum: 'WGS84' },
      flash_fired: false,
      orientation: 1,
      raw_tags: { LensModel: 'NIKKOR Z 24-70mm f/2.8 S' },
    },
    labels: ['travel', 'landscape', 'mountain', 'sunrise'],
    rating: 5,
    flagged: true,
    added_at: '2026-05-19T08:00:00Z',
  },
]

export const App: React.FC = () => {
  const {
    theme,
    activeView,
    lightsOut,
    toggleLightsOut,
    filterCameras,
    filterTags,
    filterCollection,
    filterTimeframe,
    searchQuery,
    inspectedPhoto,
    setInspectedPhoto,
    toastMessage,
  } = useUiStore()

  const [photos, setPhotos] = useState<PhotoMetadata[]>(SAMPLE_PHOTOS)
  const [isLoading, setIsLoading] = useState(false)

  // Fetch real photos from FastAPI backend, fallback to demo dataset if empty
  const loadData = async () => {
    try {
      setIsLoading(true)
      const data = await fetchPhotos(1, 100)
      if (data && data.items && data.items.length > 0) {
        setPhotos(data.items)
        if (!inspectedPhoto) {
          setInspectedPhoto(data.items[0])
        }
      } else {
        if (!inspectedPhoto) {
          setInspectedPhoto(SAMPLE_PHOTOS[0])
        }
      }
    } catch {
      // Fallback
      if (!inspectedPhoto) {
        setInspectedPhoto(SAMPLE_PHOTOS[0])
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    loadData()
  }, [])

  // Keyboard shortcut listener for 'L' (Lights Out)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key.toLowerCase() === 'l') {
        toggleLightsOut()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggleLightsOut])

  // Filter photos based on store filter criteria
  const filteredPhotos = photos.filter((p) => {
    if (filterCameras.length > 0 && !filterCameras.includes(p.exif.camera_make || 'Unknown')) {
      return false
    }
    if (filterTags.length > 0 && !filterTags.some((t) => p.labels.includes(t))) {
      return false
    }
    if (filterCollection === 'Favorites' && !p.flagged) {
      return false
    }
    if (filterTimeframe !== 'all') {
      const yr = (p.exif.captured_at || p.added_at).substring(0, 4)
      if (yr !== filterTimeframe) return false
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchName = p.file_info.name.toLowerCase().includes(q)
      const matchMake = (p.exif.camera_make || '').toLowerCase().includes(q)
      const matchModel = (p.exif.camera_model || '').toLowerCase().includes(q)
      const matchTag = p.labels.some((t) => t.toLowerCase().includes(q))
      if (!matchName && !matchMake && !matchModel && !matchTag) return false
    }
    return true
  })

  return (
    <div
      className={lightsOut ? 'lights-out' : ''}
      style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}
    >
      {/* Lights out indicator badge */}
      {lightsOut && (
        <div className="lights-out-indicator">
          <EyeOff size={14} />
          <span>Lights Out Active (Press L or click Dim to restore)</span>
        </div>
      )}

      {/* App Header */}
      <AppHeader />

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        {activeView === 'studio' && (
          <>
            <FilterSidebar />
            <PhotoGallery photos={filteredPhotos} isLoading={isLoading} />
            <ExifInspector />
          </>
        )}

        {activeView === 'timeline' && <TimelineView photos={filteredPhotos} />}
        {activeView === 'map' && <MapExplorerView photos={filteredPhotos} />}
        {activeView === 'kanban' && <KanbanBoardView photos={filteredPhotos} onRefresh={loadData} />}
        {activeView === 'analytics' && <DashboardView photos={photos} />}
      </div>

      {/* Floating Selection Dock */}
      <SelectionDock photos={photos} onRefresh={loadData} />

      {/* Modals & Overlays */}
      <CommandPalette />
      <LightboxModal photos={filteredPhotos} />

      {/* Toast notifications */}
      {toastMessage && (
        <div className="toast-notice">
          <CheckCircle2 size={16} color="var(--accent-primary)" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  )
}
export default App
