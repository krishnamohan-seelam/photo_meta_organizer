import { getThumbnailUrl } from '../../api/client'
import type { GeoCluster } from '../../types/metadata'

/** Marker box in px; Leaflet anchors the icon at the bubble's centre. */
export const MARKER_SIZE = { width: 120, height: 64 }

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)
}

/** 999 stays 999, 1200 becomes 1.2k, so a big cluster still fits its bubble. */
export function formatCount(count: number): string {
  if (count < 1000) return String(count)
  if (count < 10_000) return `${(count / 1000).toFixed(1).replace(/\.0$/, '')}k`
  return `${Math.round(count / 1000)}k`
}

/**
 * Markup of one map marker: a thumbnail for a single photo, a count bubble for a group, and the
 * place name underneath when the server found one. Everything interpolated is escaped.
 */
export function markerHtml(cluster: GeoCluster): string {
  const label = cluster.label ? `<span class="pmo-marker-label">${escapeHtml(cluster.label)}</span>` : ''
  if (cluster.count === 1) {
    const src = escapeHtml(getThumbnailUrl(cluster.representative_hash, 96, 96))
    return `<span class="pmo-pin"><img src="${src}" alt="" loading="lazy" draggable="false"></span>${label}`
  }
  return `<span class="pmo-bubble">${formatCount(cluster.count)}</span>${label}`
}
