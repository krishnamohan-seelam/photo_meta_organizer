import React, { useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Camera, Flag, Folder, Images, Plus, Star } from 'lucide-react'
import { useUiStore } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { useFacets } from '../../hooks/useFacets'
import { useCollections, useSaveCollection } from '../../hooks/useCollections'
import { NameDialog } from '../collections/NameDialog'

interface RowProps {
  icon: React.ReactNode
  label: string
  count?: number
  pressed: boolean
  onClick: () => void
  /** 0..1: a proportion bar under the label (cameras). */
  share?: number
}

const PanelRow: React.FC<RowProps> = ({ icon, label, count, pressed, onClick, share }) => (
  <button type="button" className="btn-reset lib-row" aria-pressed={pressed} onClick={onClick}>
    <span className="lib-row-ic" aria-hidden="true">
      {icon}
    </span>
    <span className="lib-row-label">{label}</span>
    <span className="lib-row-count">{count ?? ''}</span>
    {share !== undefined && (
      <span className="lib-row-bar" aria-hidden="true">
        <i style={{ width: `${Math.round(share * 100)}%` }} />
      </span>
    )}
  </button>
)

const Section: React.FC<{ title: string; onClear?: () => void; action?: React.ReactNode; children: React.ReactNode }> = ({ title, onClear, action, children }) => (
  <section className="lib-sec" aria-label={title}>
    <div className="sec-h">
      <span>{title}</span>
      {onClear ? (
        <button type="button" className="btn-reset link-btn" onClick={onClear}>
          Clear
        </button>
      ) : (
        action
      )}
    </div>
    {children}
  </section>
)

/** Flat filter panel (FR-1d.1): Library, Rating, Collections, Cameras and Tags, with whole-library counts. */
export const LibraryPanel: React.FC = () => {
  const s = useUiStore(
    useShallow((st) => ({
      sidebarOpen: st.sidebarOpen,
      filterCameras: st.filterCameras,
      toggleCameraFilter: st.toggleCameraFilter,
      filterTags: st.filterTags,
      toggleTagFilter: st.toggleTagFilter,
      filterCollection: st.filterCollection,
      setCollectionFilter: st.setCollectionFilter,
      filterRating: st.filterRating,
      setRatingFilter: st.setRatingFilter,
    }))
  )
  const selectionCount = useSelectionStore((st) => st.selectedHashes.size)
  const { cameras, tags, stats } = useFacets()
  const collections = useCollections()
  const saveCollection = useSaveCollection()
  const [naming, setNaming] = useState(false)

  if (!s.sidebarOpen) return null

  const camerasByCount = [...cameras].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  const largestCamera = camerasByCount[0]?.count ?? 0
  const namedCollection = s.filterCollection !== 'all' && s.filterCollection !== 'Favorites'

  return (
    <aside className="lib-panel" aria-label="Library panel">
      <div className="lib-title">Library</div>

      <section className="lib-sec" aria-label="Library">
        <PanelRow icon={<Images size={15} />} label="All photos" count={stats.total_count} pressed={s.filterCollection === 'all'} onClick={() => s.setCollectionFilter('all')} />
        <PanelRow icon={<Flag size={15} />} label="Picks" count={stats.flagged_count} pressed={s.filterCollection === 'Favorites'} onClick={() => s.setCollectionFilter('Favorites')} />
      </section>

      <Section title="Rating" onClear={s.filterRating !== null ? () => s.setRatingFilter(null) : undefined}>
        {[5, 4, 3, 2, 1].map((n) => (
          <PanelRow
            key={n}
            icon={<Star size={15} />}
            label={`${n} star${n > 1 ? 's' : ''}`}
            pressed={s.filterRating === n}
            onClick={() => s.setRatingFilter(s.filterRating === n ? null : n)}
          />
        ))}
      </Section>

      <Section
        title="Collections"
        onClear={namedCollection ? () => s.setCollectionFilter('all') : undefined}
        action={
          <button
            type="button"
            className="btn-reset link-btn"
            onClick={() => setNaming(true)}
            disabled={selectionCount === 0}
            aria-label="New collection from the selection"
            title={selectionCount === 0 ? 'Select photos first' : `New collection from ${selectionCount} selected`}
          >
            <Plus size={13} />
          </button>
        }
      >
        {collections.length === 0 && <div className="lib-empty">No collections yet</div>}
        {collections.map((c) => (
          <PanelRow
            key={c.name}
            icon={<Folder size={15} />}
            label={c.name}
            count={c.photo_hashes.length}
            pressed={s.filterCollection === c.name}
            onClick={() => s.setCollectionFilter(s.filterCollection === c.name ? 'all' : c.name)}
          />
        ))}
      </Section>

      <Section title="Cameras" onClear={s.filterCameras.length > 0 ? () => useUiStore.setState({ filterCameras: [] }) : undefined}>
        {camerasByCount.length === 0 && <div className="lib-empty">No camera data</div>}
        {camerasByCount.map((c) => (
          <PanelRow
            key={c.name}
            icon={<Camera size={15} />}
            label={c.name}
            count={c.count}
            share={largestCamera ? c.count / largestCamera : 0}
            pressed={s.filterCameras.includes(c.name)}
            onClick={() => s.toggleCameraFilter(c.name)}
          />
        ))}
      </Section>

      <Section title="Tags" onClear={s.filterTags.length > 0 ? () => useUiStore.setState({ filterTags: [] }) : undefined}>
        {tags.length === 0 ? (
          <div className="lib-empty">No tags yet</div>
        ) : (
          <div className="pill-list">
            {tags.map((t) => (
              <button key={t.name} type="button" className="btn-reset pill" aria-pressed={s.filterTags.includes(t.name)} onClick={() => s.toggleTagFilter(t.name)}>
                {t.name}
                <span className="pill-count">{t.count}</span>
              </button>
            ))}
          </div>
        )}
      </Section>

      {naming && (
        <NameDialog
          title={`New collection from ${selectionCount} photo${selectionCount === 1 ? '' : 's'}`}
          label="Collection name"
          placeholder="e.g. Japan 2026"
          submitLabel="Create"
          onSubmit={(name) => saveCollection(name, [...useSelectionStore.getState().selectedHashes], collections.find((c) => c.name === name))}
          onClose={() => setNaming(false)}
        />
      )}
    </aside>
  )
}
