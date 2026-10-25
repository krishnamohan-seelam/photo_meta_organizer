# 10: Folder watcher and offline roots

**What to build:** New and changed photos appear without a manual scan, and an unplugged drive is handled calmly.

**Blocked by:** 09 Stored roots, scan on start and first run

**Status:** done (2026-10-25). `FolderWatcher`/`WatchHandle` port (`application/interfaces/folder_watcher.py`), `infrastructure/watching/watchfiles_watcher.WatchfilesFolderWatcher` (new dependency `watchfiles`, collected in the PyInstaller bundle), `tests/fakes.FakeFolderWatcher`. `application/root_watcher.RootWatcher` keeps the readable roots watched, collects the folders where a photo changed, and after 5 s of quiet scans only those (each as deep as it can be, none inside another; a deleted folder is scanned from its nearest existing parent; more than 1,000 distinct folders scan the whole root; a folder whose job is busy is retried after the next quiet spell). Every 30 s, and on `recheck()` / `POST /api/roots/recheck`, it tests the roots: an unreadable one stops being watched without a scan or an error, and one that comes back is watched again and scanned. The API lifespan starts and stops it (`Settings.watch_folders`, `PMO_WATCH_FOLDERS=0` turns it off; the CLI never does). The SPA calls the recheck when the window regains focus. All timing goes through `tick()`, so tests use a fake clock.

- [x] A FolderWatcher port with a watchfiles implementation and a fake for tests; runs in the backend only while the desktop backend or API runs, never from the CLI
- [x] Events collect into a set of directories; after 5 s of quiet only those directories are scanned, with a full root scan above 1,000 distinct directories
- [x] An unreadable root is shown as offline with missing badges and no error toast; it is re-checked on a timer and on a device-change hint
