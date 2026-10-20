# 12: Remove from library, with undo

**What to build:** Removing photos from the library is undoable for a short time and stays removed afterwards; the files on disk are never touched.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage); 05 One scan pipeline (R4)

**Status:** ready-for-agent

- [ ] Batch remove confirms the count, then soft-deletes (removed_at) and hides the photos; an Undo toast clears it
- [ ] The photos are purged (with curation, embeddings, tags, collection membership) after about 30 s or on the next app start
- [ ] Purging records the file paths in ignored_files; scans skip those paths, but a file whose content changed is scanned as a different photo
- [ ] Settings has a 'Removed from library' list with Restore
