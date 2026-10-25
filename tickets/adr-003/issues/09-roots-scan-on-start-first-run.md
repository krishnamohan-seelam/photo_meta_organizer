# 09: Stored roots, scan on start and first run

**What to build:** The library remembers its folders, rescans them when the app starts, and a new user is guided from empty library to scanned photos.

**Blocked by:** 05 One scan pipeline (R4); 08 Event stream (R5b)

**Status:** done (2026-10-25). Migration 0005 adds `roots` and a small `library_state` table (the "skipped the suggestions" answer); `RootStore` port + `SqliteRootStore` + `composition.build_root_store`; `application/roots.suggest_roots` (pure: folds subfolders into an ancestor, three or more siblings become their parent, never a drive root). `api/routes/roots_router.py`: `GET/POST/DELETE /api/roots`, `GET /api/roots/suggestions`, `POST /api/roots/suggestions/dismiss`; `scan_roots` runs from the lifespan when `Settings.scan_on_start` (`PMO_SCAN_ON_START`, default on) and starts a non-removing scan per readable root, skipping an offline one quietly. Frontend: `FirstRunState` (replaces the empty-library state), `RootSuggestionsDialog`, `FoldersDialog` (palette: "Watched folders…"), `hooks/useRoots.ts`.

- [x] Roots are stored in the library and scanned on start; users never need to know the word 'sync'
- [x] An empty library shows: choose a folder, watch the scan live, optional AI setup
- [x] An existing library with no roots is offered the folders found in its files as a checkbox list; nothing is watched silently; skipping leaves watching off and manual 'Scan folder' works

**Known limits:** the CLI never scans roots (only the API/desktop backend does, per the ADR) and has no command to list them; a root's scan on start is one job per root, run side by side; the watcher itself is ticket 10; the offline re-check timer and device-change hint (also ticket 10) are not built, so an unplugged root is picked up at the next start.
