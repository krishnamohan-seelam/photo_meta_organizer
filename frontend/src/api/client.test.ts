import { describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, getPhotoByHash, patchPhotoApi, startSyncJobApi } from './client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const err = await promise.then(
    () => null,
    (e: unknown) => e,
  )
  expect(err).toBeInstanceOf(ApiError)
  return err as ApiError
}

describe('API client errors (PMO-15)', () => {
  it("shows FastAPI's string detail", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: "Photo with hash 'x' not found." }, 404)))
    const err = await failure(getPhotoByHash('x'))
    expect(err.message).toBe("Photo with hash 'x' not found.")
    expect(err.status).toBe(404)
  })

  it('joins a 422 validation list into one readable message', async () => {
    const detail = [
      { loc: ['body', 'rating'], msg: 'Input should be less than or equal to 5', type: 'less_than_equal' },
      { loc: ['body', 'labels', 0], msg: 'String should have at least 1 character', type: 'string_too_short' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail }, 422)))
    const err = await failure(patchPhotoApi('h', { rating: 9 }))
    expect(err.message).toBe(
      'rating: Input should be less than or equal to 5; labels.0: String should have at least 1 character',
    )
    expect(err.status).toBe(422)
  })

  it('falls back to the status line when the body is not JSON', async () => {
    const page = new Response('<html>Bad gateway</html>', { status: 502, statusText: 'Bad Gateway' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(page))
    const err = await failure(getPhotoByHash('x'))
    expect(err.message).toBe('Loading the photo failed (502 Bad Gateway)')
  })

  it('reports an unreachable backend with a null status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await failure(getPhotoByHash('x'))
    expect(err.status).toBeNull()
    expect(err.message).toMatch(/Cannot reach the backend/)
  })

  it('errorMessage never returns an empty string', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom')
    expect(errorMessage(new Error(''))).toBe('Something went wrong')
    expect(errorMessage('a string')).toBe('Something went wrong')
  })
})

describe('API client requests', () => {
  it('sends a sync request with the folder and the options', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'j1' }, 202))
    vi.stubGlobal('fetch', fetchMock)
    await startSyncJobApi('D:/photos', { dry_run: true, cleanup_deleted: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/sync')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ folder_path: 'D:/photos', dry_run: true, cleanup_deleted: true })
  })
})
