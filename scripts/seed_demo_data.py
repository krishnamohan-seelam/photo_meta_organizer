"""Seed sample photos and metadata into photos.db for interactive demo testing."""

import os
from datetime import datetime, timezone
from PIL import Image, ImageDraw

from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_photos")
os.makedirs(SAMPLE_DIR, exist_ok=True)

photos_spec = [
    {
        "filename": "DSC04928_Tokyo_Tower_Sunset.jpg",
        "hash": "3f8b9a1c4d2e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4",
        "color": (230, 80, 50),
        "make": "Sony",
        "model": "ILCE-7M4 (A7 IV)",
        "f_stop": 2.8,
        "shutter": "1/250s",
        "iso": 400,
        "focal": "35.0 mm",
        "date": datetime(2026, 5, 14, 18, 42, 10, tzinfo=timezone.utc),
        "lat": 35.6586,
        "lon": 139.7454,
        "labels": ["travel", "japan", "architecture", "sunset"],
        "rating": 5,
        "flagged": True,
    },
    {
        "filename": "IMG_8392_Kyoto_Bamboo_Path.jpg",
        "hash": "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b",
        "color": (40, 160, 90),
        "make": "Canon",
        "model": "EOS R5",
        "f_stop": 4.0,
        "shutter": "1/125s",
        "iso": 800,
        "focal": "24.0 mm",
        "date": datetime(2026, 5, 16, 8, 15, 30, tzinfo=timezone.utc),
        "lat": 35.0167,
        "lon": 135.6713,
        "labels": ["travel", "nature", "landscape", "green"],
        "rating": 4,
        "flagged": True,
    },
    {
        "filename": "iPhone_15Pro_Shibuya_Night.jpg",
        "hash": "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
        "color": (30, 40, 100),
        "make": "Apple",
        "model": "iPhone 15 Pro",
        "f_stop": 1.78,
        "shutter": "1/40s",
        "iso": 1250,
        "focal": "24.0 mm",
        "date": datetime(2026, 5, 16, 22, 30, 15, tzinfo=timezone.utc),
        "lat": 35.6595,
        "lon": 139.7005,
        "labels": ["travel", "urban", "night", "street"],
        "rating": 4,
        "flagged": False,
    },
    {
        "filename": "_DSC9102_Fuji_Sunrise.jpg",
        "hash": "7c8d9e0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f",
        "color": (240, 180, 70),
        "make": "Nikon",
        "model": "Z8",
        "f_stop": 8.0,
        "shutter": "1/500s",
        "iso": 100,
        "focal": "70.0 mm",
        "date": datetime(2026, 5, 18, 5, 10, 0, tzinfo=timezone.utc),
        "lat": 35.3606,
        "lon": 138.7274,
        "labels": ["travel", "landscape", "mountain", "sunrise"],
        "rating": 5,
        "flagged": True,
    },
    {
        "filename": "DSC05101_Golden_Gate_Fog.jpg",
        "hash": "5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c",
        "color": (180, 100, 70),
        "make": "Sony",
        "model": "ILCE-7M4 (A7 IV)",
        "f_stop": 5.6,
        "shutter": "1/320s",
        "iso": 200,
        "focal": "50.0 mm",
        "date": datetime(2026, 4, 10, 15, 20, 0, tzinfo=timezone.utc),
        "lat": 37.8199,
        "lon": -122.4783,
        "labels": ["landscape", "usa", "sanfrancisco"],
        "rating": 3,
        "flagged": False,
    },
    {
        "filename": "IMG_9021_London_BigBen.jpg",
        "hash": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c",
        "color": (100, 120, 150),
        "make": "Canon",
        "model": "EOS R5",
        "f_stop": 4.0,
        "shutter": "1/200s",
        "iso": 100,
        "focal": "35.0 mm",
        "date": datetime(2026, 3, 22, 14, 0, 0, tzinfo=timezone.utc),
        "lat": 51.5007,
        "lon": -0.1246,
        "labels": ["travel", "uk", "architecture", "city"],
        "rating": 4,
        "flagged": True,
    },
]

repo = SqliteRepository(db_path="photos.db")

for spec in photos_spec:
    img_path = os.path.join(SAMPLE_DIR, spec["filename"])
    if not os.path.exists(img_path):
        img = Image.new("RGB", (1920, 1080), color=spec["color"])
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 1870, 1030], outline=(255, 255, 255), width=8)
        img.save(img_path, format="JPEG", quality=90)

    size = os.path.getsize(img_path)
    metadata = ImageMetadata(
        file_hash=spec["hash"],
        file_info=ImageFileInfo(
            name=spec["filename"],
            path=img_path,
            size_bytes=size,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1920, height=1080),
        exif=ImageExifData(
            camera_make=spec["make"],
            camera_model=spec["model"],
            f_stop=spec["f_stop"],
            exposure_time=spec["shutter"],
            iso=spec["iso"],
            focal_length=spec["focal"],
            captured_at=spec["date"],
            camera_profile=(
                CameraProfile.MOBILE
                if spec["make"] == "Apple"
                else CameraProfile.MIRRORLESS
            ),
            location=GpsCoordinates(
                latitude=spec["lat"], longitude=spec["lon"], datum="WGS84"
            ),
            flash_fired=False,
            orientation=1,
            raw_tags={"Artist": "Krishna Mohan"},
        ),
        labels=spec["labels"],
        rating=spec["rating"],
        flagged=spec["flagged"],
    )
    repo.save(metadata)

repo.close()
print("Successfully seeded photos.db with sample photos!")
