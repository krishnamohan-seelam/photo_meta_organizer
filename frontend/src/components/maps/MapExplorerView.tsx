import React, { useCallback, useMemo, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Crosshair, Images, MapPin } from 'lucide-react'
import { useFacets } from '../../hooks/useFacets'
import { useAppConfig, useGeoClusters, useMapFilterRequest } from '../../hooks/useGeoClusters'
import { useUiStore } from '../../stores/useUiStore'
import type { GeoCluster } from '../../types/metadata'
import { normalizeBounds, padBounds } from '../../utils/geo'
import { LeafletMap, type FitRequest, type MapView } from './LeafletMap'

/** The request covers this much more than the screen on each side, so a small pan needs no reload. */
const VIEWPORT_PADDING = 0.25
const NO_CLUSTERS: GeoCluster[] = []

/**
 * Map Explorer: your geotagged photos, clustered by the server for the area and zoom on screen
 * and filtered like the Library. The Library's own filters apply; the map has its own area.
 */
export const MapExplorerView: React.FC = () => {
  const { theme, inspectorOpen, toggleInspector, setInspectedHash, setActiveView, setFilterArea, showToast } =
    useUiStore(
      useShallow((s) => ({
        theme: s.theme,
        inspectorOpen: s.inspectorOpen,
        toggleInspector: s.toggleInspector,
        setInspectedHash: s.setInspectedHash,
        setActiveView: s.setActiveView,
        setFilterArea: s.setFilterArea,
        showToast: s.showToast,
      }))
    )
  const facets = useFacets()
  const config = useAppConfig()
  const filters = useMapFilterRequest()

  const [view, setView] = useState<MapView | null>(null)
  const [fitTo, setFitTo] = useState<FitRequest | null>(null)
  // The library's extent, once known, is where the map first looks (one automatic fit).
  const [autoFitted, setAutoFitted] = useState(false)
  if (!autoFitted && facets.gps_bounds) {
    setAutoFitted(true)
    const b = facets.gps_bounds
    setFitTo({ bounds: { south: b.min_lat, west: b.min_lon, north: b.max_lat, east: b.max_lon }, key: 1 })
  }

  const request = useMemo(
    () => (view ? { ...filters, bbox: padBounds(view.bbox, VIEWPORT_PADDING), zoom: view.zoom } : null),
    [filters, view]
  )
  const { data, isError, error } = useGeoClusters(request)
  const clusters = data?.clusters ?? NO_CLUSTERS
  const inView = data?.total_count ?? 0
  const geotagged = facets.stats.geotagged_count

  const fitToPhotos = () => {
    const b = facets.gps_bounds
    if (!b) return
    setFitTo({
      bounds: { south: b.min_lat, west: b.min_lon, north: b.max_lat, east: b.max_lon },
      key: (fitTo?.key ?? 0) + 1,
    })
  }

  const showInLibrary = () => {
    if (!view) return
    setFilterArea(normalizeBounds(view.bbox))
    setActiveView('studio')
    showToast('Library narrowed to the map area. Remove the “Map area” chip to see everything.')
  }

  const openPhoto = useCallback(
    (fileHash: string) => {
      setInspectedHash(fileHash)
      if (!inspectorOpen) toggleInspector()
    },
    [setInspectedHash, inspectorOpen, toggleInspector]
  )

  return (
    <div className="map-view">
      <div className="map-toolbar">
        <div className="map-toolbar-title">
          <MapPin size={16} />
          <span>Map</span>
        </div>
        <div className="badge badge-camera" aria-live="polite">
          {inView} {inView === 1 ? 'photo' : 'photos'} in view
        </div>
        <span className="map-toolbar-muted">{geotagged} geotagged in the library</span>
        <div className="map-toolbar-actions">
          <button type="button" className="btn-secondary" onClick={fitToPhotos} disabled={!facets.gps_bounds}>
            <Crosshair size={14} /> Fit to photos
          </button>
          <button type="button" className="btn-primary" onClick={showInLibrary} disabled={!view || inView === 0}>
            <Images size={14} /> Show these in Library
          </button>
        </div>
      </div>

      <div className="map-stage">
        <LeafletMap
          clusters={clusters}
          tilesUrl={config.map_tiles_url}
          tilesAttribution={config.map_tiles_attribution}
          theme={theme}
          fitTo={fitTo}
          onViewChange={setView}
          onOpenPhoto={openPhoto}
        />
        {isError && (
          <div className="map-notice map-notice-error" role="alert">
            {error instanceof Error ? error.message : 'Could not load the map.'}
          </div>
        )}
        {!isError && data && geotagged === 0 && (
          <div className="map-notice">None of your photos have GPS coordinates, so there is nothing to place on the map.</div>
        )}
        {!isError && data && geotagged > 0 && inView === 0 && (
          <div className="map-notice">No geotagged photos match the filters in this area.</div>
        )}
      </div>
    </div>
  )
}
