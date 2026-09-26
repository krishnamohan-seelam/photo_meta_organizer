import React from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useUiStore } from '../../stores/useUiStore'
import type { ViewMode } from '../../stores/useUiStore'
import { useJobs } from '../../hooks/useJobs'
import { JobProgress } from '../jobs/JobProgress'
import {
  Camera,
  Search,
  Sun,
  Moon,
  EyeOff,
  LayoutGrid,
  Calendar,
  MapPin,
  Kanban,
  BarChart3,
  PanelLeftClose,
  PanelRightClose,
  Download,
  FolderPlus,
  RefreshCw,
} from 'lucide-react'

export const AppHeader: React.FC = () => {
  const { activeJob } = useJobs()
  const setJobDialog = useUiStore((s) => s.setJobDialog)
  const { theme, toggleTheme, activeView, setActiveView, lightsOut, toggleLightsOut, sidebarOpen, toggleSidebar, inspectorOpen, toggleInspector, setCommandPaletteOpen, showToast } = useUiStore(useShallow((s) => ({ theme: s.theme, toggleTheme: s.toggleTheme, activeView: s.activeView, setActiveView: s.setActiveView, lightsOut: s.lightsOut, toggleLightsOut: s.toggleLightsOut, sidebarOpen: s.sidebarOpen, toggleSidebar: s.toggleSidebar, inspectorOpen: s.inspectorOpen, toggleInspector: s.toggleInspector, setCommandPaletteOpen: s.setCommandPaletteOpen, showToast: s.showToast })))

  const views: { key: ViewMode; label: string; icon: React.ReactNode }[] = [
    { key: 'studio', label: 'Studio Grid', icon: <LayoutGrid size={15} /> },
    { key: 'timeline', label: 'Timeline', icon: <Calendar size={15} /> },
    { key: 'map', label: 'Map Explorer', icon: <MapPin size={15} /> },
    { key: 'kanban', label: 'Collections', icon: <Kanban size={15} /> },
    { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={15} /> },
  ]

  const handleExportJson = () => {
    // Not built yet (PMO-30): say so rather than announce an export that never happens.
    showToast('Metadata export is not available yet', 'error')
  }

  return (
    <header className="app-header">
      {/* Brand */}
      <div className="brand">
        <div className="brand-logo">
          <Camera size={18} />
        </div>
        <span>Photo Meta Organizer</span>
        <span className="badge badge-camera" style={{ textTransform: 'uppercase' }}>
          Phase 4 Pro
        </span>
      </div>

      {/* Command Palette Trigger */}
      <div className="cmd-k-trigger" onClick={() => setCommandPaletteOpen(true)}>
        <Search size={15} />
        <span>Type a command or search...</span>
        <span className="kbd-chip">Ctrl + K</span>
      </div>

      {/* View Switcher Navigation */}
      <div
        style={{
          display: 'flex',
          background: 'var(--bg-surface)',
          padding: '3px',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border-color)',
          gap: '2px',
        }}
      >
        {views.map((v) => (
          <button
            key={v.key}
            onClick={() => setActiveView(v.key)}
            className={`btn ${activeView === v.key ? 'btn-primary' : 'btn-secondary'}`}
            style={{
              padding: '5px 10px',
              fontSize: '0.78rem',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
            }}
          >
            {v.icon}
            <span>{v.label}</span>
          </button>
        ))}
      </div>

      {/* Header Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* Light / Dark Mode Toggle */}
        <button
          className="btn btn-secondary"
          onClick={toggleTheme}
          title="Switch Light/Dark Mode"
          style={{ padding: '6px 12px' }}
        >
          {theme === 'dark' ? <Sun size={15} color="var(--accent-warning)" /> : <Moon size={15} />}
          <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
        </button>

        {/* Lights Out Toggle */}
        <button
          className={`btn ${lightsOut ? 'btn-primary' : 'btn-secondary'}`}
          onClick={toggleLightsOut}
          title="Toggle Lights Out Mode (Hotkey: L)"
          style={{ padding: '6px 12px' }}
        >
          <EyeOff size={15} />
          <span>Dim</span>
        </button>

        {/* Panel Toggles (visible in Studio view) */}
        {activeView === 'studio' && (
          <>
            <button
              className={`btn ${sidebarOpen ? 'btn-secondary' : 'btn-primary'}`}
              onClick={toggleSidebar}
              title="Toggle Filter Sidebar"
              style={{ padding: '6px 10px' }}
            >
              <PanelLeftClose size={15} />
            </button>
            <button
              className={`btn ${inspectorOpen ? 'btn-secondary' : 'btn-primary'}`}
              onClick={toggleInspector}
              title="Toggle EXIF Inspector"
              style={{ padding: '6px 10px' }}
            >
              <PanelRightClose size={15} />
            </button>
          </>
        )}

        {activeJob ? (
          <JobProgress job={activeJob} />
        ) : (
          <>
            <button
              className="btn btn-secondary"
              onClick={() => setJobDialog('index')}
              title="Scan and index photos from a local folder"
              style={{ padding: '6px 12px', gap: '6px', whiteSpace: 'nowrap' }}
            >
              <FolderPlus size={15} color="var(--accent-primary)" />
              <span>Scan</span>
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setJobDialog('sync')}
              title="Re-check a scanned folder for new, edited and deleted photos"
              style={{ padding: '6px 12px', gap: '6px', whiteSpace: 'nowrap' }}
            >
              <RefreshCw size={15} color="var(--accent-primary)" />
              <span>Sync</span>
            </button>
          </>
        )}

        <button className="btn btn-primary" onClick={handleExportJson} style={{ whiteSpace: 'nowrap' }}>
          <Download size={15} />
          <span>Export JSON</span>
        </button>
      </div>
    </header>
  )
}
