import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import type { Facets, GeoClustersResponse } from '../../types/metadata'
import { useUiStore } from '../../stores/useUiStore'
import { renderWithQuery } from '../../test/render'
import { MapExplorerView } from './MapExplorerView'
import type { LeafletMap } from './LeafletMap'

// Leaflet needs real layout; the component under test is everything around it.
let mapProps: Parameters<typeof LeafletMap>[0]
vi.mock('./LeafletMap', () => ({
  LeafletMap: (props: Parameters<typeof LeafletMap>[0]) => {
    mapProps = props
    return <div data-testid="map">{props.clusters.length} clusters</div>
  },
}))

const api = vi.hoisted(() => ({
  fetchGeoClustersApi: vi.fn(),
  fetchConfigApi: vi.fn(),
  fetchFacetsApi: vi.fn(),
}))
vi.mock('../../api/client', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))

const FACETS: Facets = {
  cameras: [],
  tags: [],
  years: [],
  isos: [],
  gps_bounds: { min_lat: 35, max_lat: 36, min_lon: 135, max_lon: 140 },
  stats: { total_count: 10, flagged_count: 0, geotagged_count: 3, undated_count: 0, total_bytes: 0, avg_megapixels: 0 },
}

const CLUSTERS: GeoClustersResponse = {
  clusters: [
    { latitude: 35.68, longitude: 139.65, count: 2, representative_hash: 'h1', label: 'Tokyo, Japan' },
    { latitude: 35.01, longitude: 135.76, count: 1, representative_hash: 'h2', label: 'Kyoto, Japan' },
  ],
  total_count: 3,
}

const VIEW = { bbox: { south: 30, west: 130, north: 40, east: 145 }, zoom: 5 }
const initial = useUiStore.getState()

beforeEach(() => {
  api.fetchFacetsApi.mockResolvedValue(FACETS)
  api.fetchConfigApi.mockResolvedValue({ map_tiles_url: null, map_tiles_attribution: null })
  api.fetchGeoClustersApi.mockResolvedValue(CLUSTERS)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  useUiStore.setState(initial, true)
})

async function showMap() {
  renderWithQuery(<MapExplorerView />)
  await waitFor(() => expect(mapProps.fitTo).not.toBeNull())
  act(() => mapProps.onViewChange(VIEW))
  await screen.findByText('3 photos in view')
}

describe('MapExplorerView', () => {
  it('first looks at the extent of the geotagged photos', async () => {
    renderWithQuery(<MapExplorerView />)
    await waitFor(() => expect(mapProps.fitTo?.bounds).toEqual({ south: 35, west: 135, north: 36, east: 140 }))
  })

  it('asks the server for clusters of the visible area, a little padded, at its zoom', async () => {
    await showMap()
    const request = api.fetchGeoClustersApi.mock.calls.at(-1)![0]
    expect(request.zoom).toBe(5)
    expect(request.bbox.south).toBeLessThan(30)
    expect(request.bbox.north).toBeGreaterThan(40)
    expect(screen.getByTestId('map').textContent).toBe('2 clusters')
    expect(screen.getByText('3 geotagged in the library')).toBeTruthy()
  })

  it('applies the library filters but not the library map area', async () => {
    useUiStore.setState({ filterCameras: ['Sony'], filterArea: { south: 0, west: 0, north: 1, east: 1 } })
    await showMap()
    const request = api.fetchGeoClustersApi.mock.calls.at(-1)![0]
    expect(request.camera_makes).toEqual(['Sony'])
    expect(request.within).toBeUndefined()
  })

  it('"Show these in Library" narrows the Library to the visible area and opens it', async () => {
    useUiStore.setState({ activeView: 'map' })
    await showMap()
    fireEvent.click(screen.getByRole('button', { name: /show these in library/i }))
    const state = useUiStore.getState()
    expect(state.filterArea).toEqual(VIEW.bbox)
    expect(state.activeView).toBe('studio')
  })

  it('cannot show an empty area in the Library', async () => {
    api.fetchGeoClustersApi.mockResolvedValue({ clusters: [], total_count: 0 })
    renderWithQuery(<MapExplorerView />)
    await waitFor(() => expect(mapProps.fitTo).not.toBeNull())
    act(() => mapProps.onViewChange(VIEW))
    await screen.findByText('No geotagged photos match the filters in this area.')
    expect((screen.getByRole('button', { name: /show these in library/i }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('"Fit to photos" asks the map to re-fit even to the same bounds', async () => {
    await showMap()
    const before = mapProps.fitTo!.key
    fireEvent.click(screen.getByRole('button', { name: /fit to photos/i }))
    expect(mapProps.fitTo!.key).toBeGreaterThan(before)
  })

  it('inspects a single photo that is clicked and opens the details panel', async () => {
    useUiStore.setState({ inspectorOpen: false })
    await showMap()
    act(() => mapProps.onOpenPhoto('h2'))
    expect(useUiStore.getState().inspectedHash).toBe('h2')
    expect(useUiStore.getState().inspectorOpen).toBe(true)
  })

  it('passes the opted-in tile server to the map', async () => {
    api.fetchConfigApi.mockResolvedValue({ map_tiles_url: 'https://t.example/{z}/{x}/{y}.png', map_tiles_attribution: '© T' })
    renderWithQuery(<MapExplorerView />)
    await waitFor(() => expect(mapProps.tilesUrl).toBe('https://t.example/{z}/{x}/{y}.png'))
    expect(mapProps.tilesAttribution).toBe('© T')
  })

  it('says so when no photo has GPS', async () => {
    api.fetchFacetsApi.mockResolvedValue({ ...FACETS, gps_bounds: null, stats: { ...FACETS.stats, geotagged_count: 0 } })
    api.fetchGeoClustersApi.mockResolvedValue({ clusters: [], total_count: 0 })
    renderWithQuery(<MapExplorerView />)
    await waitFor(() => expect(mapProps).toBeDefined())
    act(() => mapProps.onViewChange(VIEW))
    await screen.findByText(/none of your photos have gps/i)
    expect((screen.getByRole('button', { name: /fit to photos/i }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a failed load', async () => {
    api.fetchGeoClustersApi.mockRejectedValue(new Error('Cannot reach the backend. Is it running?'))
    renderWithQuery(<MapExplorerView />)
    await waitFor(() => expect(mapProps).toBeDefined())
    act(() => mapProps.onViewChange(VIEW))
    expect((await screen.findByRole('alert')).textContent).toContain('Cannot reach the backend')
  })
})
