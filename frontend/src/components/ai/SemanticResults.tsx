import React from 'react'
import { Sparkles, X } from 'lucide-react'
import { useSemanticSearch } from '../../hooks/useAnalysis'
import { useUiStore } from '../../stores/useUiStore'
import type { SemanticQuery } from '../../stores/useUiStore'
import { useSelectionStore } from '../../stores/useSelectionStore'
import { getThumbnailUrl, errorMessage } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { formatScore } from '../../utils/analysis'
import type { SemanticHit } from '../../types/metadata'

const TILE = 190

function semanticTitle(q: SemanticQuery): string {
  return q.kind === 'text' ? `Meaning: “${q.text}”` : `Like ${q.name}`
}

const Tile: React.FC<{ hit: SemanticHit }> = ({ hit }) => {
  const photo = hit.photo
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const inspected = useUiStore((s) => s.inspectedHash === photo.file_hash)
  const selected = useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))
  const toggleSelect = useSelectionStore((s) => s.toggleSelect)
  return (
    <div className={`tile${selected ? ' sel' : ''}${inspected ? ' cur' : ''}`} style={{ width: TILE, height: TILE }}>
      <button
        type="button"
        className="btn-reset tile-hit"
        aria-label={`${photo.file_info.name}, ${formatScore(hit.score)} match`}
        aria-current={inspected ? 'true' : undefined}
        title={`${photo.file_info.name} · Ctrl-click to select`}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) toggleSelect(photo.file_hash, photo.file_info.size_bytes)
          else setInspectedHash(photo.file_hash)
        }}
      />
      <img src={getThumbnailUrl(photo.file_hash, TILE * 2, TILE * 2)} alt="" loading="lazy" onError={swapToPlaceholder} />
      <span className="tile-score num" aria-hidden="true">
        {formatScore(hit.score)}
      </span>
    </div>
  )
}

/**
 * The Library's list while a search by meaning is active: the best matches, best first, under the
 * current filters. Replaces the grid; clearing the query brings the grid back.
 */
export const SemanticResults: React.FC<{ query: SemanticQuery }> = ({ query }) => {
  const { data, isLoading, error } = useSemanticSearch(query)
  const setSemantic = useUiStore((s) => s.setSemantic)
  const setAiDialogOpen = useUiStore((s) => s.setAiDialogOpen)
  const hits = data?.items ?? []

  return (
    <div className="semantic-results">
      <div className="semantic-head">
        <Sparkles size={14} aria-hidden="true" />
        <span role="status">
          {semanticTitle(query)}
          {data && ` · ${hits.length} match${hits.length === 1 ? '' : 'es'}`}
        </span>
        <button type="button" className="btn-reset link-btn" onClick={() => setSemantic(null)}>
          <X size={12} /> Clear
        </button>
      </div>
      {isLoading && <p className="lib-empty">Searching…</p>}
      {error && (
        <p className="lib-empty" role="alert">
          {errorMessage(error)}{' '}
          <button type="button" className="btn-reset link-btn" onClick={() => setAiDialogOpen(true)}>
            Set up AI search
          </button>
        </p>
      )}
      {data && hits.length === 0 && <p className="lib-empty">Nothing matches under the current filters.</p>}
      <div className="semantic-grid">
        {hits.map((hit) => (
          <Tile key={hit.photo.file_hash} hit={hit} />
        ))}
      </div>
    </div>
  )
}
