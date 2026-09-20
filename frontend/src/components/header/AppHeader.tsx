import React from 'react'
import { useUiStore } from '../../stores/useUiStore'
import type { ViewMode } from '../../stores/useUiStore'
import { indexFolderApi } from '../../api/client'
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
} from 'lucide-react'

export const AppHeader: React.FC = () => {
  const [isIndexing, setIsIndexing] = React.useState(false)
  const {
    theme,
    toggleTheme,
    activeView,
    setActiveView,
    lightsOut,
    toggleLightsOut,
    sidebarOpen,
    toggleSidebar,
    inspectorOpen,
    toggleInspector,
    setCommandPaletteOpen,
    showToast,
  } = useUiStore()

  const handleScanFolder = async () => {
    let folderPath: string | null = null
    if (window.electronAPI?.openDirectory) {
      folderPath = await window.electronAPI.openDirectory()
    } else {
      folderPath = window.prompt('Enter absolute folder path to index:')
    }

    if (!folderPath) return

    try {
      setIsIndexing(true)
      showToast(`Indexing folder: ${folderPath}...`)
      const res = await indexFolderApi(folderPath)
      showToast(res.message)
      window.dispatchEvent(new CustomEvent('photos-updated'))
    } catch (err: any) {
      showToast(`Error indexing folder: ${err.message}`)
    } finally {
      setIsIndexing(false)
    }
  }

  const views: { key: ViewMode; label: string; icon: React.ReactNode }[] = [
    { key: 'studio', label: 'Studio Grid', icon: <LayoutGrid size={15} /> },
    { key: 'timeline', label: 'Timeline', icon: <Calendar size={15} /> },
    { key: 'map', label: 'Map Explorer', icon: <MapPin size={15} /> },
    { key: 'kanban', label: 'Collections', icon: <Kanban size={15} /> },
    { key: 'analytics', label: 'Analytics', icon: <BarChart3 size={15} /> },
  ]

  const handleExportJson = () => {
    showToast('Exporting metadata JSON package...')
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

        <button
          className="btn btn-secondary"
          onClick={handleScanFolder}
          disabled={isIndexing}
          title="Scan and index photos from a local folder"
          style={{ padding: '6px 12px', gap: '6px' }}
        >
          <FolderPlus size={15} color="var(--accent-primary)" />
          <span>{isIndexing ? 'Indexing...' : 'Scan Folder'}</span>
        </button>

        <button className="btn btn-primary" onClick={handleExportJson}>
          <Download size={15} />
          <span>Export JSON</span>
        </button>
      </div>
    </header>
  )
}
