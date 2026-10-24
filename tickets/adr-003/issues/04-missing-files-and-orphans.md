# 04: Missing files and orphans

**What to build:** A file that disappears (or whose drive is unplugged) is flagged, not forgotten, and nothing is deleted without an explicit remove-missing request limited to the scanned roots.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** done (2026-10-24). Migration 0003 adds `files.missing_since`; the API shows it as `file_info.missing_since`. The ticket 05 rename of `--cleanup-deleted` to `remove_missing` is still to come.

- [x] Files not found by a scan get missing_since; it is cleared when the path reappears
- [x] The UI shows a 'file missing' badge
- [x] remove_missing deletes only files under the roots actually scanned; an unreadable or absent root deletes nothing and fails
- [x] An Asset becomes an orphan only when its last file row is removed, then it is deleted with its curation, embeddings and tags
- [x] Moving a folder out and back loses nothing
