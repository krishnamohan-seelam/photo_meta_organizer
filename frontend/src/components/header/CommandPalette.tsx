import React, { useState, useEffect, useId, useRef } from 'react'
import { useShallow } from 'zustand/react/shallow'
import {
  BarChart3,
  CalendarDays,
  Camera,
  Columns3,
  Download,
  EyeOff,
  FolderInput,
  Keyboard,
  LayoutGrid,
  MapPin,
  RefreshCw,
  Search,
  SunMoon,
  Tag,
} from 'lucide-react'
import { useUiStore, type ViewMode } from '../../stores/useUiStore'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useExport } from '../../hooks/useExport'
import { useFacets } from '../../hooks/useFacets'
import { VIEW_LABELS } from '../../utils/shortcuts'

interface Command {
  id: string
  title: string
  icon: React.ReactNode
  hotkey?: string
  action: () => void
}

const VIEW_ICONS: Record<ViewMode, React.ReactNode> = {
  studio: <LayoutGrid size={15} />,
  timeline: <CalendarDays size={15} />,
  map: <MapPin size={15} />,
  kanban: <Columns3 size={15} />,
  analytics: <BarChart3 size={15} />,
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
  const { toggleTheme, toggleLightsOut, setActiveView, toggleCameraFilter, toggleTagFilter, setJobDialog, setShortcutsOpen } = useUiStore(
    useShallow((s) => ({
      toggleTheme: s.toggleTheme,
      toggleLightsOut: s.toggleLightsOut,
      setActiveView: s.setActiveView,
      toggleCameraFilter: s.toggleCameraFilter,
      toggleTagFilter: s.toggleTagFilter,
      setJobDialog: s.setJobDialog,
      setShortcutsOpen: s.setShortcutsOpen,
    }))
  )
  const { cameras, tags } = useFacets()

  const [search, setSearch] = useState('')
  const [active, setActive] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  useDialogFocus(dialogRef, inputRef)

  const { exportJson } = useExport()

  const views = (Object.keys(VIEW_LABELS) as ViewMode[]).map<Command>((view) => ({
    id: `view-${view}`,
    title: `Go to ${VIEW_LABELS[view].label}`,
    icon: VIEW_ICONS[view],
    hotkey: VIEW_LABELS[view].key,
    action: () => setActiveView(view),
  }))

  const commands: Command[] = [
    ...views,
    { id: 'scan', title: 'Import (scan a folder)…', icon: <FolderInput size={15} />, action: () => setJobDialog('index') },
    { id: 'sync', title: 'Sync a folder…', icon: <RefreshCw size={15} />, action: () => setJobDialog('sync') },
    { id: 'theme', title: 'Toggle light/dark theme', icon: <SunMoon size={15} />, action: () => toggleTheme() },
    { id: 'dim', title: 'Toggle Lights Out', icon: <EyeOff size={15} />, hotkey: 'L', action: () => toggleLightsOut() },
    { id: 'export', title: 'Export library as JSON', icon: <Download size={15} />, action: () => void exportJson() },
    { id: 'shortcuts', title: 'Keyboard shortcuts', icon: <Keyboard size={15} />, hotkey: '?', action: () => setShortcutsOpen(true) },
    // Filters for what the library actually holds (whole-library facets).
    ...cameras.map<Command>((c) => ({
      id: `cam-${c.name}`,
      title: `Filter: camera ${c.name}`,
      icon: <Camera size={15} />,
      action: () => {
        toggleCameraFilter(c.name)
        setActiveView('studio')
      },
    })),
    ...tags.map<Command>((t) => ({
      id: `tag-${t.name}`,
      title: `Filter: #${t.name}`,
      icon: <Tag size={15} />,
      action: () => {
        toggleTagFilter(t.name)
        setActiveView('studio')
      },
    })),
  ]

  const filtered = commands.filter((c) => c.title.toLowerCase().includes(search.toLowerCase().trim()))
  const current = Math.min(active, Math.max(filtered.length - 1, 0))
  const optionId = (id: string) => `${listId}-${id.replace(/\s+/g, '_')}`
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
    if (activeId) document.getElementById(activeId)?.scrollIntoView?.({ block: 'nearest' })
  }, [activeId])

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Command palette" className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <Search size={18} aria-hidden="true" />
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
            placeholder="Type a command, camera or tag…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setActive(0)
            }}
          />
        </div>

        <div id={listId} role="listbox" aria-label="Commands" className="palette-list">
          {/* Focus stays in the search box (aria-activedescendant), so options need no tabIndex. */}
          {filtered.map((cmd, idx) => (
            <div
              key={cmd.id}
              id={optionId(cmd.id)}
              role="option"
              aria-selected={idx === current}
              className="palette-option"
              onClick={() => run(cmd)}
              onMouseMove={() => idx !== current && setActive(idx)}
            >
              <span className="palette-option-main">
                {cmd.icon}
                <span>{cmd.title}</span>
              </span>
              {cmd.hotkey && <kbd className="kbd-chip">{cmd.hotkey}</kbd>}
            </div>
          ))}
          {filtered.length === 0 && <div className="palette-empty">No commands matching "{search}"</div>}
        </div>

        <div className="palette-footer">
          <span>
            Move <kbd className="kbd-chip">↑</kbd> <kbd className="kbd-chip">↓</kbd> · Run <kbd className="kbd-chip">Enter</kbd>
          </span>
          <span>
            Close <kbd className="kbd-chip">Esc</kbd>
          </span>
        </div>
      </div>
    </div>
  )
}
