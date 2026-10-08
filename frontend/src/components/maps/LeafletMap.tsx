import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Topology } from 'topojson-specification'
import type { BoundingBox, GeoCluster } from '../../types/metadata'
import type { Theme } from '../../utils/theme'
import { MAX_ZOOM, clusterTitle, normalizeBounds, zoomIntoCluster } from '../../utils/geo'
import { swapToPlaceholder } from '../../utils/placeholder'
import { MARKER_SIZE, markerHtml } from './markers'

export interface MapView {
  /** The visible area, longitudes wrapped (see `normalizeBounds`). */
  bbox: BoundingBox
  zoom: number
}

export interface FitRequest {
  bounds: BoundingBox
  /** Changes for every request, so asking for the same bounds twice still re-fits. */
  key: number
}

interface Props {
  clusters: GeoCluster[]
  /** Online tile template the user opted into; without it the bundled world outline is drawn. */
  tilesUrl: string | null
  tilesAttribution: string | null
  theme: Theme
  fitTo: FitRequest | null
  onViewChange: (view: MapView) => void
  onOpenPhoto: (fileHash: string) => void
}

const OUTLINE_CREDIT = 'Country outlines: Natural Earth (public domain)'

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** The bundled country outlines as a Leaflet layer (a lazy chunk: ~750 KB, only on the Map view). */
async function loadOutline(): Promise<L.GeoJSON> {
  const [{ feature }, world] = await Promise.all([import('topojson-client'), import('world-atlas/countries-50m.json')])
  const topology = world.default as unknown as Topology
  const countries = feature(topology, topology.objects.countries as never)
  return L.geoJSON(countries as never, {
    interactive: false,
    style: () => ({
      fill: true,
      fillColor: cssVar('--bg-surface', '#1c1c1c'),
      fillOpacity: 1,
      color: cssVar('--border-color', '#444'),
      weight: 0.8,
    }),
  })
}

/**
 * The Leaflet map: imperative by nature, so everything React-specific stays in this one file.
 * It reports the visible area on every pan or zoom, draws the clusters it is given, and zooms
 * into a group when it is clicked.
 */
export function LeafletMap({ clusters, tilesUrl, tilesAttribution, theme, fitTo, onViewChange, onOpenPhoto }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.LayerGroup | null>(null)
  const baseRef = useRef<L.Layer | null>(null)
  // Handlers read through a ref, so the map is built once and never rebinds its events.
  const callbacks = useRef({ onViewChange, onOpenPhoto })
  useEffect(() => {
    callbacks.current = { onViewChange, onOpenPhoto }
  })

  useEffect(() => {
    const el = container.current
    if (!el) return
    const map = L.map(el, { minZoom: 2, maxZoom: MAX_ZOOM, worldCopyJump: true, zoomSnap: 1 }).setView([25, 10], 2)
    mapRef.current = map
    markersRef.current = L.layerGroup().addTo(map)

    const report = () => {
      const b = map.getBounds()
      callbacks.current.onViewChange({
        bbox: normalizeBounds({ south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() }),
        zoom: Math.round(map.getZoom()),
      })
    }
    map.on('moveend', report)
    report()

    // The panels beside the map open and close, which changes its width.
    const resize = new ResizeObserver(() => map.invalidateSize())
    resize.observe(el)
    return () => {
      resize.disconnect()
      map.remove()
      mapRef.current = null
      markersRef.current = null
      baseRef.current = null
    }
  }, [])

  // Basemap: opted-in tiles, otherwise the offline outline (restyled when the theme changes).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    let cancelled = false
    const install = (layer: L.Layer) => {
      if (cancelled) return
      baseRef.current?.remove()
      layer.addTo(map)
      baseRef.current = layer
      if ('bringToBack' in layer) (layer as L.TileLayer).bringToBack()
    }
    if (tilesUrl) {
      map.attributionControl.setPrefix(false)
      install(L.tileLayer(tilesUrl, { attribution: tilesAttribution ?? '', maxZoom: MAX_ZOOM }))
    } else {
      map.attributionControl.setPrefix(false)
      loadOutline().then(
        (layer) => {
          install(layer)
          map.attributionControl.addAttribution(OUTLINE_CREDIT)
        },
        () => undefined // no outline: the markers still work on the plain background
      )
    }
    return () => {
      cancelled = true
      map.attributionControl.removeAttribution(OUTLINE_CREDIT)
    }
    // `theme` is a dependency on purpose: the outline reads the theme's CSS variables.
  }, [tilesUrl, tilesAttribution, theme])

  useEffect(() => {
    const map = mapRef.current
    const layer = markersRef.current
    if (!map || !layer) return
    layer.clearLayers()
    for (const cluster of clusters) {
      const marker = L.marker([cluster.latitude, cluster.longitude], {
        icon: L.divIcon({
          className: 'pmo-marker',
          html: markerHtml(cluster),
          iconSize: [MARKER_SIZE.width, MARKER_SIZE.height],
          iconAnchor: [MARKER_SIZE.width / 2, 24],
        }),
        title: clusterTitle(cluster),
        alt: clusterTitle(cluster),
        keyboard: true,
      })
      marker.on('click', () => {
        if (cluster.count === 1) callbacks.current.onOpenPhoto(cluster.representative_hash)
        else map.setView([cluster.latitude, cluster.longitude], zoomIntoCluster(map.getZoom()))
      })
      marker.addTo(layer)
      // A thumbnail the backend cannot render gets the same placeholder as in the grid.
      marker.getElement()?.querySelector('img')?.addEventListener('error', (e) => swapToPlaceholder(e as never), { once: true })
    }
  }, [clusters])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !fitTo) return
    const { south, west, north, east } = fitTo.bounds
    // A box across the date line has west > east: extend east by a full turn for Leaflet.
    map.fitBounds(
      [
        [south, west],
        [north, west <= east ? east : east + 360],
      ],
      { maxZoom: 12, padding: [48, 48] }
    )
  }, [fitTo])

  return <div ref={container} className="pmo-map" role="application" aria-label="Photo map" />
}
