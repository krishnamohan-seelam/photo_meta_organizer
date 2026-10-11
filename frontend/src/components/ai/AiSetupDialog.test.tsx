import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import type { AnalysisStatus } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { analysisStep, formatScore } from '../../utils/analysis'
import { AiSetupDialog } from './AiSetupDialog'

const initial = useUiStore.getState()

const base: AnalysisStatus = {
  runtime_installed: true,
  model_installed: false,
  model_id: 'clip-test',
  model_source: 'https://example.test/clip',
  model_licence: 'MIT',
  download_bytes: 305_000_000,
  total_photos: 10,
  analyzed_photos: 0,
  pending_photos: 10,
  active_job_id: null,
  active_job_kind: null,
}

function open(status: AnalysisStatus) {
  useUiStore.setState({ aiDialogOpen: true })
  const qc = testQueryClient()
  qc.setQueryData(['analysis', 'status'], status)
  renderWithQuery(<AiSetupDialog />, qc)
}

function fetchSpy() {
  const spy = vi.fn(async () => new Response(JSON.stringify({ id: 'j1', kind: 'model-download' }), { status: 202 }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => useUiStore.setState({ ...initial }))
afterEach(() => vi.unstubAllGlobals())

describe('analysisStep', () => {
  it('walks from nothing installed to ready', () => {
    expect(analysisStep(undefined).kind).toBe('loading')
    expect(analysisStep({ ...base, runtime_installed: false }).kind).toBe('no-runtime')
    expect(analysisStep(base).kind).toBe('needs-model')
    expect(analysisStep({ ...base, model_installed: true }).kind).toBe('needs-analysis')
    expect(analysisStep({ ...base, model_installed: true, analyzed_photos: 10, pending_photos: 0 }).kind).toBe('ready')
  })

  it('reports a running job before anything else', () => {
    const busy = analysisStep({ ...base, active_job_id: 'j', active_job_kind: 'model-download' })
    expect(busy).toEqual({ kind: 'busy', what: 'model-download' })
    expect(analysisStep({ ...base, model_installed: true, active_job_id: 'j', active_job_kind: 'analyze' })).toEqual({ kind: 'busy', what: 'analyze' })
  })
})

describe('formatScore', () => {
  it('is a clamped percentage', () => {
    expect(formatScore(0.2843)).toBe('28%')
    expect(formatScore(-0.1)).toBe('0%')
    expect(formatScore(1.2)).toBe('100%')
  })
})

describe('AiSetupDialog', () => {
  it('renders nothing while closed', () => {
    renderWithQuery(<AiSetupDialog />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('states size, source and licence before anything is downloaded, and downloads nothing until asked', () => {
    open(base)
    const spy = fetchSpy()
    expect(screen.getByText('https://example.test/clip')).toBeTruthy()
    expect(screen.getByText('MIT')).toBeTruthy()
    expect(screen.getByText(/never uploaded/)).toBeTruthy()
    expect(spy).not.toHaveBeenCalled()
  })

  it('sends the consent only when Download is pressed, then closes', async () => {
    open(base)
    const spy = fetchSpy()
    fireEvent.click(screen.getByRole('button', { name: /Download model/ }))
    await vi.waitFor(() => expect(spy).toHaveBeenCalled())
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/analysis/model/download')
    expect(JSON.parse(init.body as string)).toEqual({ accept: true })
    expect(useUiStore.getState().aiDialogOpen).toBe(false)
  })

  it('offers to analyze once the model is installed', async () => {
    open({ ...base, model_installed: true })
    const spy = fetchSpy()
    fireEvent.click(screen.getByRole('button', { name: /Analyze 10 photos/ }))
    await vi.waitFor(() => expect(spy).toHaveBeenCalled())
    expect((spy.mock.calls[0] as unknown as [string])[0]).toBe('/api/analysis/run')
  })

  it('explains a missing runtime instead of offering a download', () => {
    open({ ...base, runtime_installed: false })
    expect(screen.getByRole('alert').textContent).toMatch(/--extra ai/)
    expect(screen.queryByRole('button', { name: /Download model/ })).toBeNull()
  })

  it('closes on Escape', () => {
    open(base)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(useUiStore.getState().aiDialogOpen).toBe(false)
  })
})
