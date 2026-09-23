import type { BatchPhotoRequest, PatchPhotoRequest, PhotoMetadata } from '../types/metadata'

/** Append `additions` to `current`, keeping order and dropping duplicates (mirrors the backend's `merge_labels`). */
function mergeLabels(current: string[], additions: string[]): string[] {
  const merged = [...new Set(current)]
  for (const tag of additions) if (!merged.includes(tag)) merged.push(tag)
  return merged
}

/**
 * The photo as the server will hold it after `patch`. Same order as the backend
 * (rating, flag, labels, add_tags, remove_tags), so an optimistic update and the confirmed record agree.
 */
export function applyPatch(photo: PhotoMetadata, patch: PatchPhotoRequest): PhotoMetadata {
  let labels = photo.labels
  if (patch.labels) labels = mergeLabels([], patch.labels)
  if (patch.add_tags) labels = mergeLabels(labels, patch.add_tags)
  if (patch.remove_tags) {
    const removed = new Set(patch.remove_tags)
    labels = labels.filter((t) => !removed.has(t))
  }
  return {
    ...photo,
    ...(patch.rating !== undefined && { rating: patch.rating }),
    ...(patch.flagged !== undefined && { flagged: patch.flagged }),
    labels,
  }
}

/** The photo as the server will hold it after one batch action (`delete` is not handled here: the record goes away). */
export function applyBatchAction(
  photo: PhotoMetadata,
  action: Exclude<BatchPhotoRequest['action'], 'delete'>,
  value: unknown
): PhotoMetadata {
  switch (action) {
    case 'add_tag':
      return applyPatch(photo, { add_tags: [String(value).trim()] })
    case 'remove_tag':
      return applyPatch(photo, { remove_tags: [String(value).trim()] })
    case 'set_rating':
      return applyPatch(photo, { rating: value as number })
    case 'set_flag':
      return applyPatch(photo, { flagged: Boolean(value) })
  }
}
