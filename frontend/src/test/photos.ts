import type { PhotoMetadata } from '../types/metadata'

/** A complete photo record as the API returns it, with `overrides` applied. */
export function makePhoto(overrides: Partial<PhotoMetadata> = {}): PhotoMetadata {
  const hash = overrides.file_hash ?? 'a'.repeat(64)
  return {
    file_hash: hash,
    file_info: {
      name: `${hash.slice(0, 6)}.jpg`,
      path: `/photos/${hash.slice(0, 6)}.jpg`,
      size_bytes: 2_097_152,
      mime_type: 'image/jpeg',
    },
    dimensions: { width: 6000, height: 4000 },
    exif: {
      camera_make: 'Sony',
      camera_model: 'A7 IV',
      camera_profile: 'raw',
      captured_at: '2024-03-20T15:30:00',
      exposure_program: null,
      exposure_time: '1/250',
      f_stop: 2.8,
      flash_fired: false,
      focal_length: '35 mm',
      focal_length_35mm: null,
      iso: 400,
      location: null,
      metering_mode: null,
      orientation: 1,
      raw_tags: {},
      white_balance_mode: null,
    },
    labels: [],
    rating: null,
    flagged: false,
    added_at: '2026-01-01T00:00:00',
    ...overrides,
  }
}
