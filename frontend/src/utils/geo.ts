import type { BoundingBox, GeoCluster, PhotoMetadata } from '../types/metadata'

/** Highest zoom the map offers (and the API accepts). */
export const MAX_ZOOM = 18

/** Keep in step with `application/geo.py`: a ~64 px marker per 256 px tile. */
const CLUSTER_PIXELS = 64
const TILE_PIXELS = 256

/** Side, in degrees, of the grid cell that clusters photos at a Web-Mercator zoom level. */
export function cellDegreesForZoom(zoom: number): number {
  const z = Math.max(0, Math.min(20, Math.round(zoom)))
  return ((360 / 2 ** z) * CLUSTER_PIXELS) / TILE_PIXELS
}

/** Longitude folded into [-180, 180]; Leaflet reports > 180 after panning past the date line. */
export function wrapLongitude(lon: number): number {
  if (lon >= -180 && lon <= 180) return lon
  return ((((lon + 180) % 360) + 360) % 360) - 180
}

/** A map viewport as the API takes it: latitude clamped, longitude wrapped, a full world as -180..180. */
export function normalizeBounds(b: BoundingBox): BoundingBox {
  const south = Math.max(-90, Math.min(90, b.south))
  const north = Math.max(-90, Math.min(90, b.north))
  if (b.east - b.west >= 360) return { south, west: -180, north, east: 180 }
  return { south, west: wrapLongitude(b.west), north, east: wrapLongitude(b.east) }
}

/** The viewport grown by `fraction` of its size on each side, so a small pan does not blank the map. */
export function padBounds(b: BoundingBox, fraction: number): BoundingBox {
  // West > east means the view crosses the date line: measure it on an unwrapped longitude.
  const east = b.west <= b.east ? b.east : b.east + 360
  const lonSpan = east - b.west
  return normalizeBounds({
    south: b.south - (b.north - b.south) * fraction,
    north: b.north + (b.north - b.south) * fraction,
    west: b.west - lonSpan * fraction,
    east: east + lonSpan * fraction,
  })
}

/** Zoom level to move to when a cluster is clicked. */
export function zoomIntoCluster(current: number): number {
  return Math.min(MAX_ZOOM, Math.floor(current) + 2)
}

/** "7 photos" / "1 photo", with the place when the server named one. */
export function clusterTitle(cluster: Pick<GeoCluster, 'count' | 'label'>): string {
  const photos = `${cluster.count} ${cluster.count === 1 ? 'photo' : 'photos'}`
  return cluster.label ? `${cluster.label}: ${photos}` : photos
}

/** Whether a point is inside a box; `west > east` means the box crosses the date line. */
export function boxContains(b: BoundingBox, lat: number, lon: number): boolean {
  if (lat < b.south || lat > b.north) return false
  return b.west <= b.east ? lon >= b.west && lon <= b.east : lon >= b.west || lon <= b.east
}

/**
 * The same grid clustering the server does in SQL, over photos already in memory (`?demo=1`).
 * Positions are cell means; the representative is the most recently captured member.
 */
export function clusterPhotos(photos: PhotoMetadata[], zoom: number, bbox?: BoundingBox | null): GeoCluster[] {
  const cell = cellDegreesForZoom(zoom)
  const cells = new Map<string, PhotoMetadata[]>()
  for (const p of photos) {
    const loc = p.exif.location
    if (!loc) continue
    if (bbox && !boxContains(bbox, loc.latitude, loc.longitude)) continue
    const key = `${Math.floor((loc.latitude + 90) / cell)}:${Math.floor((loc.longitude + 180) / cell)}`
    const members = cells.get(key)
    if (members) members.push(p)
    else cells.set(key, [p])
  }
  return [...cells.values()]
    .map((members) => {
      const newest = members.reduce((a, b) => ((b.exif.captured_at ?? '') > (a.exif.captured_at ?? '') ? b : a))
      return {
        latitude: members.reduce((s, m) => s + (m.exif.location?.latitude ?? 0), 0) / members.length,
        longitude: members.reduce((s, m) => s + (m.exif.location?.longitude ?? 0), 0) / members.length,
        count: members.length,
        representative_hash: newest.file_hash,
        label: null,
      }
    })
    .sort((a, b) => b.count - a.count || a.representative_hash.localeCompare(b.representative_hash))
}
