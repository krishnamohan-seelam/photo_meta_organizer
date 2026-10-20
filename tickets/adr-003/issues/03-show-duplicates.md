# 03: Show duplicates (R3 API and UI)

**What to build:** A user can see that a photo exists in several places, see every path, and review duplicates without anything being deleted on disk.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** ready-for-agent

- [ ] Photo responses carry a paths list, primary first; OpenAPI types regenerated and committed
- [ ] The inspector lists every file of the photo
- [ ] A duplicates facet counts Assets with more than one file, and a filter shows them
- [ ] A duplicates view groups them, shows reclaimable space, and lets the user hide copies; it never deletes files on disk
- [ ] Contract tests (pytest and Vitest) pass
