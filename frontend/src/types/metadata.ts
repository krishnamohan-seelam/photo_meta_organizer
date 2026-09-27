/**
 * TypeScript domain and API interfaces matching backend models.
 */

export interface GpsCoordinates {
  latitude: number
  longitude: number
  altitude?: number
  datum: string
}

export interface FileInfo {
  name: string
  path: string
  size_bytes: number
  mime_type: string
}

export interface Dimensions {
  width: number
  height: number
}

export interface ExifData {
  camera_make?: string
  camera_model?: string
  f_stop?: number
  exposure_time?: string
  iso?: number
  focal_length?: string
  captured_at?: string
  camera_profile: string
  location?: GpsCoordinates
  flash_fired?: boolean
  focal_length_35mm?: string
  white_balance_mode?: string
  exposure_program?: string
  metering_mode?: string
  orientation?: number
  raw_tags: Record<string, any>
}

export interface PhotoMetadata {
  file_hash: string
  file_info: FileInfo
  dimensions: Dimensions
  exif: ExifData
  labels: string[]
  rating?: number
  flagged: boolean
  added_at: string
}

export interface PaginatedPhotosResponse {
  items: PhotoMetadata[]
  total_count: number
  page: number
  page_size: number
  total_pages: number
}

export interface SearchRequest {
  search_term?: string
  date_start?: string
  date_end?: string
  camera_make?: string
  camera_model?: string
  /** Any of these makes, matched exactly. */
  camera_makes?: string[]
  /** `false`: only photos without a capture date. */
  has_capture_date?: boolean
  has_location?: boolean
  /** Members of this named collection. */
  collection?: string
  location_lat?: number
  location_lon?: number
  radius_km?: number
  /** AND: a photo must carry every tag (ADR D2). */
  tags?: string[]
  rating?: number
  flagged?: boolean
  sort_by?: SortField
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export type SortField = 'captured_at' | 'size_bytes' | 'camera_model' | 'file_name'

/** One search match reduced to what a selection needs (`POST /api/search/ids`). */
export interface PhotoId {
  file_hash: string
  size_bytes: number
}

export interface FacetCount {
  name: string
  count: number
}

export interface LibraryStats {
  total_count: number
  flagged_count: number
  geotagged_count: number
  undated_count: number
  total_bytes: number
  avg_megapixels: number
}

/** `GET /api/facets`: whole-library counts for filters and analytics. */
export interface Facets {
  cameras: FacetCount[]
  tags: FacetCount[]
  years: FacetCount[]
  isos: FacetCount[]
  stats: LibraryStats
}

export interface PatchPhotoRequest {
  rating?: number
  flagged?: boolean
  labels?: string[]
  add_tags?: string[]
  remove_tags?: string[]
}

export interface BatchPhotoRequest {
  photo_hashes: string[]
  action: 'add_tag' | 'remove_tag' | 'set_rating' | 'set_flag' | 'delete'
  value?: any
}

export interface BatchPhotoResponse {
  updated_count: number
  /** Present for the `delete` action, which is reported here instead of in `updated_count`. */
  deleted_count?: number
  action: string
  message: string
}

export interface Collection {
  name: string
  description: string
  photo_hashes: string[]
  updated_at: string
}
