# 03: Show duplicates (R3 API and UI)

**What to build:** A user can see that a photo exists in several places, see every path, and review duplicates without anything being deleted on disk.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** done (2026-10-25). Migration 0006 adds `files.hidden_at`; `StoredFile.hidden_at` and `is_copy`; the repository port gets `files_of(hashes)` (one query, primary first), `duplicate_groups(limit, offset)` and `set_file_hidden(path, hidden)`; `SearchQuery.duplicates` and `LibraryStats.duplicate_count/reclaimable_bytes`. API: `paths` on every photo response (`photos_router.to_responses`), `GET /api/duplicates`, `POST /api/files/hide`, `SearchRequest.duplicates` (query token `dupes:yes|no`). UI: `FilesSection` in the inspector, a Duplicates row and a review link in the Library panel, `DuplicatesDialog` (also in the palette). A copy counts when its file is on disk and not hidden; hiding keeps the File recorded, so a scan does not add it back, and it never touches a file on disk.

- [x] Photo responses carry a paths list, primary first; OpenAPI types regenerated and committed
- [x] The inspector lists every file of the photo
- [x] A duplicates facet counts Assets with more than one file, and a filter shows them
- [x] A duplicates view groups them, shows reclaimable space, and lets the user hide copies; it never deletes files on disk
- [x] Contract tests (pytest and Vitest) pass
