"""Unit tests for domain.models.py.

These tests verify that domain entities are properly immutable, serializable,
and conform to the PRD specification for image metadata management.

Tests cover:
- All value objects (ImageFileInfo, ImageDimensions, GpsCoordinates, ImageExifData)
- CameraProfile enum
- Three-tier EXIF architecture (Tier 1 universal, Tier 2 common, Tier 3 raw_tags)
- ImageMetadata domain entity
"""

import pytest
from datetime import datetime

from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageLocation,
    ImageMetadata,
)


@pytest.mark.unit
class TestImageFileInfo:
    """Test ImageFileInfo value object."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating ImageFileInfo with all required fields."""
        info = ImageFileInfo(
            name="test.jpg",
            path="/photos/test.jpg",
            size_bytes=1024,
            mime_type="image/jpeg",
        )
        assert info.name == "test.jpg"
        assert info.path == "/photos/test.jpg"
        assert info.size_bytes == 1024
        assert info.mime_type == "image/jpeg"

    def test_immutability(self) -> None:
        """Test that ImageFileInfo is immutable (frozen dataclass)."""
        info = ImageFileInfo(
            name="test.jpg",
            path="/photos/test.jpg",
            size_bytes=1024,
            mime_type="image/jpeg",
        )
        with pytest.raises(AttributeError):
            info.name = "other.jpg"  # type: ignore

    def test_equality(self) -> None:
        """Test that two ImageFileInfo instances with same values are equal."""
        info1 = ImageFileInfo("test.jpg", "/photos/test.jpg", 1024, "image/jpeg")
        info2 = ImageFileInfo("test.jpg", "/photos/test.jpg", 1024, "image/jpeg")
        assert info1 == info2

    def test_hash_equality(self) -> None:
        """Test that equal ImageFileInfo instances have same hash."""
        info1 = ImageFileInfo("test.jpg", "/photos/test.jpg", 1024, "image/jpeg")
        info2 = ImageFileInfo("test.jpg", "/photos/test.jpg", 1024, "image/jpeg")
        assert hash(info1) == hash(info2)


@pytest.mark.unit
class TestImageDimensions:
    """Test ImageDimensions value object."""

    def test_creation_and_fields(self) -> None:
        """Test creating ImageDimensions with width and height."""
        dims = ImageDimensions(width=1920, height=1080)
        assert dims.width == 1920
        assert dims.height == 1080

    def test_aspect_ratio_calculation(self) -> None:
        """Test aspect ratio calculation."""
        dims = ImageDimensions(width=1920, height=1080)
        assert abs(dims.aspect_ratio - (1920 / 1080)) < 0.001

    def test_aspect_ratio_zero_height(self) -> None:
        """Test aspect ratio returns 0 when height is zero."""
        dims = ImageDimensions(width=1920, height=0)
        assert dims.aspect_ratio == 0.0

    def test_immutability(self) -> None:
        """Test that ImageDimensions is immutable."""
        dims = ImageDimensions(width=1920, height=1080)
        with pytest.raises(AttributeError):
            dims.width = 4000  # type: ignore


@pytest.mark.unit
class TestCameraProfile:
    """Test CameraProfile enum."""

    def test_all_profiles_defined(self) -> None:
        """All 6 camera profiles are accessible."""
        profiles = [
            CameraProfile.UNKNOWN,
            CameraProfile.DSLR,
            CameraProfile.MIRRORLESS,
            CameraProfile.MOBILE,
            CameraProfile.ACTION_CAM,
            CameraProfile.FILM_SCANNER,
        ]
        assert len(profiles) == 6

    def test_profile_values(self) -> None:
        """Profile enum values are lowercase strings."""
        assert CameraProfile.DSLR.value == "dslr"
        assert CameraProfile.MOBILE.value == "mobile"
        assert CameraProfile.UNKNOWN.value == "unknown"


@pytest.mark.unit
class TestGpsCoordinates:
    """Test GpsCoordinates value object."""

    def test_creation_valid(self) -> None:
        """Valid GPS coordinates creation."""
        gps = GpsCoordinates(
            latitude=37.7749,
            longitude=-122.4194,
            altitude=10.0,
        )
        assert gps.latitude == 37.7749
        assert gps.longitude == -122.4194
        assert gps.altitude == 10.0
        assert gps.datum == "WGS84"

    def test_creation_minimal(self) -> None:
        """GPS with only lat/lon, defaults for altitude and datum."""
        gps = GpsCoordinates(latitude=0.0, longitude=0.0)
        assert gps.altitude is None
        assert gps.datum == "WGS84"

    def test_creation_invalid_latitude(self) -> None:
        """Invalid latitude raises ValueError."""
        with pytest.raises(ValueError, match="Latitude.*out of range"):
            GpsCoordinates(latitude=100.0, longitude=0.0)

    def test_creation_invalid_latitude_negative(self) -> None:
        """Invalid negative latitude raises ValueError."""
        with pytest.raises(ValueError, match="Latitude.*out of range"):
            GpsCoordinates(latitude=-91.0, longitude=0.0)

    def test_creation_invalid_longitude(self) -> None:
        """Invalid longitude raises ValueError."""
        with pytest.raises(ValueError, match="Longitude.*out of range"):
            GpsCoordinates(latitude=0.0, longitude=200.0)

    def test_creation_boundary_values(self) -> None:
        """Boundary values for lat/lon are accepted."""
        gps1 = GpsCoordinates(latitude=90.0, longitude=180.0)
        gps2 = GpsCoordinates(latitude=-90.0, longitude=-180.0)
        assert gps1.latitude == 90.0
        assert gps2.longitude == -180.0

    def test_immutability(self) -> None:
        """GpsCoordinates is immutable (frozen)."""
        gps = GpsCoordinates(latitude=37.7749, longitude=-122.4194)
        with pytest.raises(AttributeError):
            gps.latitude = 40.0  # type: ignore

    def test_backward_compatible_alias(self) -> None:
        """ImageLocation alias works as GpsCoordinates."""
        loc = ImageLocation(latitude=37.7749, longitude=-122.4194)
        assert isinstance(loc, GpsCoordinates)
        assert loc.latitude == 37.7749


@pytest.mark.unit
class TestImageExifData:
    """Test ImageExifData value object."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating ImageExifData with Tier 1 + Tier 2 fields."""
        location = GpsCoordinates(latitude=37.7749, longitude=-122.4194)
        exif = ImageExifData(
            camera_make="Sony",
            camera_model="A7III",
            f_stop=2.8,
            exposure_time="1/200",
            iso=800,
            focal_length="35mm",
            captured_at=datetime(2024, 1, 15, 14, 30, 0),
            camera_profile=CameraProfile.MIRRORLESS,
            location=location,
            flash_fired=False,
            focal_length_35mm="52mm",
            white_balance_mode="Auto",
            exposure_program="Aperture Priority",
            metering_mode="Pattern",
            orientation=1,
            raw_tags={"LensModel": "Sony FE 35mm F1.4"},
        )
        assert exif.camera_make == "Sony"
        assert exif.camera_model == "A7III"
        assert exif.f_stop == 2.8
        assert exif.iso == 800
        assert exif.location == location
        assert exif.camera_profile == CameraProfile.MIRRORLESS
        assert exif.flash_fired is False
        assert exif.orientation == 1

    def test_creation_with_no_exif_data(self) -> None:
        """Test creating ImageExifData with all fields None (no EXIF in image)."""
        exif = ImageExifData()
        assert exif.camera_make is None
        assert exif.camera_model is None
        assert exif.location is None
        assert exif.camera_profile == CameraProfile.UNKNOWN
        assert exif.flash_fired is None
        assert exif.orientation is None
        assert len(exif.raw_tags) == 0

    def test_tier_1_fields_only(self) -> None:
        """Creation with only Tier 1 universal fields."""
        exif = ImageExifData(
            camera_make="Sony",
            camera_model="A7III",
            captured_at=datetime(2024, 1, 1, 12, 0, 0),
            iso=400,
            f_stop=2.8,
            exposure_time="1/200",
            focal_length="35mm",
        )
        assert exif.camera_make == "Sony"
        assert exif.camera_profile == CameraProfile.UNKNOWN  # Default

    def test_tier_2_with_location(self) -> None:
        """Creation with Tier 2 location field."""
        gps = GpsCoordinates(latitude=37.7749, longitude=-122.4194)
        exif = ImageExifData(
            camera_make="Apple",
            camera_model="iPhone 14",
            camera_profile=CameraProfile.MOBILE,
            location=gps,
        )
        assert exif.location == gps

    def test_tier_3_raw_tags_extensibility(self) -> None:
        """raw_tags preserves camera-specific fields."""
        exif = ImageExifData(
            camera_make="Sony",
            raw_tags={
                "LensModel": "Sony FE 35mm F1.4",
                "Flash": "Flash fired",
                "Saturation": "Normal",
            },
        )
        assert exif.raw_tags["LensModel"] == "Sony FE 35mm F1.4"

    def test_default_factory_raw_tags(self) -> None:
        """Test that raw_tags defaults to empty dict (non-shared instance)."""
        exif1 = ImageExifData()
        exif2 = ImageExifData()
        # Each instance should have its own dict (frozen prevents reassign
        # but raw_tags is a mutable default that's factory-created per instance)
        assert exif1.raw_tags is not exif2.raw_tags


@pytest.mark.unit
class TestImageMetadata:
    """Test ImageMetadata domain entity."""

    def test_creation_with_all_fields(self, sample_image_metadata: ImageMetadata) -> None:
        """Test creating complete ImageMetadata matching PRD spec."""
        assert sample_image_metadata.file_hash.startswith("e3b0c442")
        assert sample_image_metadata.file_info.name == "vacation.jpg"
        assert sample_image_metadata.dimensions.width == 4000
        assert sample_image_metadata.exif.camera_make == "Sony"
        assert sample_image_metadata.labels == ["beach", "sunset", "vacation"]

    def test_file_hash_as_primary_key(self, sample_image_metadata: ImageMetadata) -> None:
        """Test that file_hash uniquely identifies a photo."""
        hash1 = sample_image_metadata.file_hash
        assert hash1 == sample_image_metadata.file_hash

    def test_deduplication_via_hash(self) -> None:
        """Test that content-based hashing enables deduplication."""
        metadata1 = ImageMetadata(
            file_hash="abc123",
            file_info=ImageFileInfo("photo.jpg", "/path1/photo.jpg", 1024, "image/jpeg"),
            dimensions=ImageDimensions(1920, 1080),
            exif=ImageExifData(),
        )
        metadata2 = ImageMetadata(
            file_hash="abc123",
            file_info=ImageFileInfo("photo.jpg", "/path2/photo.jpg", 1024, "image/jpeg"),
            dimensions=ImageDimensions(1920, 1080),
            exif=ImageExifData(),
        )
        assert metadata1.file_hash == metadata2.file_hash

    def test_immutability(self, sample_image_metadata: ImageMetadata) -> None:
        """Test that ImageMetadata is immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            sample_image_metadata.file_hash = "different_hash"  # type: ignore

        with pytest.raises(AttributeError):
            sample_image_metadata.added_at = datetime.utcnow()  # type: ignore

    def test_added_at_defaults_to_now(self) -> None:
        """Test that added_at defaults to current timestamp."""
        metadata = ImageMetadata(
            file_hash="abc123",
            file_info=ImageFileInfo("test.jpg", "/test.jpg", 1024, "image/jpeg"),
            dimensions=ImageDimensions(1920, 1080),
            exif=ImageExifData(),
        )
        assert metadata.added_at is not None
        assert isinstance(metadata.added_at, datetime)
        now = datetime.utcnow()
        assert (now - metadata.added_at).total_seconds() < 1

    def test_labels_default_to_empty_list(self) -> None:
        """Test that labels defaults to empty list."""
        metadata = ImageMetadata(
            file_hash="abc123",
            file_info=ImageFileInfo("test.jpg", "/test.jpg", 1024, "image/jpeg"),
            dimensions=ImageDimensions(1920, 1080),
            exif=ImageExifData(),
        )
        assert metadata.labels == []

    def test_metadata_with_minimal_exif(
        self, sample_image_metadata_minimal: ImageMetadata
    ) -> None:
        """Test creating metadata for image with no EXIF data."""
        assert sample_image_metadata_minimal.exif.camera_make is None
        assert sample_image_metadata_minimal.exif.captured_at is None
        assert sample_image_metadata_minimal.exif.camera_profile == CameraProfile.UNKNOWN
        assert sample_image_metadata_minimal.labels == []

    def test_equality_with_same_values(self) -> None:
        """Test that two ImageMetadata with same values are equal."""
        file_info = ImageFileInfo("test.jpg", "/test.jpg", 1024, "image/jpeg")
        dims = ImageDimensions(1920, 1080)
        exif = ImageExifData(camera_make="Canon")

        metadata1 = ImageMetadata(
            file_hash="abc123",
            file_info=file_info,
            dimensions=dims,
            exif=exif,
            labels=["test"],
        )
        metadata2 = ImageMetadata(
            file_hash="abc123",
            file_info=file_info,
            dimensions=dims,
            exif=exif,
            labels=["test"],
        )
        assert metadata1 == metadata2

    def test_different_metadata_not_equal(
        self, sample_image_metadata: ImageMetadata
    ) -> None:
        """Test that metadata with different hashes are not equal."""
        other_metadata = ImageMetadata(
            file_hash="different_hash",
            file_info=sample_image_metadata.file_info,
            dimensions=sample_image_metadata.dimensions,
            exif=sample_image_metadata.exif,
        )
        assert sample_image_metadata != other_metadata

    def test_prd_spec_compliance_all_fields_present(
        self, sample_image_metadata: ImageMetadata
    ) -> None:
        """Test that ImageMetadata contains all fields specified in PRD."""
        assert hasattr(sample_image_metadata, "file_hash")
        assert hasattr(sample_image_metadata, "file_info")
        assert hasattr(sample_image_metadata, "dimensions")
        assert hasattr(sample_image_metadata, "exif")
        assert hasattr(sample_image_metadata, "labels")
        assert hasattr(sample_image_metadata, "added_at")

        # file_info sub-fields
        assert hasattr(sample_image_metadata.file_info, "name")
        assert hasattr(sample_image_metadata.file_info, "path")
        assert hasattr(sample_image_metadata.file_info, "size_bytes")
        assert hasattr(sample_image_metadata.file_info, "mime_type")

        # dimensions sub-fields
        assert hasattr(sample_image_metadata.dimensions, "width")
        assert hasattr(sample_image_metadata.dimensions, "height")

        # exif sub-fields (Tier 1 + Tier 2)
        assert hasattr(sample_image_metadata.exif, "camera_make")
        assert hasattr(sample_image_metadata.exif, "camera_model")
        assert hasattr(sample_image_metadata.exif, "captured_at")
        assert hasattr(sample_image_metadata.exif, "location")
        assert hasattr(sample_image_metadata.exif, "camera_profile")
        assert hasattr(sample_image_metadata.exif, "flash_fired")
        assert hasattr(sample_image_metadata.exif, "raw_tags")
