"""Map zoom to grid cell size (Part A of the Phase 5 plan)."""

import pytest

from photo_meta_organizer.application.geo import cell_degrees_for_zoom


def test_cells_halve_with_each_zoom_level():
    assert cell_degrees_for_zoom(4) == pytest.approx(cell_degrees_for_zoom(3) / 2)


def test_world_view_cells_are_coarse_and_street_view_cells_fine():
    assert cell_degrees_for_zoom(1) > 10
    assert cell_degrees_for_zoom(18) < 0.001


@pytest.mark.parametrize("zoom", [-3, 0, 25, 99])
def test_zoom_is_clamped(zoom):
    assert cell_degrees_for_zoom(zoom) > 0
