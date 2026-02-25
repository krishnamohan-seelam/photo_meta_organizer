"""Unit tests for domain.services.py.

Tests for the CameraClassifier domain service which infers
camera profiles from make, model, and available field metadata.
"""

import pytest

from photo_meta_organizer.domain.models import CameraProfile
from photo_meta_organizer.domain.services import CameraClassifier


@pytest.mark.unit
class TestCameraClassifier:
    """Tests for CameraClassifier domain service."""

    # --- DSLR Detection ---

    def test_dslr_sony_with_lens(self) -> None:
        """Sony with LensModel → DSLR."""
        profile = CameraClassifier.classify(
            camera_make="Sony",
            camera_model="SLT-A37",
            has_lens_model=True,
        )
        assert profile == CameraProfile.DSLR

    def test_dslr_canon_with_lens(self) -> None:
        """Canon with LensModel → DSLR."""
        profile = CameraClassifier.classify(
            camera_make="Canon",
            camera_model="EOS 5D Mark IV",
            has_lens_model=True,
        )
        assert profile == CameraProfile.DSLR

    def test_dslr_nikon_with_lens(self) -> None:
        """Nikon with LensModel → DSLR."""
        profile = CameraClassifier.classify(
            camera_make="NIKON",
            camera_model="D850",
            has_lens_model=True,
        )
        assert profile == CameraProfile.DSLR

    # --- Mobile Detection ---

    def test_mobile_apple(self) -> None:
        """Apple → MOBILE."""
        profile = CameraClassifier.classify(
            camera_make="Apple",
            camera_model="iPhone 14 Pro",
            has_lens_model=False,
        )
        assert profile == CameraProfile.MOBILE

    def test_mobile_xiaomi(self) -> None:
        """Xiaomi → MOBILE (case insensitive)."""
        profile = CameraClassifier.classify(
            camera_make="XIAOMI",
            camera_model="MI4",
            has_lens_model=False,
        )
        assert profile == CameraProfile.MOBILE

    def test_mobile_samsung(self) -> None:
        """Samsung → MOBILE."""
        profile = CameraClassifier.classify(
            camera_make="samsung",
            camera_model="Galaxy S23",
            has_lens_model=False,
        )
        assert profile == CameraProfile.MOBILE

    def test_mobile_google(self) -> None:
        """Google → MOBILE."""
        profile = CameraClassifier.classify(
            camera_make="Google",
            camera_model="Pixel 8",
        )
        assert profile == CameraProfile.MOBILE

    # --- Mirrorless Detection ---

    def test_mirrorless_canon_eos_r(self) -> None:
        """Canon EOS R pattern → MIRRORLESS."""
        profile = CameraClassifier.classify(
            camera_make="Canon",
            camera_model="Canon EOS R5",
            has_lens_model=True,
        )
        assert profile == CameraProfile.MIRRORLESS

    def test_mirrorless_sony_a7(self) -> None:
        """Sony A7 pattern → MIRRORLESS."""
        profile = CameraClassifier.classify(
            camera_make="Sony",
            camera_model="ILCE-A7M4",
            has_lens_model=True,
        )
        assert profile == CameraProfile.MIRRORLESS

    def test_mirrorless_nikon_z(self) -> None:
        """Nikon Z8 pattern → MIRRORLESS."""
        profile = CameraClassifier.classify(
            camera_make="Nikon",
            camera_model="Z8",
            has_lens_model=True,
        )
        assert profile == CameraProfile.MIRRORLESS

    def test_mirrorless_sony_without_lens(self) -> None:
        """Sony without LensModel and no mirrorless pattern → MIRRORLESS fallback."""
        profile = CameraClassifier.classify(
            camera_make="Sony",
            camera_model="DSC-RX100",
            has_lens_model=False,
        )
        assert profile == CameraProfile.MIRRORLESS

    # --- Action Camera Detection ---

    def test_action_cam_gopro(self) -> None:
        """GoPro → ACTION_CAM."""
        profile = CameraClassifier.classify(
            camera_make="GoPro",
            camera_model="HERO11 Black",
            has_lens_model=False,
        )
        assert profile == CameraProfile.ACTION_CAM

    def test_action_cam_dji(self) -> None:
        """DJI → ACTION_CAM."""
        profile = CameraClassifier.classify(
            camera_make="DJI",
            camera_model="Osmo Action 4",
            has_lens_model=False,
        )
        assert profile == CameraProfile.ACTION_CAM

    # --- Film Scanner Detection ---

    def test_film_scanner(self) -> None:
        """Model containing 'Scanner' → FILM_SCANNER."""
        profile = CameraClassifier.classify(
            camera_make="Epson",
            camera_model="Perfection V600 Film Scanner",
            has_lens_model=False,
        )
        assert profile == CameraProfile.FILM_SCANNER

    # --- Unknown / Edge Cases ---

    def test_unknown_no_make(self) -> None:
        """No camera make → UNKNOWN."""
        profile = CameraClassifier.classify(
            camera_make=None,
            camera_model=None,
            has_lens_model=False,
        )
        assert profile == CameraProfile.UNKNOWN

    def test_unknown_empty_make(self) -> None:
        """Empty camera make → UNKNOWN."""
        profile = CameraClassifier.classify(
            camera_make="",
            camera_model="Unknown Model",
        )
        assert profile == CameraProfile.UNKNOWN

    def test_unknown_unrecognized_make(self) -> None:
        """Unrecognized make → UNKNOWN."""
        profile = CameraClassifier.classify(
            camera_make="Leica",
            camera_model="M11",
            has_lens_model=True,
        )
        assert profile == CameraProfile.UNKNOWN

    def test_case_insensitive_matching(self) -> None:
        """Make matching is case-insensitive."""
        profile1 = CameraClassifier.classify("apple", "iPhone", False)
        profile2 = CameraClassifier.classify("APPLE", "iPhone", False)
        profile3 = CameraClassifier.classify("Apple", "iPhone", False)
        assert profile1 == profile2 == profile3 == CameraProfile.MOBILE

    def test_whitespace_handling(self) -> None:
        """Leading/trailing whitespace is trimmed."""
        profile = CameraClassifier.classify(
            camera_make="  Apple  ",
            camera_model=" iPhone 14 ",
        )
        assert profile == CameraProfile.MOBILE
