import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'
import type {
  AiTag,
  AiTagBatchResponse,
  AnalysisStatus,
  BatchPhotoRequest,
  BatchPhotoResponse,
  AppConfig,
  Collection,
  Duplicates,
  FacetCount,
  Facets,
  GeoClustersRequest,
  GeoClustersResponse,
  Job,
  KeepAnalysed,
  PaginatedPhotosResponse,
  PatchPhotoRequest,
  PhotoId,
  PhotoMetadata,
  RemovedFile,
  ReviewItems,
  ReviewLabel,
  Root,
  RootSuggestions,
  SearchRequest,
  SyncFolderRequest,
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

/** The server's `detail` for a failed response, or null when it sent none (a proxy page, an empty body). */
async function detailOf(res: Response): Promise<string | null> {
  try {
    return detailToMessage((await res.json())?.detail)
  } catch {
    return null
  }
}

async function errorFromResponse(res: Response, action: string): Promise<ApiError> {
  const detail = await detailOf(res)
  return new ApiError(detail ?? `${action} failed (${res.status} ${res.statusText})`.trim(), res.status)
}

const UNREACHABLE = 'Cannot reach the backend. Is it running?'

/** A failed response that carried no `detail`: `call` words it with the action that failed. */
class NoDetailError extends ApiError {
  readonly statusText: string

  constructor(status: number, statusText: string) {
    super('', status)
    this.statusText = statusText
  }
}

/**
 * One error convention for every endpoint (ADR-003 R10): any non-2xx becomes an `ApiError`
 * carrying FastAPI's `detail` (a string, or a 422 list joined), and an unreachable server one
 * with a null status, so React Query's `onError` and the toasts see what they always saw.
 */
export const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return undefined
    const detail = await detailOf(response.clone())
    throw detail ? new ApiError(detail, response.status) : new NoDetailError(response.status, response.statusText)
  },
  onError() {
    return new ApiError(UNREACHABLE, null)
  },
}

/**
 * The typed client over the generated `schema.ts`: paths, parameters, bodies and responses all
 * come from the OpenAPI document. `fetch` is looked up per call and given a relative URL and a
 * plain init, so tests can stub `globalThis.fetch` as before.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === 'undefined' ? '' : window.location.origin,
  fetch: async (request: Request) => {
    const url = new URL(request.url)
    const hasBody = request.method !== 'GET' && request.method !== 'HEAD'
    const body = hasBody ? await request.text() : undefined
    const headers: Record<string, string> = {}
    request.headers.forEach((value, key) => (headers[key] = value))
    return globalThis.fetch(`${url.pathname}${url.search}`, { method: request.method, headers, ...(body ? { body } : {}) })
  },
})
api.use(errorMiddleware)

/** The data of a typed call; a failure without a `detail` is worded with `action`. */
async function call<T>(action: string, pending: Promise<{ data?: T }>): Promise<T> {
  try {
    return (await pending).data as T
  } catch (err) {
    if (err instanceof NoDetailError) {
      throw new ApiError(`${action} failed (${err.status} ${err.statusText})`.trim(), err.status)
    }
    throw err
  }
}

/** Text safe to show a user for anything a call might have thrown. */
export function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return 'Something went wrong'
}

export function searchPhotosApi(body: SearchRequest): Promise<PaginatedPhotosResponse> {
  return call('Loading photos', api.POST('/api/search', { body }))
}

/** Hash and size of every photo matching `body`, ignoring paging ("select all"). */
export function searchPhotoIdsApi(body: SearchRequest): Promise<PhotoId[]> {
  return call('Selecting photos', api.POST('/api/search/ids', { body }))
}

/** Clusters of the geotagged photos matching the filters, for the visible map area. */
export function fetchGeoClustersApi(body: GeoClustersRequest): Promise<GeoClustersResponse> {
  return call('Loading the map', api.POST('/api/geo/clusters', { body }))
}

export function fetchConfigApi(): Promise<AppConfig> {
  return call('Loading settings', api.GET('/api/config'))
}

export function fetchFacetsApi(): Promise<Facets> {
  return call('Loading library statistics', api.GET('/api/facets'))
}

export function getPhotoByHash(fileHash: string): Promise<PhotoMetadata> {
  return call('Loading the photo', api.GET('/api/photos/{file_hash}', { params: { path: { file_hash: fileHash } } }))
}

export function patchPhotoApi(fileHash: string, patch: PatchPhotoRequest): Promise<PhotoMetadata> {
  return call('Saving the photo', api.PATCH('/api/photos/{file_hash}', { params: { path: { file_hash: fileHash } }, body: patch }))
}

export function batchUpdatePhotosApi(body: BatchPhotoRequest): Promise<BatchPhotoResponse> {
  return call('Batch update', api.POST('/api/photos/batch', { body }))
}

export function fetchCollectionsApi(): Promise<Collection[]> {
  return call('Loading collections', api.GET('/api/collections'))
}

export function saveCollectionApi(name: string, photoHashes: string[], description: string = ''): Promise<Collection> {
  return call('Saving the collection', api.POST('/api/collections', { body: { name, photo_hashes: photoHashes, description } }))
}

/** Bring back photos removed a moment ago (undo). Ones already purged are gone and not counted. */
export function restorePhotosApi(photoHashes: string[]): Promise<{ restored_count: number }> {
  return call('Restoring the photos', api.POST('/api/photos/restore', { body: { photo_hashes: photoHashes } }))
}

/** Files removed from the library for good. Scans skip them until they change on disk or are restored. */
export function listRemovedApi(): Promise<RemovedFile[]> {
  return call('Loading removed files', api.GET('/api/removed'))
}

/** Stop ignoring these files; their folders are scanned so they are recorded again. */
export function restoreRemovedApi(paths: string[]): Promise<{ restored_count: number; job_ids: string[] }> {
  return call('Restoring the files', api.POST('/api/removed/restore', { body: { paths } }))
}

export function getThumbnailUrl(fileHash: string, width: number = 320, height: number = 320): string {
  return `${BASE_URL}/photos/${fileHash}/thumbnail?w=${width}&h=${height}`
}

/** Original file bytes. A browser cannot display HEIC or RAW from this; use getPreviewUrl to show one. */
export function getRawImageUrl(fileHash: string): string {
  return `${BASE_URL}/photos/${fileHash}/raw`
}

/** Large WebP (up to 2048 px) of any indexed format, HEIC and RAW included: for the viewer. */
export function getPreviewUrl(fileHash: string): string {
  return `${BASE_URL}/photos/${fileHash}/preview`
}

/** Not queued or running. An interrupted job is finished too: it waits for Resume or Dismiss. */
export function isJobFinished(job: Job): boolean {
  return job.status !== 'queued' && job.status !== 'running'
}

/** Start indexing a folder in the background. A 409 means a job is already running on it. */
export function startIndexJobApi(folderPath: string, numWorkers: number = 4): Promise<Job> {
  return call('Indexing the folder', api.POST('/api/index', { body: { folder_path: folderPath, num_workers: numWorkers } }))
}

/** Flags of an incremental sync; the server defaults match the CLI (cleanup off, new + modified on). */
export type SyncOptions = Omit<SyncFolderRequest, 'folder_path'>

/** Start an incremental sync of a folder. Only photos under that folder are affected. */
export function startSyncJobApi(folderPath: string, options: SyncOptions = {}): Promise<Job> {
  return call('Syncing the folder', api.POST('/api/sync', { body: { folder_path: folderPath, ...options } }))
}

/** Recent jobs, newest first. Stored in the library, so they survive a restart (one running then is `interrupted`). */
export function listJobsApi(): Promise<Job[]> {
  return call('Loading jobs', api.GET('/api/jobs'))
}

const jobPath = (jobId: string) => ({ params: { path: { job_id: jobId } } })

export function getJobApi(jobId: string): Promise<Job> {
  return call('Checking the job', api.GET('/api/jobs/{job_id}', jobPath(jobId)))
}

export function cancelJobApi(jobId: string): Promise<Job> {
  return call('Cancelling the job', api.POST('/api/jobs/{job_id}/cancel', jobPath(jobId)))
}

/** Ask a running job to stop and wait: it ends interrupted, and Resume carries on. 409 if it is not running. */
export function pauseJobApi(jobId: string): Promise<Job> {
  return call('Pausing the job', api.POST('/api/jobs/{job_id}/pause', jobPath(jobId)))
}

/** Run an interrupted job again with its original options. 409 if its folder is busy. */
export function resumeJobApi(jobId: string): Promise<Job> {
  return call('Resuming the job', api.POST('/api/jobs/{job_id}/resume', jobPath(jobId)))
}

/** Give up on an interrupted job; it ends cancelled. */
export function dismissJobApi(jobId: string): Promise<Job> {
  return call('Dismissing the job', api.POST('/api/jobs/{job_id}/dismiss', jobPath(jobId)))
}

/** Photos kept at more than one path, biggest saving first (a copy counts when it is on disk and not hidden). */
export function listDuplicatesApi(limit: number): Promise<Duplicates> {
  return call('Looking for duplicates', api.GET('/api/duplicates', { params: { query: { limit } } }))
}

/** Hide one copy from the duplicates view, or show it again. Only the library's record changes; no file is touched. */
export async function hideFileApi(path: string, hidden: boolean): Promise<void> {
  await call(hidden ? 'Hiding the copy' : 'Showing the copy', api.POST('/api/files/hide', { body: { path, hidden } }))
}

/** The folders the library rescans when the app starts; `online` is false while one cannot be read. */
export function listRootsApi(): Promise<Root[]> {
  return call('Loading folders', api.GET('/api/roots'))
}

/** Remember a folder and, unless `scan` is false, scan it now (`job_id` names the scan). */
export function addRootApi(folderPath: string, scan: boolean = true): Promise<Root> {
  return call('Adding the folder', api.POST('/api/roots', { body: { folder_path: folderPath, scan } }))
}

/** Stop rescanning a folder. Its photos stay in the library. */
export async function removeRootApi(path: string): Promise<void> {
  await call('Removing the folder', api.DELETE('/api/roots', { params: { query: { path } } }))
}

/** Folders found in an existing library's files, to offer as roots. Empty once there is a root or the offer was skipped. */
export function fetchRootSuggestionsApi(): Promise<RootSuggestions> {
  return call('Looking for your photo folders', api.GET('/api/roots/suggestions'))
}

/** A hint that a drive may have come or gone: the server tests the roots now instead of at its next timer. */
export async function recheckRootsApi(): Promise<void> {
  await call('Checking the folders', api.POST('/api/roots/recheck'))
}

/** Skip the suggested folders for good; watching stays off. */
export async function dismissRootSuggestionsApi(): Promise<void> {
  await call('Skipping the suggestions', api.POST('/api/roots/suggestions/dismiss'))
}

/** AI analysis (Phase 5). Status codes: 503 no `ai` extra, 409 no model / nothing analysed yet. */
export function fetchAnalysisStatusApi(): Promise<AnalysisStatus> {
  return call('Checking the AI setup', api.GET('/api/analysis/status'))
}

/** Start the model download. The body is the user's explicit consent; the server refuses without it. */
export function startModelDownloadApi(): Promise<Job> {
  return call('Downloading the AI model', api.POST('/api/analysis/model/download', { body: { accept: true } }))
}

/** Whether new photos are analysed automatically (off by default), and why it is or is not running now. */
export function fetchKeepAnalysedApi(): Promise<KeepAnalysed> {
  return call('Checking automatic analysis', api.GET('/api/analysis/keep'))
}

export function setKeepAnalysedApi(enabled: boolean): Promise<KeepAnalysed> {
  return call('Saving the setting', api.PUT('/api/analysis/keep', { body: { enabled } }))
}

export function startAnalysisApi(options: { reanalyze?: boolean } = {}): Promise<Job> {
  return call('Analyzing the library', api.POST('/api/analysis/run', { body: options }))
}

export function fetchAiTagCountsApi(): Promise<FacetCount[]> {
  return call('Loading suggested labels', api.GET('/api/ai-tags'))
}

const photoPath = (fileHash: string) => ({ path: { file_hash: fileHash } })

export function fetchAiTagsApi(fileHash: string): Promise<AiTag[]> {
  return call('Loading suggested tags', api.GET('/api/photos/{file_hash}/ai-tags', { params: photoPath(fileHash) }))
}

export function resolveAiTagApi(fileHash: string, label: string, action: 'accept' | 'reject' | 'reset'): Promise<AiTag[]> {
  return call(
    'Saving the tag decision',
    api.POST('/api/photos/{file_hash}/ai-tags', { params: photoPath(fileHash), body: { label, action } })
  )
}

/** Labels with open suggestions, the one with the most confident suggestion first. */
export function fetchReviewLabelsApi(): Promise<ReviewLabel[]> {
  return call('Loading suggestions to review', api.GET('/api/ai-tags/review'))
}

/** Open suggestions of one label, most confident first. 404 when the label has none left. */
export function fetchReviewItemsApi(label: string, limit: number): Promise<ReviewItems> {
  return call('Loading suggestions to review', api.GET('/api/ai-tags/review/items', { params: { query: { label, limit } } }))
}

/** How many open suggestions of a label reach a confidence: what accept-above would accept. */
export function fetchReviewCountApi(label: string, minConfidence: number): Promise<{ count: number }> {
  return call(
    'Counting suggestions',
    api.GET('/api/ai-tags/review/count', { params: { query: { label, min_confidence: minConfidence } } })
  )
}

/**
 * Accept a label on every photo whose open suggestion is at or above the confidence. `expectedCount` is the
 * number the user confirmed: if the server counts something else now it accepts nothing (409).
 */
export function acceptAboveApi(label: string, minConfidence: number, expectedCount: number): Promise<AiTagBatchResponse> {
  return call(
    'Accepting the suggestions',
    api.POST('/api/ai-tags/accept-above', { body: { label, min_confidence: minConfidence, expected_count: expectedCount } })
  )
}

export function resolveAiTagsBatchApi(photoHashes: string[], action: 'accept' | 'reject'): Promise<AiTagBatchResponse> {
  return call('Saving the tag decisions', api.POST('/api/ai-tags/batch', { body: { photo_hashes: photoHashes, action } }))
}

/** What a finished export download reports (PMO-28). */
export interface ExportResult {
  filename: string
  /** Photos in the file (ZIP: files bundled). */
  files: number | null
  /** Selected photos left out (ZIP: not indexed or file missing; listed in export_report.txt). */
  skipped: number
}

function filenameFrom(res: Response, fallback: string): string {
  const match = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '')
  return match ? match[1] : fallback
}

function intHeader(res: Response, name: string): number | null {
  const value = res.headers.get(name)
  return value === null ? null : Number(value)
}

/** Hand a downloaded blob to the browser as a file save. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Give the download a moment to start before the URL goes away.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/**
 * POST a download request and save the response as a file. `onProgress` gets a 0..1
 * fraction while the body streams in, when the server says how large it will be.
 */
async function download(
  path: string,
  action: string,
  body: unknown,
  fallbackName: string,
  onProgress?: (fraction: number) => void
): Promise<ExportResult> {
  // A streamed file, not JSON: plain fetch, with the same error convention as the typed calls.
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch {
    throw new ApiError(UNREACHABLE, null)
  }
  if (!res.ok) throw await errorFromResponse(res, action)

  const expected = intHeader(res, 'X-Export-Bytes')
  let blob: Blob
  if (res.body && expected && onProgress) {
    const reader = res.body.getReader()
    const chunks: BlobPart[] = []
    let received = 0
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      received += value.length
      // The archive is a little larger than the files it holds; hold at 99% until the end.
      onProgress(Math.min(received / expected, 0.99))
    }
    blob = new Blob(chunks, { type: res.headers.get('Content-Type') ?? 'application/octet-stream' })
  } else {
    blob = await res.blob()
  }
  onProgress?.(1)
  saveBlob(blob, filenameFrom(res, fallbackName))
  return {
    filename: filenameFrom(res, fallbackName),
    files: intHeader(res, 'X-Export-Files'),
    skipped: intHeader(res, 'X-Export-Skipped') ?? 0,
  }
}

/** Download the selected photos' original files as one ZIP (streamed; progress in bytes). */
export function exportZipApi(photoHashes: string[], onProgress?: (fraction: number) => void): Promise<ExportResult> {
  return download('/export/zip', 'Exporting the ZIP', { photo_hashes: photoHashes }, 'photos.zip', onProgress)
}

/** Download metadata as JSON: of `photoHashes`, or of the whole library when omitted. */
export function exportJsonApi(photoHashes?: string[]): Promise<ExportResult> {
  return download('/export/json', 'Exporting metadata', { photo_hashes: photoHashes ?? null }, 'photo-metadata.json')
}
