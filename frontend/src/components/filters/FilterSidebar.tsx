import React from 'react'
import { useUiStore } from '../../stores/useUiStore'
import { DropdownFilterCard } from './DropdownFilterCard'
import { Camera, Tag, Folder, Keyboard, RotateCcw } from 'lucide-react'

export const FilterSidebar: React.FC = () => {
  const {
    sidebarOpen,
    filterCameras,
    toggleCameraFilter,
    filterTags,
    toggleTagFilter,
    filterCollection,
    setCollectionFilter,
    resetFilters,
  } = useUiStore()

  if (!sidebarOpen) return null

  const cameras = [
    { name: 'Sony', count: 10 },
    { name: 'Canon', count: 6 },
    { name: 'Apple', count: 4 },
    { name: 'Nikon', count: 4 },
  ]

  const tags = [
    { name: 'travel', count: 12 },
    { name: 'landscape', count: 8 },
    { name: 'architecture', count: 7 },
    { name: 'portrait', count: 5 },
    { name: 'night', count: 4 },
    { name: 'urban', count: 4 },
  ]

  const collections = [
    { name: 'all', label: '📁 All Indexed Photos (24)' },
    { name: 'Favorites', label: '⭐ Flagged / Picks (8)' },
    { name: 'Japan Trip 2026', label: '🌸 Japan Trip 2026 (12)' },
    { name: 'Client Shoots', label: '💼 Client Shoots (4)' },
  ]

  return (
    <aside
      className="sidebar-pane"
      style={{
        width: '280px',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
        padding: '16px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
          Filters & Hierarchy
        </span>
        <button
          onClick={resetFilters}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--accent-primary)',
            fontSize: '0.75rem',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <RotateCcw size={12} />
          <span>Reset All</span>
        </button>
      </div>

      {/* 1. Camera Brands Dropdown */}
      <DropdownFilterCard
        title="Camera Brands"
        icon={<Camera size={15} color="var(--accent-secondary)" />}
        activeBadgeText={filterCameras.length > 0 ? `${filterCameras.length} active` : undefined}
        onReset={() => useUiStore.setState({ filterCameras: [] })}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '160px', overflowY: 'auto' }}>
          {cameras.map((c) => (
            <label
              key={c.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 8px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                color: filterCameras.includes(c.name) ? 'var(--accent-primary)' : 'var(--text-secondary)',
                background: filterCameras.includes(c.name) ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  checked={filterCameras.includes(c.name)}
                  onChange={() => toggleCameraFilter(c.name)}
                  style={{ accentColor: 'var(--accent-primary)' }}
                />
                <span>{c.name}</span>
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>({c.count})</span>
            </label>
          ))}
        </div>
      </DropdownFilterCard>

      {/* 2. Tags & Labels Dropdown */}
      <DropdownFilterCard
        title="Tags & Labels"
        icon={<Tag size={15} color="var(--accent-success)" />}
        activeBadgeText={filterTags.length > 0 ? `${filterTags.length} active` : undefined}
        onReset={() => useUiStore.setState({ filterTags: [] })}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {tags.map((t) => {
            const active = filterTags.includes(t.name)
            return (
              <button
                key={t.name}
                onClick={() => toggleTagFilter(t.name)}
                className={`badge ${active ? 'badge-tag' : ''}`}
                style={{
                  padding: '4px 8px',
                  cursor: 'pointer',
                  border: active ? '1px solid var(--accent-success)' : '1px solid var(--border-color)',
                  background: active ? 'rgba(52, 211, 153, 0.2)' : 'var(--bg-surface)',
                  color: active ? 'var(--accent-success)' : 'var(--text-secondary)',
                  fontWeight: active ? 600 : 400,
                }}
              >
                #{t.name} <span style={{ fontSize: '0.65rem', opacity: 0.8 }}>({t.count})</span>
              </button>
            )
          })}
        </div>
      </DropdownFilterCard>

      {/* 3. Collections & Picks Dropdown */}
      <DropdownFilterCard
        title="Collections & Picks"
        icon={<Folder size={15} color="var(--accent-warning)" />}
        activeBadgeText={filterCollection !== 'all' ? filterCollection : undefined}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {collections.map((col) => (
            <div
              key={col.name}
              onClick={() => setCollectionFilter(col.name)}
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.78rem',
                cursor: 'pointer',
                color: filterCollection === col.name ? 'var(--accent-primary)' : 'var(--text-secondary)',
                background: filterCollection === col.name ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                fontWeight: filterCollection === col.name ? 600 : 400,
              }}
            >
              {col.label}
            </div>
          ))}
        </div>
      </DropdownFilterCard>

      {/* Hotkeys card */}
      <DropdownFilterCard
        title="Keyboard Hotkeys"
        icon={<Keyboard size={15} color="var(--text-muted)" />}
        defaultOpen={false}
      >
        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Quick Lightbox</span>
            <kbd className="kbd-chip">Space</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Pick / Flag</span>
            <kbd className="kbd-chip">P</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Star Rating</span>
            <kbd className="kbd-chip">1-5</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Lights Out Dim</span>
            <kbd className="kbd-chip">L</kbd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Command Palette</span>
            <kbd className="kbd-chip">Ctrl+K</kbd>
          </div>
        </div>
      </DropdownFilterCard>
    </aside>
  )
}
