import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { KeepAnalysed } from '../../types/metadata'
import { analysisKey } from '../../hooks/useAnalysis'
import { renderWithQuery, testQueryClient } from '../../test/render'
import { KeepAnalysedToggle, keepAnalysedNote } from './KeepAnalysedToggle'

const keep = (over: Partial<KeepAnalysed> = {}): KeepAnalysed => ({
  enabled: false,
  threshold: 2000,
  pending: 5,
  state: 'off',
  ...over,
})

function show(status: KeepAnalysed) {
  const qc = testQueryClient()
  qc.setQueryData([...analysisKey, 'keep'], status)
  renderWithQuery(<KeepAnalysedToggle />, qc)
  return qc
}

afterEach(() => vi.unstubAllGlobals())

describe('KeepAnalysedToggle', () => {
  it('is an unchecked box until the user chooses it', () => {
    show(keep())
    const box = screen.getByRole('checkbox', { name: /Keep the library analysed automatically/ })
    expect(box).toHaveProperty('checked', false)
    expect(screen.getByText(/never without the model you already downloaded/)).toBeTruthy()
  })

  it('turning it on saves the setting and shows what it is doing', async () => {
    const qc = show(keep())
    const spy = vi.fn(async () => new Response(JSON.stringify(keep({ enabled: true, state: 'waiting_for_idle' })), { status: 200 }))
    vi.stubGlobal('fetch', spy)
    fireEvent.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/analysis/keep')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({ enabled: true })
    await waitFor(() => expect(screen.getByText(/starts once you have been still/)).toBeTruthy())
    expect(qc.getQueryData([...analysisKey, 'keep'])).toMatchObject({ enabled: true })
  })

  it('says why nothing happens: no model, too many photos, battery, paused', () => {
    expect(keepAnalysedNote(keep({ state: 'waiting_for_model' }))).toMatch(/download it above first/)
    expect(keepAnalysedNote(keep({ state: 'needs_approval', pending: 2500 }))).toMatch(/2,500 photos are waiting, more than the 2,000/)
    expect(keepAnalysedNote(keep({ state: 'on_battery' }))).toMatch(/plugged in/)
    expect(keepAnalysedNote(keep({ state: 'paused' }))).toMatch(/Resume or dismiss/)
    expect(keepAnalysedNote(keep({ state: 'off' }))).toBeNull()
  })
})
