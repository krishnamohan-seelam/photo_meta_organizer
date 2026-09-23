import React, { useState, useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useUiStore } from '../../stores/useUiStore'
import { Search, Camera, Tag, MapPin, Sun, EyeOff, Download, CheckSquare } from 'lucide-react'

export const CommandPalette: React.FC = () => {
  const { commandPaletteOpen, setCommandPaletteOpen, toggleTheme, toggleLightsOut, setActiveView, toggleCameraFilter, toggleTagFilter, setCityFilter, showToast } = useUiStore(useShallow((s) => ({ commandPaletteOpen: s.commandPaletteOpen, setCommandPaletteOpen: s.setCommandPaletteOpen, toggleTheme: s.toggleTheme, toggleLightsOut: s.toggleLightsOut, setActiveView: s.setActiveView, toggleCameraFilter: s.toggleCameraFilter, toggleTagFilter: s.toggleTagFilter, setCityFilter: s.setCityFilter, showToast: s.showToast })))

  const [search, setSearch] = useState('')

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandPaletteOpen(!commandPaletteOpen)
      } else if (e.key === 'Escape' && commandPaletteOpen) {
        setCommandPaletteOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [commandPaletteOpen, setCommandPaletteOpen])

  if (!commandPaletteOpen) return null

  const commands = [
    {
      id: 'theme',
      title: 'Toggle Light / Dark Mode',
      icon: <Sun size={15} />,
      hotkey: 'Theme',
      action: () => toggleTheme(),
    },
    {
      id: 'dim',
      title: 'Toggle Lights Out Dimmer',
      icon: <EyeOff size={15} />,
      hotkey: 'L',
      action: () => toggleLightsOut(),
    },
    {
      id: 'map',
      title: 'Open Geospatial Map Explorer',
      icon: <MapPin size={15} />,
      hotkey: 'Map',
      action: () => setActiveView('map'),
    },
    {
      id: 'analytics',
      title: 'Open Library Analytics Dashboard',
      icon: <CheckSquare size={15} />,
      hotkey: 'Stats',
      action: () => setActiveView('analytics'),
    },
    {
      id: 'cam-sony',
      title: 'Filter: Sony Cameras',
      icon: <Camera size={15} />,
      action: () => {
        toggleCameraFilter('Sony')
        setActiveView('studio')
        showToast('Filtered by Sony cameras')
      },
    },
    {
      id: 'cam-canon',
      title: 'Filter: Canon Cameras',
      icon: <Camera size={15} />,
      action: () => {
        toggleCameraFilter('Canon')
        setActiveView('studio')
        showToast('Filtered by Canon cameras')
      },
    },
    {
      id: 'tag-travel',
      title: 'Filter: #travel tag',
      icon: <Tag size={15} />,
      action: () => {
        toggleTagFilter('travel')
        setActiveView('studio')
        showToast('Filtered by #travel tag')
      },
    },
    {
      id: 'city-tokyo',
      title: 'Filter Location: Tokyo, Japan',
      icon: <MapPin size={15} />,
      action: () => {
        setCityFilter('Tokyo')
        setActiveView('studio')
        showToast('Filtered by Tokyo')
      },
    },
    {
      id: 'export',
      title: 'Bundle & Export All Metadata JSON',
      icon: <Download size={15} />,
      hotkey: 'Export',
      action: () => showToast('Metadata export is not available yet', 'error'),
    },
  ]

  const filtered = commands.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase().trim())
  )

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        zIndex: 99999,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '15vh',
      }}
      onClick={() => setCommandPaletteOpen(false)}
    >
      <div
        style={{
          background: 'var(--modal-bg)',
          border: '1px solid var(--border-color)',
          boxShadow: 'var(--shadow-lg), 0 0 20px var(--accent-glow)',
          borderRadius: 'var(--radius-lg)',
          width: '90%',
          maxWidth: '580px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px 18px',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          <Search size={18} color="var(--text-muted)" />
          <input
            type="text"
            autoFocus
            placeholder="Type a command, camera model, tag, or city..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: 'var(--text-primary)',
              fontSize: '1rem',
              fontFamily: 'inherit',
            }}
          />
        </div>

        {/* Results List */}
        <div
          style={{
            maxHeight: '320px',
            overflowY: 'auto',
            padding: '8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          {filtered.map((cmd) => (
            <div
              key={cmd.id}
              onClick={() => {
                setCommandPaletteOpen(false)
                cmd.action()
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                fontSize: '0.85rem',
                cursor: 'pointer',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(56, 189, 248, 0.15)'
                e.currentTarget.style.color = 'var(--text-primary)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.color = 'var(--text-secondary)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {cmd.icon}
                <span>{cmd.title}</span>
              </div>
              {cmd.hotkey && <span className="kbd-chip">{cmd.hotkey}</span>}
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No commands matching "{search}"
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '8px 16px',
            background: 'var(--box-bg)',
            borderTop: '1px solid var(--border-color)',
            fontSize: '0.72rem',
            color: 'var(--text-muted)',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>Select: <kbd className="kbd-chip">Enter</kbd></span>
          <span>Close: <kbd className="kbd-chip">Esc</kbd></span>
        </div>
      </div>
    </div>
  )
}
