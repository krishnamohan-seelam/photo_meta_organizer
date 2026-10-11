import React from 'react'
import { Check, Sparkles, X } from 'lucide-react'
import { useAnalysisStatus, usePhotoAiTags, useResolveAiTag, useSemanticSearch } from '../../hooks/useAnalysis'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl } from '../../api/client'
import { swapToPlaceholder } from '../../utils/placeholder'
import { formatScore } from '../../utils/analysis'

const SIMILAR_SHOWN = 6

/**
 * AI suggestions for the inspected photo: tags to accept or dismiss, and look-alikes. Renders
 * nothing until the photo has been analysed, so a library without AI looks exactly as before.
 */
export const AiTagsSection: React.FC<{ hash: string; name: string }> = ({ hash, name }) => {
  const status = useAnalysisStatus()
  const enabled = Boolean(status?.runtime_installed && status.model_installed && status.analyzed_photos > 0)
  const { data: tags = [] } = usePhotoAiTags(hash, enabled)
  const resolve = useResolveAiTag(hash)
  const setSemantic = useUiStore((s) => s.setSemantic)
  const setActiveView = useUiStore((s) => s.setActiveView)
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const similar = useSemanticSearch(enabled ? { kind: 'like', hash, name } : null, SIMILAR_SHOWN + 1, false)

  const open = tags.filter((t) => t.status === 'suggested')
  const hits = (similar.data?.items ?? []).filter((h) => h.photo.file_hash !== hash).slice(0, SIMILAR_SHOWN)
  if (!enabled || (open.length === 0 && hits.length === 0)) return null

  return (
    <section className="insp-sec" aria-label="AI suggestions">
      <h3>
        Suggested <span>by AI, on this computer</span>
      </h3>
      {open.length > 0 && (
        <div className="insp-tags">
          {open.map((t) => (
            <span key={t.label} className="chip chip-ai" title={`${formatScore(t.confidence)} confident`}>
              {t.label}
              <button
                type="button"
                className="btn-reset"
                aria-label={`Accept tag ${t.label}`}
                disabled={resolve.isPending}
                onClick={() => resolve.mutate({ label: t.label, action: 'accept' })}
              >
                <Check size={12} />
              </button>
              <button
                type="button"
                className="btn-reset"
                aria-label={`Dismiss suggestion ${t.label}`}
                disabled={resolve.isPending}
                onClick={() => resolve.mutate({ label: t.label, action: 'reject' })}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      {hits.length > 0 && (
        <>
          <div className="similar-head">
            Similar photos
            <button
              type="button"
              className="btn-reset link-btn"
              onClick={() => {
                setSemantic({ kind: 'like', hash, name })
                setActiveView('studio')
              }}
            >
              <Sparkles size={11} /> See all
            </button>
          </div>
          <div className="similar-strip">
            {hits.map((h) => (
              <button
                key={h.photo.file_hash}
                type="button"
                className="btn-reset similar-thumb"
                aria-label={`Open ${h.photo.file_info.name}, ${formatScore(h.score)} similar`}
                onClick={() => setInspectedHash(h.photo.file_hash)}
              >
                <img src={getThumbnailUrl(h.photo.file_hash, 160, 160)} alt="" loading="lazy" onError={swapToPlaceholder} />
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
