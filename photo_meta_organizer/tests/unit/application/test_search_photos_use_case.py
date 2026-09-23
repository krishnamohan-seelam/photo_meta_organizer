"""Unit tests for SearchPhotosUseCase (PMO-09: a thin pass-through to
``repository.query()``; filtering/sorting/paging behavior itself is covered by
the repository contract tests, since it now lives in each implementation).
"""

from unittest.mock import MagicMock

from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    PaginatedResult,
    SearchPhotosQuery,
    SearchPhotosUseCase,
    haversine_distance_km,
)


def test_haversine_distance():
    # SF to Oakland is ~13 km
    dist = haversine_distance_km(37.7749, -122.4194, 37.8044, -122.2712)
    assert 10.0 <= dist <= 15.0

    # Same location -> 0 km
    assert haversine_distance_km(37.7749, -122.4194, 37.7749, -122.4194) == 0.0


def test_paginated_result_iterator():
    items = ["a", "b", "c"]
    res = PaginatedResult(items=items, total_count=3, page=1, page_size=10, total_pages=1)

    collected = list(res)
    assert collected == ["a", "b", "c"]
    assert len(res) == 3


def test_execute_delegates_to_repository_query():
    repo = MagicMock()
    expected = PaginatedResult(items=[], total_count=0, page=1, page_size=50, total_pages=1)
    repo.query.return_value = expected

    use_case = SearchPhotosUseCase(repository=repo)
    query = SearchPhotosQuery(camera_make="Sony")
    result = use_case.execute(query)

    repo.query.assert_called_once_with(query)
    assert result is expected
