import React from 'react'
import { Sparkles, X } from 'lucide-react'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { useViewStore, type SemanticQuery } from '../../stores/useViewStore'

function semanticTitle(q: SemanticQuery): string {
  return q.kind === 'text' ? `Meaning: “${q.text}”` : `Like ${q.name || 'this photo'}`
}

/**
 * Above the Library while a search by meaning ranks it (ADR-003 R9): what it is ranked by, how
 * many close matches there are, a switch to every analysed photo, and Clear. The grid, table,
 * timeline, Select All and export show the ranked photos like any other search.
 */
export const SemanticBanner: React.FC = () => {
  const semantic = useViewStore((s) => s.semantic)
  const setSemantic = useViewStore((s) => s.setSemantic)
  const { totalCount, data } = usePhotoSearch()
  if (!semantic) return null
  const everything = Boolean(semantic.everything)
  return (
    <div className="semantic-head" role="status">
      <Sparkles size={14} aria-hidden="true" />
      <span>
        {semanticTitle(semantic)}
        {data && ` · ${totalCount} ${everything ? 'ranked' : `close match${totalCount === 1 ? '' : 'es'}`}`}
      </span>
      <button type="button" className="btn-reset link-btn" onClick={() => setSemantic({ ...semantic, everything: !everything })}>
        {everything ? 'Close matches only' : 'Show everything'}
      </button>
      <button type="button" className="btn-reset link-btn" onClick={() => setSemantic(null)}>
        <X size={12} /> Clear
      </button>
    </div>
  )
}
