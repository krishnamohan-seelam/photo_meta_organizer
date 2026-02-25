"""Domain services for image metadata processing.

This module contains domain services that encapsulate business logic
which doesn't naturally belong to a single entity or value object.

Domain services are:
- Stateless (no internal state between calls)
- Depend only on domain models (no infrastructure dependencies)
- Contain business rules expressed in domain language
"""

from typing import Optional

from photo_meta_organizer.domain.models import CameraProfile


class CameraClassifier:
    """Domain service for classifying camera types from extracted metadata.

    Camera profile classification is domain knowledge that determines
    recovery strategies and downstream behavior (e.g., which fields to
    expect as populated vs. gracefully missing).

    The classification uses make, model, and available field metadata
    to infer the camera profile. This is a pure domain decision — no
    infrastructure dependencies.
    """

    # Camera make patterns (all uppercase for case-insensitive matching)
    MOBILE_MAKES = {
        "APPLE", "SAMSUNG", "XIAOMI", "HUAWEI",
        "GOOGLE", "ONEPLUS", "OPPO", "VIVO",
    }
    DSLR_MAKES = {"SONY", "CANON", "NIKON", "PENTAX", "FUJIFILM"}
    ACTION_CAM_MAKES = {"GOPRO", "DJI", "INSTA360"}
    MIRRORLESS_PATTERNS = {
        "EOS R", "Z5", "Z6", "Z7", "Z8", "Z9",
        "A7", "A6", "S5", "S1", "X-T", "X-H",
    }

    @staticmethod
    def classify(
        camera_make: Optional[str],
        camera_model: Optional[str],
        has_lens_model: bool = False,
    ) -> CameraProfile:
        """Infer camera profile from make, model, and available field data.

        Args:
            camera_make: Camera manufacturer string (case-insensitive).
            camera_model: Camera model string (case-insensitive).
            has_lens_model: Whether EXIF LensModel tag was present.

        Returns:
            Best-guess CameraProfile enum value. Returns UNKNOWN
            when insufficient data is available.
        """
        if not camera_make:
            return CameraProfile.UNKNOWN

        make_upper = camera_make.strip().upper()
        model_upper = (camera_model or "").strip().upper()

        if make_upper in CameraClassifier.MOBILE_MAKES:
            return CameraProfile.MOBILE

        if make_upper in CameraClassifier.ACTION_CAM_MAKES:
            return CameraProfile.ACTION_CAM

        if "SCANNER" in model_upper or "FILM" in model_upper:
            return CameraProfile.FILM_SCANNER

        if any(
            pattern in model_upper
            for pattern in CameraClassifier.MIRRORLESS_PATTERNS
        ):
            return CameraProfile.MIRRORLESS

        if make_upper in CameraClassifier.DSLR_MAKES and has_lens_model:
            return CameraProfile.DSLR

        if make_upper in CameraClassifier.DSLR_MAKES:
            # Modern cameras from these brands without explicit detection
            return CameraProfile.MIRRORLESS

        return CameraProfile.UNKNOWN
