import React, { Suspense, lazy, useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { errorMessage } from './api/client'
import { isDemoMode, usePhotoSearch } from './hooks/usePhotos'
import { useFacetsQuery } from './hooks/useFacets'
import { useJobCompletionNotices, useJobs } from './hooks/useJobs'
import { useGlobalHotkeys } from './hooks/useGlobalHotkeys'
import { useUiStore } from './stores/useUiStore'
import { NavRail } from './components/shell/NavRail'
import { TopBar } from './components/header/TopBar'
import { CommandPalette } from './components/header/CommandPalette'
import { ShortcutsOverlay } from './components/header/ShortcutsOverlay'
import { FolderJobDialog } from './components/jobs/FolderJobDialog'
import { AiSetupDialog } from './components/ai/AiSetupDialog'
import { LibraryPanel } from './components/filters/LibraryPanel'
import { LibraryView } from './components/gallery/LibraryView'
import { ExifInspector } from './components/inspector/ExifInspector'
import { SelectionDock } from './components/collections/SelectionDock'
import { TimelineView } from './components/timeline/TimelineView'
import { KanbanBoardView } from './components/kanban/KanbanBoardView'
import { DashboardView } from './components/dashboard/DashboardView'
import { LightboxModal } from './components/lightbox/LightboxModal'
import { EmptyLibraryState, ErrorState, LoadingState, StaleBanner } from './components/states/LibraryStates'
import { AlertCircle, CheckCircle2, EyeOff } from 'lucide-react'

// Leaflet and the country outlines are only needed on the Map view.
const MapExplorerView = lazy(() => import('./components/maps/MapExplorerView').then((m) => ({ default: m.MapExplorerView })))

export const App: React.FC = () => {
  const { theme, activeView, lightsOut, inspectedHash, setInspectedHash, toastMessage, toastKind } = useUiStore(useShallow((s) => ({ theme: s.theme, activeView: s.activeView, lightsOut: s.lightsOut, inspectedHash: s.inspectedHash, setInspectedHash: s.setInspectedHash, toastMessage: s.toastMessage, toastKind: s.toastKind })))

  // The server filters, sorts and pages the library (PMO-27); views read the loaded pages from one cache entry.
  const { data, photos, isPending, isError, error, refetch, isFetching } = usePhotoSearch()
  // Whole-library totals tell an empty library apart from a filter that matches nothing.
  const facets = useFacetsQuery()
  const libraryIsEmpty = facets.data?.stats.total_count === 0 && !isDemoMode()
  const { activeJob } = useJobs()
  const setJobDialog = useUiStore((s) => s.setJobDialog)
  useJobCompletionNotices()
  useGlobalHotkeys()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Open the inspector on the first photo once there is one. It is keyed by hash, so reloads keep the selection.
  useEffect(() => {
    if (!inspectedHash && photos.length > 0) setInspectedHash(photos[0].file_hash)
  }, [inspectedHash, photos, setInspectedHash])

  return (
    <div className={`app-shell${lightsOut ? ' lights-out' : ''}`}>
      {lightsOut && (
        <div className="lights-out-indicator" role="status">
          <EyeOff size={14} />
          <span>Lights Out · press L to restore</span>
        </div>
      )}

      <NavRail />

      <div className="app-main">
        <TopBar />

        {/* A failed refresh must not hide photos we already have, but must not pass them off as current */}
        {isError && data && <StaleBanner message={errorMessage(error)} onRetry={() => refetch()} retrying={isFetching} />}

        {/* Loading, error and empty are distinct states, never a stand-in library */}
        <div className="app-body">
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
                  <LibraryPanel />
                  <LibraryView />
                  <ExifInspector />
                </>
              )}

              {activeView === 'timeline' && <TimelineView />}
              {activeView === 'map' && (
                <>
                  <Suspense fallback={<LoadingState />}>
                    <MapExplorerView />
                  </Suspense>
                  <ExifInspector />
                </>
              )}
              {activeView === 'kanban' && <KanbanBoardView />}
              {activeView === 'analytics' && <DashboardView />}
            </>
          )}
        </div>
      </div>

      <SelectionDock />

      <CommandPalette />
      <ShortcutsOverlay />
      <FolderJobDialog />
      <AiSetupDialog />
      <LightboxModal />

      {toastMessage && (
        <div className={`toast-notice${toastKind === 'error' ? ' toast-error' : ''}`} role={toastKind === 'error' ? 'alert' : 'status'}>
          {toastKind === 'error' ? <AlertCircle size={16} className="toast-icon-error" /> : <CheckCircle2 size={16} className="toast-icon-ok" />}
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  )
}
export default App
