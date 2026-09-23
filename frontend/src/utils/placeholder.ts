/**
 * Shown when a thumbnail fails to load (RAW/HEIC the backend cannot decode, a moved file).
 * An inline data URI, so a broken thumbnail never causes a second network request.
 */
export const PLACEHOLDER_SRC =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">' +
      '<rect width="400" height="300" fill="#1e293b"/>' +
      '<g fill="none" stroke="#64748b" stroke-width="8" stroke-linecap="round" stroke-linejoin="round">' +
      '<rect x="140" y="95" width="120" height="90" rx="10"/>' +
      '<circle cx="200" cy="140" r="24"/>' +
      '<path d="M170 95l8-14h44l8 14"/></g>' +
      '<text x="200" y="228" fill="#64748b" font-family="sans-serif" font-size="18" text-anchor="middle">No preview</text>' +
      '</svg>'
  )

/** `onError` handler for an `<img>`: swap in the placeholder once, and never loop if that fails too. */
export function swapToPlaceholder(e: { currentTarget: HTMLImageElement }): void {
  const img = e.currentTarget
  if (img.dataset.fallback) return
  img.dataset.fallback = '1'
  img.src = PLACEHOLDER_SRC
}
