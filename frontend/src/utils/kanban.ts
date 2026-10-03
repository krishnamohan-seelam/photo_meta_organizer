import type { PatchPhotoRequest, PhotoMetadata } from '../types/metadata'

/**
 * Kanban stages are derived from rating, flag and the `export` tag (decision D4: no stored stage).
 * Each photo is in exactly one stage; the first rule that matches wins:
 *   Export Ready: rated 5 or tagged `export`
 *   Picks:        flagged or rated 4
 *   Inbox:        everything else (unrated or rated 1-3, not flagged)
 */
export type KanbanStage = 'inbox' | 'picks' | 'export'

export const EXPORT_TAG = 'export'

export function kanbanStage(photo: Pick<PhotoMetadata, 'rating' | 'flagged' | 'labels'>): KanbanStage {
  const rating = photo.rating ?? 0
  if (rating === 5 || photo.labels.includes(EXPORT_TAG)) return 'export'
  if (photo.flagged || rating === 4) return 'picks'
  return 'inbox'
}

export function groupByStage<T extends Pick<PhotoMetadata, 'rating' | 'flagged' | 'labels'>>(
  photos: T[],
): Record<KanbanStage, T[]> {
  const groups: Record<KanbanStage, T[]> = { inbox: [], picks: [], export: [] }
  for (const photo of photos) groups[kanbanStage(photo)].push(photo)
  return groups
}

/** The edit that moves a photo one stage forward, or `null` from the last stage. */
export function promotion(photo: Pick<PhotoMetadata, 'rating' | 'flagged' | 'labels'>): PatchPhotoRequest | null {
  switch (kanbanStage(photo)) {
    case 'inbox':
      return { flagged: true, rating: 4 }
    case 'picks':
      return { rating: 5, add_tags: [EXPORT_TAG] }
    case 'export':
      return null
  }
}

/**
 * The edit that moves a photo one stage back, or `null` from the first stage. It changes only what
 * keeps the photo in its current stage: from Export Ready the 5th star and the `export` tag go (it
 * stays flagged as a pick); from Picks the flag goes and a 4-5 star rating drops to 3.
 */
export function demotion(photo: Pick<PhotoMetadata, 'rating' | 'flagged' | 'labels'>): PatchPhotoRequest | null {
  const rating = photo.rating ?? 0
  switch (kanbanStage(photo)) {
    case 'inbox':
      return null
    case 'picks':
      return rating >= 4 ? { flagged: false, rating: 3 } : { flagged: false }
    case 'export': {
      const patch: PatchPhotoRequest = { flagged: true }
      if (rating === 5) patch.rating = 4
      if (photo.labels.includes(EXPORT_TAG)) patch.remove_tags = [EXPORT_TAG]
      return patch
    }
  }
}
