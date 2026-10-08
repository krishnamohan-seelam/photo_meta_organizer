import React from 'react'
import { useShallow } from 'zustand/react/shallow'
import { CheckSquare, ImageIcon, LayoutGrid, Table2, X } from 'lucide-react'
import type { SortField } from '../../types/metadata'
import { ROW_HEIGHT_MAX, ROW_HEIGHT_MIN, useUiStore } from '../../stores/useUiStore'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { useFacets } from '../../hooks/useFacets'
import { removeFilterChip, useLibraryFilters } from '../../hooks/useLibraryFilters'
import { useSelectAllMatches } from '../../hooks/useSelectAllMatches'
import { filterChips, galleryTitle } from '../../utils/filterChips'
import { PhotoGallery } from './PhotoGallery'
import { PhotoTable } from './PhotoTable'

/** Sort choices, all applied by the server (PMO-27). Unknown capture dates always sort last. */
const SORTS: { value: string; label: string; field: SortField; order: 'asc' | 'desc' }[] = [
  { value: 'captured_at:desc', label: 'Newest', field: 'captured_at', order: 'desc' },
  { value: 'captured_at:asc', label: 'Oldest', field: 'captured_at', order: 'asc' },
  { value: 'file_name:asc', label: 'Name', field: 'file_name', order: 'asc' },
  { value: 'size_bytes:desc', label: 'Largest', field: 'size_bytes', order: 'desc' },
  { value: 'camera_model:asc', label: 'Camera', field: 'camera_model', order: 'asc' },
]

/** Title, counts, active-filter chips, sort, layout and size (FR-1c.9, FR-2c.1). */
const GalleryToolbar: React.FC = () => {
  const { gridItemSize, setGridItemSize, sortBy, sortOrder, setSort, libraryLayout, setLibraryLayout } = useUiStore(
    useShallow((s) => ({
      gridItemSize: s.gridItemSize,
      setGridItemSize: s.setGridItemSize,
      sortBy: s.sortBy,
      sortOrder: s.sortOrder,
      setSort: s.setSort,
      libraryLayout: s.libraryLayout,
      setLibraryLayout: s.setLibraryLayout,
    }))
  )
  const filters = useLibraryFilters()
  const { photos, totalCount, isPlaceholderData } = usePhotoSearch()
  const { stats } = useFacets()
  const { selectAllMatches, busy } = useSelectAllMatches()
  const chips = filterChips(filters)
  const sortValue = `${sortBy}:${sortOrder}`

  return (
    <div className="gallery-toolbar">
      <h1>{galleryTitle(filters.filterCollection)}</h1>
      <span className="gallery-meta num" role="status">
        {totalCount.toLocaleString()} of {stats.total_count.toLocaleString()}
        {photos.length < totalCount && ` · ${photos.length.toLocaleString()} loaded`}
        {isPlaceholderData && ' · updating…'}
      </span>
      {chips.length > 0 && (
        <div className="chips" aria-label="Active filters">
          {chips.map((chip) => (
            <span key={chip.id} className="chip">
              {chip.label}
              <button type="button" className="btn-reset" onClick={() => removeFilterChip(chip)} aria-label={`Remove filter ${chip.label}`}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      <span className="toolbar-spacer" />
      {libraryLayout === 'grid' && (
        <div className="seg" role="group" aria-label="Sort">
          {SORTS.map((s) => (
            <button key={s.value} type="button" className="btn-reset" aria-pressed={sortValue === s.value} onClick={() => setSort(s.field, s.order)}>
              {s.label}
            </button>
          ))}
        </div>
      )}
      {libraryLayout === 'grid' && (
        <label className="size-control" title="Row height">
          <ImageIcon size={14} aria-hidden="true" />
          <span className="visually-hidden">Row height</span>
          <input type="range" min={ROW_HEIGHT_MIN} max={ROW_HEIGHT_MAX} step={10} value={gridItemSize} onChange={(e) => setGridItemSize(parseInt(e.target.value, 10))} />
        </label>
      )}
      <div className="seg" role="group" aria-label="Layout">
        <button type="button" className="btn-reset seg-icon" aria-pressed={libraryLayout === 'grid'} aria-label="Grid" aria-keyshortcuts="V" title="Grid (V)" onClick={() => setLibraryLayout('grid')}>
          <LayoutGrid size={14} />
        </button>
        <button type="button" className="btn-reset seg-icon" aria-pressed={libraryLayout === 'table'} aria-label="Table" aria-keyshortcuts="V" title="Table (V)" onClick={() => setLibraryLayout('table')}>
          <Table2 size={14} />
        </button>
      </div>
      {libraryLayout === 'grid' && (
        <button type="button" className="btn btn-sm" onClick={() => void selectAllMatches()} disabled={busy || totalCount === 0}>
          <CheckSquare size={14} />
          <span>Select all</span>
        </button>
      )}
    </div>
  )
}

/** The Library view: one toolbar over the grid or the table (FR-2c.1). Filters, selection and the inspected photo are shared. */
export const LibraryView: React.FC = () => {
  const layout = useUiStore((s) => s.libraryLayout)
  return (
    <main className="gallery-pane" aria-label="Library">
      <GalleryToolbar />
      {layout === 'grid' ? <PhotoGallery /> : <PhotoTable />}
    </main>
  )
}
