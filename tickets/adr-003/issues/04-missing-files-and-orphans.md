# 04: Missing files and orphans

**What to build:** A file that disappears (or whose drive is unplugged) is flagged, not forgotten, and nothing is deleted without an explicit remove-missing request limited to the scanned roots.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** ready-for-agent

- [ ] Files not found by a scan get missing_since; it is cleared when the path reappears
- [ ] The UI shows a 'file missing' badge
- [ ] remove_missing deletes only files under the roots actually scanned; an unreadable or absent root deletes nothing and fails
- [ ] An Asset becomes an orphan only when its last file row is removed, then it is deleted with its curation, embeddings and tags
- [ ] Moving a folder out and back loses nothing
