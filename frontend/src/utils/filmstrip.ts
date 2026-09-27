/**
 * The slice of a list of `total` items to show around `index`: at most `size` items,
 * centred on `index` where possible and shifted inward at either end.
 * Returns `[start, end)` indices.
 */
export function filmstripWindow(index: number, total: number, size: number): [number, number] {
  if (total <= size) return [0, total]
  const start = Math.min(Math.max(0, index - Math.floor(size / 2)), total - size)
  return [start, start + size]
}
