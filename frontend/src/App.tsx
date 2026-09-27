import React, { useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { errorMessage } from './api/client'
import { isDemoMode, usePhotoSearch } from './hooks/usePhotos'
import { useFacetsQuery } from './hooks/useFacets'
import { useJobCompletionNotices, useJobs } from './hooks/useJobs'
import { useUiStore } from './stores/useUiStore'
import { shouldIgnoreHotkey } from './utils/hotkeys'
import { AppHeader } from './components/header/AppHeader'
import { CommandPalette } from './components/header/CommandPalette'
import { FolderJobDialog } from './components/jobs/FolderJobDialog'
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

export const App: React.FC = () => {
  const { theme, activeView, lightsOut, toggleLightsOut, inspectedHash, setInspectedHash, toastMessage, toastKind } = useUiStore(useShallow((s) => ({ theme: s.theme, activeView: s.activeView, lightsOut: s.lightsOut, toggleLightsOut: s.toggleLightsOut, inspectedHash: s.inspectedHash, setInspectedHash: s.setInspectedHash, toastMessage: s.toastMessage, toastKind: s.toastKind })))

  // The server filters, sorts and pages the library (PMO-27); views read the loaded pages from one cache entry.
  const { data, photos, isPending, isError, error, refetch, isFetching } = usePhotoSearch()
  // Whole-library totals tell an empty library apart from a filter that matches nothing.
  const facets = useFacetsQuery()
  const libraryIsEmpty = facets.data?.stats.total_count === 0 && !isDemoMode()
  const { activeJob } = useJobs()
  const setJobDialog = useUiStore((s) => s.setJobDialog)
  useJobCompletionNotices()

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
      // Not while typing, not with modifiers (Ctrl+L is the address bar), not inside a dialog.
      if (shouldIgnoreHotkey(e) || document.querySelector('[aria-modal="true"]')) return
      if (e.key.toLowerCase() === 'l') {
        toggleLightsOut()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggleLightsOut])

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
        ) : libraryIsEmpty ? (
          <EmptyLibraryState onScan={() => setJobDialog('index')} scanning={activeJob !== null} />
        ) : (
          <>
            {activeView === 'studio' && (
              <>
                <FilterSidebar />
                <PhotoGallery />
                <ExifInspector />
              </>
            )}

            {activeView === 'timeline' && <TimelineView />}
            {activeView === 'map' && <MapExplorerView />}
            {activeView === 'kanban' && <KanbanBoardView />}
            {activeView === 'analytics' && <DashboardView />}
          </>
        )}
      </div>

      {/* Floating Selection Dock */}
      <SelectionDock />

      {/* Modals & Overlays */}
      <CommandPalette />
      <FolderJobDialog />
      <LightboxModal />

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
