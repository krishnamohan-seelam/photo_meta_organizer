import React, { useCallback } from 'react'
import { Sparkles, X } from 'lucide-react'
import { useSemanticPhotos } from '../../hooks/useAnalysis'
import { useLibraryHotkeys } from '../../hooks/useLibraryHotkeys'
import { SEMANTIC_MAX, useUiStore } from '../../stores/useUiStore'
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

const Tile: React.FC<{ hit: SemanticHit; index: number }> = ({ hit, index }) => {
  const photo = hit.photo
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const setLightboxIndex = useUiStore((s) => s.setLightboxIndex)
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
        title={`${photo.file_info.name} · double-click or Enter to open · Ctrl-click to select`}
        data-photo-index={index}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) toggleSelect(photo.file_hash, photo.file_info.size_bytes)
          else setInspectedHash(photo.file_hash)
        }}
        onDoubleClick={() => setLightboxIndex(index)}
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
 * current filters. Opens in the viewer and takes the same keys as the grid; "Show more" asks for
 * more matches (the server ranks the whole library, so it is a larger top-k, not a next page).
 * Clearing the query brings the grid back.
 */
export const SemanticResults: React.FC = () => {
  const { semantic, limit, query, hits, photos } = useSemanticPhotos()
  const setSemantic = useUiStore((s) => s.setSemantic)
  const showMore = useUiStore((s) => s.showMoreSemantic)
  const setAiDialogOpen = useUiStore((s) => s.setAiDialogOpen)

  const reveal = useCallback((index: number) => {
    document.querySelector(`[data-photo-index="${index}"]`)?.scrollIntoView?.({ block: 'nearest' })
  }, [])
  useLibraryHotkeys({ photos, reveal, loadMore: null })

  if (!semantic) return null
  // A full page back means there may be more to ask for.
  const canShowMore = hits.length >= limit && limit < SEMANTIC_MAX

  return (
    <div className="semantic-results">
      <div className="semantic-head">
        <Sparkles size={14} aria-hidden="true" />
        <span role="status">
          {semanticTitle(semantic)}
          {query.data && ` · ${hits.length} match${hits.length === 1 ? '' : 'es'}`}
        </span>
        <button type="button" className="btn-reset link-btn" onClick={() => setSemantic(null)}>
          <X size={12} /> Clear
        </button>
      </div>
      {query.isLoading && <p className="lib-empty">Searching…</p>}
      {query.error && (
        <p className="lib-empty" role="alert">
          {errorMessage(query.error)}{' '}
          <button type="button" className="btn-reset link-btn" onClick={() => setAiDialogOpen(true)}>
            Set up AI search
          </button>
        </p>
      )}
      {query.data && hits.length === 0 && <p className="lib-empty">Nothing matches under the current filters.</p>}
      <div className="semantic-grid">
        {hits.map((hit, i) => (
          <Tile key={hit.photo.file_hash} hit={hit} index={i} />
        ))}
      </div>
      {canShowMore && (
        <div className="semantic-more">
          <button type="button" className="btn btn-secondary" onClick={showMore} disabled={query.isFetching}>
            {query.isFetching ? 'Loading…' : 'Show more'}
          </button>
        </div>
      )}
    </div>
  )
}
