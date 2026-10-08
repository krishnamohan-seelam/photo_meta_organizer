import React from 'react'
import type { PatchPhotoRequest, PhotoMetadata } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { getThumbnailUrl } from '../../api/client'
import { useCuration } from '../../hooks/usePhotoMutations'
import { swapToPlaceholder } from '../../utils/placeholder'
import { usePhotoSearch } from '../../hooks/usePhotos'
import { demotion, groupByStage, promotion, type KanbanStage } from '../../utils/kanban'
import { LoadMore } from '../states/LoadMore'
import { Inbox, Star, CheckCircle, ChevronLeft, ChevronRight } from 'lucide-react'

const COLUMNS: { id: KanbanStage; title: string; icon: React.ReactNode; forward?: string; back?: string }[] = [
  { id: 'inbox', title: 'Inbox / Unsorted', icon: <Inbox size={16} color="var(--text-muted)" />, forward: 'Picks' },
  { id: 'picks', title: 'Picks & Flagged', icon: <Star size={16} color="var(--accent-primary)" />, forward: 'Export Ready', back: 'Inbox' },
  { id: 'export', title: 'Export Ready', icon: <CheckCircle size={16} color="var(--accent-success)" />, back: 'Picks' },
]

export const KanbanBoardView: React.FC = () => {
  // Stages are derived from the loaded pages (D4, utils/kanban.ts); more load from the footer.
  const { photos, totalCount, hasNextPage, isFetchingNextPage, fetchNextPage } = usePhotoSearch()
  const setInspectedHash = useUiStore((s) => s.setInspectedHash)
  const { patchPhoto } = useCuration()
  const stages = groupByStage(photos)

  // Optimistic: the card moves at once and moves back, with an error toast, if the save fails.
  const move = (photo: PhotoMetadata, patch: PatchPhotoRequest | null, to: string) => {
    if (patch) patchPhoto(photo.file_hash, patch, `Moved ${photo.file_info.name} to ${to}`)
  }

  return (
    <div className="kanban">
      <div className="kanban-board">
        {COLUMNS.map((col) => (
          <section key={col.id} className="kanban-column" aria-label={col.title}>
            <header className="kanban-column-header">
              <h2 className="kanban-column-title">
                {col.icon}
                <span>{col.title}</span>
              </h2>
              <span className="kanban-count">{stages[col.id].length}</span>
            </header>

            <div className="kanban-cards">
              {stages[col.id].map((item) => (
                <div key={item.file_hash} className="kanban-card">
                  <button
                    type="button"
                    className="btn-reset kanban-card-main"
                    aria-label={`Inspect ${item.file_info.name}`}
                    onClick={() => setInspectedHash(item.file_hash)}
                  >
                    <img
                      src={getThumbnailUrl(item.file_hash)}
                      alt=""
                      className="kanban-thumb"
                      onError={swapToPlaceholder}
                    />
                    <span className="kanban-card-text">
                      <span className="kanban-card-name">{item.file_info.name}</span>
                      <span className="kanban-card-meta">
                        {item.exif.camera_make || 'Unknown camera'} • {(item.file_info.size_bytes / 1048576).toFixed(1)} MB
                      </span>
                      <span className="kanban-card-stars">{item.rating ? '★'.repeat(item.rating) : ''}</span>
                    </span>
                  </button>
                  <div className="kanban-card-actions">
                    {col.back && (
                      <button
                        type="button"
                        className="btn btn-secondary kanban-action"
                        aria-label={`Move ${item.file_info.name} back to ${col.back}`}
                        onClick={() => move(item, demotion(item), col.back!)}
                      >
                        <ChevronLeft size={12} /> {col.back}
                      </button>
                    )}
                    {col.forward && (
                      <button
                        type="button"
                        className="btn btn-secondary kanban-action kanban-action-forward"
                        aria-label={`Move ${item.file_info.name} to ${col.forward}`}
                        onClick={() => move(item, promotion(item), col.forward!)}
                      >
                        {col.forward} <ChevronRight size={12} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      <LoadMore loaded={photos.length} total={totalCount} hasMore={Boolean(hasNextPage)} loading={isFetchingNextPage} onLoadMore={() => void fetchNextPage()} />
    </div>
  )
}
