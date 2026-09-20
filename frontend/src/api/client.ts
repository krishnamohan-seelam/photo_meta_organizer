import type {
  BatchPhotoRequest,
  BatchPhotoResponse,
  Collection,
  PaginatedPhotosResponse,
  PatchPhotoRequest,
  PhotoMetadata,
  SearchRequest,
} from '../types/metadata'

const BASE_URL = '/api'

export async function fetchPhotos(
  page: number = 1,
  pageSize: number = 50,
  sortBy: string = 'captured_at',
  sortOrder: 'asc' | 'desc' = 'desc'
): Promise<PaginatedPhotosResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
    sort_by: sortBy,
    sort_order: sortOrder,
  })
  const res = await fetch(`${BASE_URL}/photos?${params}`)
  if (!res.ok) throw new Error(`Failed to list photos: ${res.statusText}`)
  return res.json()
}

export async function searchPhotosApi(request: SearchRequest): Promise<PaginatedPhotosResponse> {
  const res = await fetch(`${BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Search failed: ${res.statusText}`)
  return res.json()
}

export async function getPhotoByHash(fileHash: string): Promise<PhotoMetadata> {
  const res = await fetch(`${BASE_URL}/photos/${fileHash}`)
  if (!res.ok) throw new Error(`Photo ${fileHash} not found`)
  return res.json()
}

export async function patchPhotoApi(fileHash: string, patch: PatchPhotoRequest): Promise<PhotoMetadata> {
  const res = await fetch(`${BASE_URL}/photos/${fileHash}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to update photo: ${res.statusText}`)
  return res.json()
}

export async function batchUpdatePhotosApi(request: BatchPhotoRequest): Promise<BatchPhotoResponse> {
  const res = await fetch(`${BASE_URL}/photos/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error(`Batch update failed: ${res.statusText}`)
  return res.json()
}

export async function fetchCollectionsApi(): Promise<Collection[]> {
  const res = await fetch(`${BASE_URL}/collections`)
  if (!res.ok) throw new Error(`Failed to fetch collections: ${res.statusText}`)
  return res.json()
}

export async function saveCollectionApi(
  name: string,
  photoHashes: string[],
  description: string = ''
): Promise<Collection> {
  const res = await fetch(`${BASE_URL}/collections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, photo_hashes: photoHashes, description }),
  })
  if (!res.ok) throw new Error(`Failed to save collection: ${res.statusText}`)
  return res.json()
}

export function getThumbnailUrl(fileHash: string, width: number = 320, height: number = 320): string {
  return `${BASE_URL}/photos/${fileHash}/thumbnail?w=${width}&h=${height}`
}

export function getRawImageUrl(fileHash: string): string {
  return `${BASE_URL}/photos/${fileHash}/raw`
}

export interface IndexFolderResponse {
  indexed_count: number
  folder_path: string
  message: string
}

export async function indexFolderApi(
  folderPath: string,
  numWorkers: number = 4
): Promise<IndexFolderResponse> {
  const res = await fetch(`${BASE_URL}/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_path: folderPath, num_workers: numWorkers }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `Failed to index folder: ${res.statusText}`)
  }
  return res.json()
}

