import React, { useState, useEffect, useId, useRef } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useUiStore } from '../../stores/useUiStore'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { Search, Camera, Tag, MapPin, Sun, EyeOff, Download, CheckSquare, FolderPlus, RefreshCw } from 'lucide-react'

interface Command {
  id: string
  title: string
  icon: React.ReactNode
  hotkey?: string
  action: () => void
}

/** Ctrl/Cmd+K toggles the palette from anywhere; the palette itself mounts only while open. */
export const CommandPalette: React.FC = () => {
  const { commandPaletteOpen, setCommandPaletteOpen } = useUiStore(useShallow((s) => ({ commandPaletteOpen: s.commandPaletteOpen, setCommandPaletteOpen: s.setCommandPaletteOpen })))

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandPaletteOpen(!commandPaletteOpen)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [commandPaletteOpen, setCommandPaletteOpen])

  return commandPaletteOpen ? <Palette onClose={() => setCommandPaletteOpen(false)} /> : null
}

const Palette: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { toggleTheme, toggleLightsOut, setActiveView, toggleCameraFilter, toggleTagFilter, setCityFilter, showToast, setJobDialog } = useUiStore(useShallow((s) => ({ toggleTheme: s.toggleTheme, toggleLightsOut: s.toggleLightsOut, setActiveView: s.setActiveView, toggleCameraFilter: s.toggleCameraFilter, toggleTagFilter: s.toggleTagFilter, setCityFilter: s.setCityFilter, showToast: s.showToast, setJobDialog: s.setJobDialog })))

  const [search, setSearch] = useState('')
  const [active, setActive] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  useDialogFocus(dialogRef, inputRef)

  const commands: Command[] = [
    {
      id: 'scan',
      title: 'Scan a folder…',
      icon: <FolderPlus size={15} />,
      action: () => setJobDialog('index'),
    },
    {
      id: 'sync',
      title: 'Sync a folder…',
      icon: <RefreshCw size={15} />,
      action: () => setJobDialog('sync'),
    },
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
  const current = Math.min(active, Math.max(filtered.length - 1, 0))
  const optionId = (id: string) => `${listId}-${id}`
  const activeId = filtered[current] ? optionId(filtered[current].id) : undefined

  const run = (cmd: Command) => {
    onClose()
    cmd.action()
  }

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (filtered.length === 0) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((current + step + filtered.length) % filtered.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[current]) run(filtered[current])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  // Keep the highlighted command in view while arrowing through a long list.
  useEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: 'nearest' })
  }, [activeId])

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
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
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
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeId}
            aria-label="Search commands"
            onKeyDown={onInputKeyDown}
            placeholder="Type a command, camera model, tag, or city..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setActive(0)
            }}
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
          id={listId}
          role="listbox"
          aria-label="Commands"
          style={{
            maxHeight: '320px',
            overflowY: 'auto',
            padding: '8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          {/* Focus stays in the search box (aria-activedescendant), so options need no tabIndex. */}
          {filtered.map((cmd, idx) => (
            <div
              key={cmd.id}
              id={optionId(cmd.id)}
              role="option"
              aria-selected={idx === current}
              onClick={() => run(cmd)}
              onMouseMove={() => idx !== current && setActive(idx)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 'var(--radius-sm)',
                color: idx === current ? 'var(--text-primary)' : 'var(--text-secondary)',
                background: idx === current ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                fontSize: '0.85rem',
                cursor: 'pointer',
                transition: 'background 0.15s, color 0.15s',
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
          <span>Move: <kbd className="kbd-chip">↑</kbd> <kbd className="kbd-chip">↓</kbd> · Select: <kbd className="kbd-chip">Enter</kbd></span>
          <span>Close: <kbd className="kbd-chip">Esc</kbd></span>
        </div>
      </div>
    </div>
  )
}
