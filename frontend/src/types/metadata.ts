/**
 * API types, generated from the backend's OpenAPI schema (PMO-30): edit `api/schemas.py`, then run
 * `python -m scripts.export_openapi` (repo root) and `npm run gen:api`. These are names for the
 * generated shapes, so a server change shows up here as a type error instead of silent drift.
 */
import type { components } from '../api/schema'

type Schemas = components['schemas']

export type GpsCoordinates = Schemas['GpsCoordinatesSchema']
export type FileInfo = Schemas['FileInfoSchema']
export type Dimensions = Schemas['DimensionsSchema']
export type ExifData = Schemas['ExifDataSchema']
export type PhotoMetadata = Schemas['PhotoMetadataResponse']
export type PaginatedPhotosResponse = Schemas['PaginatedPhotosResponse']

/** Tag filters are AND: a photo must carry every tag (ADR D2). */
export type SearchRequest = Schemas['SearchRequest']
export type SortField = NonNullable<SearchRequest['sort_by']>

/** One search match reduced to what a selection needs (`POST /api/search/ids`). */
export type PhotoId = Schemas['PhotoIdSchema']

export type FacetCount = Schemas['FacetCountSchema']
export type LibraryStats = Schemas['LibraryStatsSchema']
/** `GET /api/facets`: whole-library counts for filters and analytics. */
export type Facets = Schemas['FacetsResponse']

export type PatchPhotoRequest = Schemas['PatchPhotoRequest']
export type BatchPhotoRequest = Schemas['BatchPhotoRequest']
export type BatchPhotoResponse = Schemas['BatchPhotoResponse']
export type Collection = Schemas['CollectionResponse']

/** A background job (`POST /api/index` and `/api/sync` return one). */
export type Job = Schemas['JobResponse']
export type JobStatus = Job['status']
export type IndexFolderRequest = Schemas['IndexFolderRequest']
export type SyncFolderRequest = Schemas['SyncFolderRequest']
