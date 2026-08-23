"""Search photos use case and query/result DTOs."""

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Generic, Iterator, List, Optional, TypeVar

from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.domain.models import ImageMetadata

T = TypeVar("T")


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Great Circle distance between two points in kilometers using Haversine formula."""
    r = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


@dataclass
class SearchPhotosQuery:
    """DTO representing search filters, sorting options, and pagination parameters."""

    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    radius_km: Optional[float] = None
    tags: Optional[List[str]] = None
    sort_by: str = "captured_at"  # Choices: captured_at, size_bytes, camera_model, file_name
    sort_order: str = "asc"        # Choices: asc, desc
    page: int = 1
    page_size: int = 50


@dataclass
class PaginatedResult(Generic[T]):
    """Paginated result container implementing the Iterator protocol."""

    items: List[T]
    total_count: int
    page: int
    page_size: int
    total_pages: int

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class SearchPhotosUseCase:
    """Use case for filtering, sorting, and paginating photo metadata."""

    def __init__(self, repository: ImageMetadataRepository) -> None:
        self.repository = repository

    def execute(self, query: SearchPhotosQuery) -> PaginatedResult[ImageMetadata]:
        """Execute the search query against the metadata repository.

        Args:
            query: The SearchPhotosQuery filtering and pagination parameters.

        Returns:
            PaginatedResult containing matching ImageMetadata entities and pagination metadata.
        """
        all_records = self.repository.list_all()
        filtered = [record for record in all_records if self._matches_query(record, query)]

        # Sorting
        sorted_records = self._sort_records(filtered, query.sort_by, query.sort_order)

        # Pagination
        total_count = len(sorted_records)
        page_size = max(1, query.page_size)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        page = max(1, min(query.page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = sorted_records[start_idx:end_idx]

        return PaginatedResult(
            items=page_items,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def _matches_query(self, record: ImageMetadata, query: SearchPhotosQuery) -> bool:
        exif = record.exif
        info = record.file_info

        # Date range filtering
        if query.date_start or query.date_end:
            captured_at = exif.captured_at if exif else None
            if not captured_at:
                return False
            if query.date_start and captured_at < query.date_start:
                return False
            if query.date_end and captured_at > query.date_end:
                return False

        # Camera make and model filtering
        if query.camera_make and query.camera_model and query.camera_make == query.camera_model:
            cam_full = f"{exif.camera_make or ''} {exif.camera_model or ''}".lower() if exif else ""
            if query.camera_make.lower() not in cam_full:
                return False
        else:
            if query.camera_make:
                make = exif.camera_make if exif else None
                if not make or query.camera_make.lower() not in make.lower():
                    return False
            if query.camera_model:
                model = exif.camera_model if exif else None
                if not model or query.camera_model.lower() not in model.lower():
                    return False

        # Location radius filtering
        if (
            query.location_lat is not None
            and query.location_lon is not None
            and query.radius_km is not None
        ):
            gps = (exif.location or getattr(exif, "gps", None)) if exif else None
            if not gps or gps.latitude is None or gps.longitude is None:
                return False
            dist = haversine_distance_km(
                query.location_lat, query.location_lon, gps.latitude, gps.longitude
            )
            if dist > query.radius_km:
                return False

        # Tags filtering
        if query.tags:
            rec_tags = set(record.labels or [])
            if exif and getattr(exif, "tags", None):
                rec_tags.update(exif.tags)
            if exif and exif.raw_tags and isinstance(exif.raw_tags.get("tags"), list):
                rec_tags.update(exif.raw_tags["tags"])
            query_tags = set(query.tags)
            if not query_tags.issubset(rec_tags):
                return False

        return True

    def _sort_records(
        self, records: List[ImageMetadata], sort_by: str, sort_order: str
    ) -> List[ImageMetadata]:
        reverse = sort_order.lower() == "desc"

        def get_sort_key(record: ImageMetadata):
            if sort_by == "size_bytes":
                return record.file_info.size_bytes or 0
            elif sort_by == "camera_model":
                return (record.exif.camera_model if record.exif else "") or ""
            elif sort_by == "file_name":
                return record.file_info.name or ""
            else:  # captured_at
                dt = record.exif.captured_at if record.exif else None
                return dt if dt is not None else datetime.min

        return sorted(records, key=get_sort_key, reverse=reverse)
