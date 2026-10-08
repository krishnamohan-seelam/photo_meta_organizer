/** Used when a photo has no usable dimensions. */
export const FALLBACK_RATIO = 3 / 2
/** Narrowest and widest ratio a tile may have, so a panorama cannot take a whole row alone. */
export const MIN_RATIO = 0.4
export const MAX_RATIO = 3.5

export interface JustifiedRow {
  /** Index of the first item in the row. */
  start: number
  /** One past the last item. */
  end: number
  /** Height of every tile in the row; a tile is `ratio * height` wide. */
  height: number
}

/** A ratio a tile can be laid out with: invalid values become 3:2, extremes are clamped. */
export function clampRatio(ratio: number): number {
  if (!Number.isFinite(ratio) || ratio <= 0) return FALLBACK_RATIO
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio))
}

/**
 * Justified rows (FR-1c.2): each row takes items until its width at `targetHeight` reaches the
 * container, then its height is scaled so it fills the width exactly. The last row keeps the
 * target height (it is not stretched) unless it would overflow. Pure, so it is memoised by callers.
 */
export function justifiedRows(
  items: readonly { ratio: number }[],
  containerWidth: number,
  targetHeight: number,
  gap = 4
): JustifiedRow[] {
  if (containerWidth <= 0 || targetHeight <= 0) return []
  const rows: JustifiedRow[] = []
  let start = 0
  let ratioSum = 0
  for (let i = 0; i < items.length; i++) {
    ratioSum += clampRatio(items[i].ratio)
    const count = i - start + 1
    const gaps = gap * (count - 1)
    if (ratioSum * targetHeight + gaps >= containerWidth) {
      rows.push({ start, end: i + 1, height: (containerWidth - gaps) / ratioSum })
      start = i + 1
      ratioSum = 0
    }
  }
  if (start < items.length) {
    const gaps = gap * (items.length - start - 1)
    rows.push({ start, end: items.length, height: Math.min(targetHeight, (containerWidth - gaps) / ratioSum) })
  }
  return rows
}

/** Width of a laid-out row, gaps included. */
export function rowWidth(items: readonly { ratio: number }[], row: JustifiedRow, gap = 4): number {
  let width = gap * (row.end - row.start - 1)
  for (let i = row.start; i < row.end; i++) width += clampRatio(items[i].ratio) * row.height
  return width
}
