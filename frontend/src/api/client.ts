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

/** An API call that failed: either the server said no (`status` set) or it could not be reached (`status` null). */
export class ApiError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI sends `{detail: "text"}`, or for a 422 `{detail: [{loc, msg, type}, ...]}`. */
function detailToMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail || null
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === 'string') return d
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? (d as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
            : ''
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : String((d as { msg: string }).msg)
        }
        return null
      })
      .filter((m): m is string => Boolean(m))
    return parts.length ? parts.join('; ') : null
  }
  return null
}

async function errorFromResponse(res: Response, action: string): Promise<ApiError> {
  let detail: string | null = null
  try {
    detail = detailToMessage((await res.json())?.detail)
  } catch {
    // Not JSON (a proxy error page, an empty body): fall back to the status line.
  }
  return new ApiError(detail ?? `${action} failed (${res.status} ${res.statusText})`.trim(), res.status)
}

/** `fetch` plus one error convention for every endpoint: throws `ApiError`, with the server's `detail` if it sent one. */
async function request<T>(path: string, action: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the backend. Is it running?', null)
  }
  if (!res.ok) throw await errorFromResponse(res, action)
  return res.json() as Promise<T>
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

/** Text safe to show a user for anything a call might have thrown. */
export function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return 'Something went wrong'
}

export function fetchPhotos(
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
  return request(`/photos?${params}`, 'Loading photos')
}

export function searchPhotosApi(body: SearchRequest): Promise<PaginatedPhotosResponse> {
  return request('/search', 'Search', jsonInit('POST', body))
}

export function getPhotoByHash(fileHash: string): Promise<PhotoMetadata> {
  return request(`/photos/${fileHash}`, 'Loading the photo')
}

export function patchPhotoApi(fileHash: string, patch: PatchPhotoRequest): Promise<PhotoMetadata> {
  return request(`/photos/${fileHash}`, 'Saving the photo', jsonInit('PATCH', patch))
}

export function batchUpdatePhotosApi(body: BatchPhotoRequest): Promise<BatchPhotoResponse> {
  return request('/photos/batch', 'Batch update', jsonInit('POST', body))
}

export function fetchCollectionsApi(): Promise<Collection[]> {
  return request('/collections', 'Loading collections')
}

export function saveCollectionApi(
  name: string,
  photoHashes: string[],
  description: string = ''
): Promise<Collection> {
  return request(
    '/collections',
    'Saving the collection',
    jsonInit('POST', { name, photo_hashes: photoHashes, description })
  )
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

export function indexFolderApi(folderPath: string, numWorkers: number = 4): Promise<IndexFolderResponse> {
  return request(
    '/index',
    'Indexing the folder',
    jsonInit('POST', { folder_path: folderPath, num_workers: numWorkers })
  )
}
