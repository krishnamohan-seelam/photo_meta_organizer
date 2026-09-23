import React, { useEffect, useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { errorMessage } from './api/client'
import { usePhotos } from './hooks/usePhotos'
import { useScanFolder } from './hooks/useScanFolder'
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
import { EmptyLibraryState, ErrorState, LoadingState, StaleBanner } from './components/states/LibraryStates'
import { AlertCircle, CheckCircle2, EyeOff } from 'lucide-react'
import type { PhotoMetadata } from './types/metadata'

const NO_PHOTOS: PhotoMetadata[] = []

export const App: React.FC = () => {
  const { theme, activeView, lightsOut, toggleLightsOut, filterCameras, filterTags, filterCollection, filterTimeframe, searchQuery, inspectedHash, setInspectedHash, toastMessage, toastKind } = useUiStore(useShallow((s) => ({ theme: s.theme, activeView: s.activeView, lightsOut: s.lightsOut, toggleLightsOut: s.toggleLightsOut, filterCameras: s.filterCameras, filterTags: s.filterTags, filterCollection: s.filterCollection, filterTimeframe: s.filterTimeframe, searchQuery: s.searchQuery, inspectedHash: s.inspectedHash, setInspectedHash: s.setInspectedHash, toastMessage: s.toastMessage, toastKind: s.toastKind })))

  // The library lives in the react-query cache: every view and every edit goes through it.
  const { data, isPending, isError, error, refetch, isFetching } = usePhotos()
  const photos = data ?? NO_PHOTOS
  const { scan, isScanning } = useScanFolder()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Open the inspector on the first photo once there is one. It is keyed by hash, so reloads keep the selection.
  useEffect(() => {
    if (!inspectedHash && photos.length > 0) setInspectedHash(photos[0].file_hash)
  }, [inspectedHash, photos, setInspectedHash])

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

  // Filter photos based on store filter criteria. Memoised: with thousands of photos this must not
  // re-run on unrelated store changes (toasts, slider drags, the lightbox opening).
  const filteredPhotos = useMemo(() => photos.filter((p) => {
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
  }), [photos, filterCameras, filterTags, filterCollection, filterTimeframe, searchQuery])

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

      {/* A failed refresh must not hide photos we already have, but must not pass them off as current */}
      {isError && data && <StaleBanner message={errorMessage(error)} onRetry={() => refetch()} retrying={isFetching} />}

      {/* Main Content Area: loading, error and empty are distinct states, never a stand-in library */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        {isPending ? (
          <LoadingState />
        ) : !data ? (
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} retrying={isFetching} />
        ) : photos.length === 0 ? (
          <EmptyLibraryState onScan={scan} scanning={isScanning} />
        ) : (
          <>
            {activeView === 'studio' && (
              <>
                <FilterSidebar />
                <PhotoGallery photos={filteredPhotos} />
                <ExifInspector />
              </>
            )}

            {activeView === 'timeline' && <TimelineView photos={filteredPhotos} />}
            {activeView === 'map' && <MapExplorerView photos={filteredPhotos} />}
            {activeView === 'kanban' && <KanbanBoardView photos={filteredPhotos} />}
            {activeView === 'analytics' && <DashboardView photos={photos} />}
          </>
        )}
      </div>

      {/* Floating Selection Dock */}
      <SelectionDock photos={photos} />

      {/* Modals & Overlays */}
      <CommandPalette />
      <LightboxModal photos={filteredPhotos} />

      {/* Toast notifications */}
      {toastMessage && (
        <div className={`toast-notice${toastKind === 'error' ? ' toast-error' : ''}`} role={toastKind === 'error' ? 'alert' : 'status'}>
          {toastKind === 'error' ? (
            <AlertCircle size={16} color="var(--accent-danger)" />
          ) : (
            <CheckCircle2 size={16} color="var(--accent-primary)" />
          )}
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  )
}
export default App
