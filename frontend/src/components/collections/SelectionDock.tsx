import React, { useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { useUiStore } from '../../stores/useUiStore'
import type { PhotoMetadata } from '../../types/metadata'
import { useCuration } from '../../hooks/usePhotoMutations'
import { Tag, Flag, Download, X } from 'lucide-react'

interface SelectionDockProps {
  photos: PhotoMetadata[]
}

export const SelectionDock: React.FC<SelectionDockProps> = ({ photos }) => {
  const { selectedHashes, clearSelection } = useSelectionStore(useShallow((s) => ({ selectedHashes: s.selectedHashes, clearSelection: s.clearSelection })))
  const { showToast } = useUiStore(useShallow((s) => ({ showToast: s.showToast })))
  const { batchPhotos } = useCuration()
  const [tagModalOpen, setTagModalOpen] = useState(false)
  const [newTag, setNewTag] = useState('')

  const selectedCount = selectedHashes.size
  if (selectedCount === 0) return null

  // Calculate cumulative size
  const totalBytes = photos
    .filter((p) => selectedHashes.has(p.file_hash))
    .reduce((acc, p) => acc + p.file_info.size_bytes, 0)

  const handleBatchTag = async () => {
    const tag = newTag.trim()
    if (!tag) return
    const saved = await batchPhotos(
      { photo_hashes: Array.from(selectedHashes), action: 'add_tag', value: tag },
      `Added tag #${tag} to ${selectedCount} photos`
    )
    // Keep the dialog (and what was typed) open on failure so the user can retry.
    if (saved) {
      setTagModalOpen(false)
      setNewTag('')
    }
  }

  const handleBatchFlag = () =>
    batchPhotos(
      { photo_hashes: Array.from(selectedHashes), action: 'set_flag', value: true },
      `Flagged ${selectedCount} photos as Picks`
    )

  // ZIP export is not built yet (tracked as PMO-30). Say so instead of pretending a download happened.
  const handleExportZip = () => showToast('ZIP export is not available yet', 'error')

  return (
    <>
      <div className="selection-dock show">
        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>{selectedCount} selected</span>
          <span style={{ color: 'var(--text-muted)' }}>•</span>
          <span style={{ color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)' }}>
            {(totalBytes / 1048576).toFixed(1)} MB
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={() => setTagModalOpen(true)} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
            <Tag size={13} />
            <span>Add Tag</span>
          </button>

          <button className="btn btn-secondary" onClick={handleBatchFlag} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
            <Flag size={13} />
            <span>Flag All</span>
          </button>

          <button className="btn btn-primary" onClick={handleExportZip} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
            <Download size={13} />
            <span>Export ZIP</span>
          </button>

          <button className="btn btn-secondary" onClick={clearSelection} style={{ padding: '4px 8px', fontSize: '0.75rem' }}>
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Batch Tagging Modal */}
      {tagModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            zIndex: 99999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => setTagModalOpen(false)}
        >
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
              width: '320px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Add Tag to {selectedCount} Photos</div>
            <input
              type="text"
              autoFocus
              placeholder="e.g. tokyo-curated, highlights"
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleBatchTag()}
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setTagModalOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleBatchTag}>
                Apply Tag
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
