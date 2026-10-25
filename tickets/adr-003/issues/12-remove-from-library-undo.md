# 12: Remove from library, with undo

**What to build:** Removing photos from the library is undoable for a short time and stays removed afterwards; the files on disk are never touched.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage); 05 One scan pipeline (R4)

**Status:** done (2026-10-25). Migration 0007: `assets.removed_at`, `ignored_files(path, file_hash, size_bytes, mtime, removed_at)`, and the views `live_assets` / `asset_view` / `photo_view` leave removed Assets out, so search, facets, counts, duplicates, geo, pending analysis, AI tag counts and the review queue all skip them. Repository: `remove_assets`, `restore_assets`, `purge_removed(older_than)`, `list_ignored`, `forget_ignored`. `application/trash.TrashPurger` purges after `UNDO_SECONDS` (30) on a 5 s check and everything at start (`create_app` lifespan); purging records each present File's path, size and mtime in `ignored_files` and deletes the Asset (curation, embeddings, tags, collection membership cascade). The scan marks a NEW path as `IGNORED` while its size and mtime still match, so it is skipped (job counts show `ignored`); a different size or mtime is new content, scanned normally, and saving a File at a path drops its ignore entry. API: `DELETE /api/photos/{hash}` and batch `delete` now remove softly (`undo_seconds`), `POST /api/photos/restore`, `GET /api/removed`, `POST /api/removed/restore` (forgets and scans the folder). UI: Remove in the selection dock with a count confirmation, a toast with Undo (toasts can carry one action), and the palette's 'Removed from library…' dialog with Restore. Files on disk are never touched.

- [x] Batch remove confirms the count, then soft-deletes (removed_at) and hides the photos; an Undo toast clears it
- [x] The photos are purged (with curation, embeddings, tags, collection membership) after about 30 s or on the next app start
- [x] Purging records the file paths in ignored_files; scans skip those paths, but a file whose content changed is scanned as a different photo
- [x] Settings has a 'Removed from library' list with Restore

**Known limits:** a file removed, purged, then only touched (same content, new mtime) is scanned as new again; the ADR's 'only the path is ignored' is approximated by size and mtime so no file is hashed for it. The removed list is a dialog in the palette, not a Settings page (there is none).
