import React, { useEffect, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { ChevronUp, Download, Flag, FolderPlus, Plus, Sparkles, Star, Tag, X } from 'lucide-react'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { useCuration } from '../../hooks/usePhotoMutations'
import { useExport } from '../../hooks/useExport'
import { aiSearchReady, useAnalysisStatus, useResolveAiTagsBatch } from '../../hooks/useAnalysis'
import { useCollections, useSaveCollection } from '../../hooks/useCollections'
import { formatBytes } from '../../utils/photoFormat'
import { NameDialog } from './NameDialog'

type Menu = 'rate' | 'collection' | 'export'
type Dialog = 'tag' | 'collection'

/** Close an open popover on Escape or a click outside it. */
function useDismiss(ref: React.RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        close()
      }
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey, true)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey, true)
    }
  }, [ref, open, close])
}

/**
 * Actions on the selection (FR-1f.2). It slides up while something is selected and away when the
 * selection is cleared; while hidden it is inert, so it is never reachable by Tab.
 */
export const SelectionDock: React.FC = () => {
  const { selectedHashes, selectedSizes, clearSelection } = useSelectionStore(useShallow((s) => ({ selectedHashes: s.selectedHashes, selectedSizes: s.selectedSizes, clearSelection: s.clearSelection })))
  const { batchPhotos } = useCuration()
  const { exportZip, zipProgress, exportJson, jsonBusy } = useExport()
  const collections = useCollections()
  const aiReady = aiSearchReady(useAnalysisStatus())
  const resolveAiTags = useResolveAiTagsBatch()
  const saveCollection = useSaveCollection()
  const [menu, setMenu] = useState<Menu | null>(null)
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const dockRef = useRef<HTMLDivElement>(null)
  useDismiss(dockRef, menu !== null, () => setMenu(null))

  const count = selectedHashes.size
  const shown = count > 0
  // The selection may include photos that are not loaded (select all), so sizes come from the store.
  let totalBytes = 0
  for (const size of selectedSizes.values()) totalBytes += size
  const hashes = () => Array.from(useSelectionStore.getState().selectedHashes)
  const plural = `${count} photo${count === 1 ? '' : 's'}`

  const rate = (rating: number | null) => {
    setMenu(null)
    void batchPhotos({ photo_hashes: hashes(), action: 'set_rating', value: rating }, rating ? `Rated ${plural} ${rating} ★` : `Cleared the rating of ${plural}`)
  }
  const pickAll = () => void batchPhotos({ photo_hashes: hashes(), action: 'set_flag', value: true }, `Picked ${plural}`)
  const exporting = zipProgress !== null

  const toggle = (m: Menu) => setMenu((current) => (current === m ? null : m))

  return (
    <>
      <div ref={dockRef} className={`selection-dock${shown ? ' show' : ''}`} role="toolbar" aria-label="Selection" aria-hidden={!shown} inert={!shown}>
        <span className="dock-count" role="status">
          {count} selected<small>{formatBytes(totalBytes)}</small>
        </span>

        <button type="button" className="btn btn-sm" onClick={pickAll}>
          <Flag size={14} /> Pick
        </button>

        <div className="dock-menu">
          <button type="button" className="btn btn-sm" aria-haspopup="true" aria-expanded={menu === 'rate'} onClick={() => toggle('rate')}>
            <Star size={14} /> Rate
          </button>
          {menu === 'rate' && (
            <div className="dock-popover" role="group" aria-label="Rate the selection">
              <div className="stars">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} type="button" className="btn-reset on" aria-label={`${n} star${n > 1 ? 's' : ''}`} onClick={() => rate(n)}>
                    <span className="num">{n}</span>
                    <Star size={15} />
                  </button>
                ))}
              </div>
              <button type="button" className="btn-reset menu-item" onClick={() => rate(null)}>
                Clear rating
              </button>
            </div>
          )}
        </div>

        <div className="dock-menu">
          <button type="button" className="btn btn-sm" aria-haspopup="true" aria-expanded={menu === 'collection'} onClick={() => toggle('collection')}>
            <FolderPlus size={14} /> Add to collection
          </button>
          {menu === 'collection' && (
            <div className="dock-popover" role="group" aria-label="Add to collection">
              {collections.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  className="btn-reset menu-item"
                  onClick={() => {
                    setMenu(null)
                    void saveCollection(c.name, hashes(), c)
                  }}
                >
                  {c.name}
                </button>
              ))}
              <button
                type="button"
                className="btn-reset menu-item"
                onClick={() => {
                  setMenu(null)
                  setDialog('collection')
                }}
              >
                <Plus size={14} /> New collection…
              </button>
            </div>
          )}
        </div>

        <button type="button" className="btn btn-sm" onClick={() => setDialog('tag')}>
          <Tag size={14} /> Tag
        </button>

        {aiReady && (
          <button
            type="button"
            className="btn btn-sm"
            title="Add every open AI-suggested tag of these photos as a real tag"
            onClick={() => void resolveAiTags(hashes(), 'accept')}
          >
            <Sparkles size={14} /> Accept suggestions
          </button>
        )}

        <span className="dock-sep" aria-hidden="true" />

        <div className="dock-menu">
          <button
            type="button"
            className="btn btn-sm btn-primary dock-export"
            aria-haspopup="true"
            aria-expanded={menu === 'export'}
            aria-busy={exporting || jsonBusy}
            onClick={() => toggle('export')}
          >
            {exporting && (
              <span
                className="export-progress"
                role="progressbar"
                aria-label="ZIP export"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(zipProgress * 100)}
                style={{ width: `${zipProgress * 100}%` }}
              />
            )}
            <Download size={14} />
            {exporting ? `Exporting ${Math.round(zipProgress * 100)}%` : 'Export'}
            <ChevronUp size={13} />
          </button>
          {menu === 'export' && (
            <div className="dock-popover" role="group" aria-label="Export the selection">
              <button
                type="button"
                className="btn-reset menu-item"
                disabled={exporting}
                onClick={() => {
                  setMenu(null)
                  void exportZip(hashes())
                }}
              >
                Photos as ZIP
              </button>
              <button
                type="button"
                className="btn-reset menu-item"
                disabled={jsonBusy}
                onClick={() => {
                  setMenu(null)
                  void exportJson(hashes())
                }}
              >
                Metadata as JSON
              </button>
            </div>
          )}
        </div>

        <button type="button" className="btn btn-sm icon-btn" onClick={clearSelection} aria-label="Clear selection" title="Clear selection (Esc)">
          <X size={14} />
        </button>
      </div>

      {dialog === 'tag' && (
        <NameDialog
          title={`Add a tag to ${plural}`}
          label="Tag"
          placeholder="e.g. highlights"
          submitLabel="Add tag"
          onSubmit={(tag) => batchPhotos({ photo_hashes: hashes(), action: 'add_tag', value: tag }, `Added #${tag} to ${plural}`)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'collection' && (
        <NameDialog
          title={`New collection from ${plural}`}
          label="Collection name"
          placeholder="e.g. Japan 2026"
          submitLabel="Create"
          onSubmit={(name) => saveCollection(name, hashes(), collections.find((c) => c.name === name))}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  )
}
