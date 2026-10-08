import type { Facets, FacetCount, GeoClustersRequest, GeoClustersResponse, PaginatedPhotosResponse, PhotoId, PhotoMetadata, SearchRequest } from '../types/metadata'
import { SAMPLE_PHOTOS } from './samplePhotos'
import { boxContains, clusterPhotos } from '../utils/geo'

// `?demo=1` runs without a backend: this module plays the server's part over the sample
// library, with the same filter rules as the repository (tags AND, unknown dates last).

let photos: PhotoMetadata[] = [...SAMPLE_PHOTOS]

/** Keep a demo edit, so a refetch does not undo it. */
export function saveDemoPhoto(updated: PhotoMetadata): void {
  photos = photos.map((p) => (p.file_hash === updated.file_hash ? updated : p))
}

export function findDemoPhoto(hash: string): PhotoMetadata | undefined {
  return photos.find((p) => p.file_hash === hash)
}

function matches(p: PhotoMetadata, r: SearchRequest): boolean {
  const captured = p.exif.captured_at ?? null
  if (r.camera_makes && !r.camera_makes.includes(p.exif.camera_make ?? '')) return false
  if (r.camera_model && !(p.exif.camera_model ?? '').toLowerCase().includes(r.camera_model.toLowerCase())) return false
  if (r.tags && !r.tags.every((t) => p.labels.includes(t))) return false
  if (r.flagged !== undefined && r.flagged !== null && p.flagged !== r.flagged) return false
  if (r.rating !== undefined && r.rating !== null && p.rating !== r.rating) return false
  if (r.collection !== undefined) return false // the demo has no collections
  if (r.has_capture_date !== undefined && (captured !== null) !== r.has_capture_date) return false
  if (r.has_location !== undefined && Boolean(p.exif.location) !== r.has_location) return false
  if (r.within && !(p.exif.location && boxContains(r.within, p.exif.location.latitude, p.exif.location.longitude))) {
    return false
  }
  if (r.date_start && (!captured || captured < r.date_start)) return false
  if (r.date_end && (!captured || captured > r.date_end)) return false
  if (r.search_term) {
    const q = r.search_term.toLowerCase()
    const hay = [p.file_info.name, p.file_info.path, p.exif.camera_make, p.exif.camera_model, ...p.labels]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    if (!hay.includes(q)) return false
  }
  return true
}

function sortKey(p: PhotoMetadata, field: SearchRequest['sort_by']): string | number {
  switch (field) {
    case 'size_bytes':
      return p.file_info.size_bytes
    case 'camera_model':
      return p.exif.camera_model ?? ''
    case 'file_name':
      return p.file_info.name
    default:
      return p.exif.captured_at ?? ''
  }
}

function search(r: SearchRequest): PhotoMetadata[] {
  const dir = r.sort_order === 'desc' ? -1 : 1
  const field = r.sort_by ?? 'captured_at'
  const found = photos.filter((p) => matches(p, r))
  const undated = field === 'captured_at' ? found.filter((p) => !p.exif.captured_at) : []
  const sorted = found
    .filter((p) => !undated.includes(p))
    .sort((a, b) => {
      const ka = sortKey(a, field)
      const kb = sortKey(b, field)
      return ka < kb ? -dir : ka > kb ? dir : 0
    })
  return [...sorted, ...undated]
}

export async function demoSearch(r: SearchRequest): Promise<PaginatedPhotosResponse> {
  const all = search(r)
  const page = r.page ?? 1
  const size = r.page_size ?? 50
  return {
    items: all.slice((page - 1) * size, page * size),
    total_count: all.length,
    page,
    page_size: size,
    total_pages: Math.max(1, Math.ceil(all.length / size)),
  }
}

export async function demoGeoClusters(r: GeoClustersRequest): Promise<GeoClustersResponse> {
  const clusters = clusterPhotos(search(r), r.zoom ?? 2, r.bbox)
  return { clusters, total_count: clusters.reduce((sum, c) => sum + c.count, 0) }
}

export async function demoSearchIds(r: SearchRequest): Promise<PhotoId[]> {
  return search(r).map((p) => ({ file_hash: p.file_hash, size_bytes: p.file_info.size_bytes }))
}

function counts(values: (string | null | undefined)[]): FacetCount[] {
  const map = new Map<string, number>()
  for (const v of values) if (v) map.set(v, (map.get(v) ?? 0) + 1)
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, count]) => ({ name, count }))
}

function gpsBounds(all: PhotoMetadata[]): Facets['gps_bounds'] {
  const points = all.flatMap((p) => (p.exif.location ? [p.exif.location] : []))
  if (points.length === 0) return null
  const lats = points.map((l) => l.latitude)
  const lons = points.map((l) => l.longitude)
  return { min_lat: Math.min(...lats), max_lat: Math.max(...lats), min_lon: Math.min(...lons), max_lon: Math.max(...lons) }
}

export async function demoFacets(): Promise<Facets> {
  const total = photos.length
  return {
    cameras: counts(photos.map((p) => p.exif.camera_make)),
    tags: counts(photos.flatMap((p) => p.labels)),
    years: counts(photos.map((p) => p.exif.captured_at?.substring(0, 4))),
    isos: counts(photos.map((p) => (p.exif.iso ? String(p.exif.iso) : null))),
    gps_bounds: gpsBounds(photos),
    stats: {
      total_count: total,
      flagged_count: photos.filter((p) => p.flagged).length,
      geotagged_count: photos.filter((p) => p.exif.location).length,
      undated_count: photos.filter((p) => !p.exif.captured_at).length,
      total_bytes: photos.reduce((sum, p) => sum + p.file_info.size_bytes, 0),
      avg_megapixels: total ? photos.reduce((s, p) => s + (p.dimensions.width * p.dimensions.height) / 1e6, 0) / total : 0,
    },
  }
}
