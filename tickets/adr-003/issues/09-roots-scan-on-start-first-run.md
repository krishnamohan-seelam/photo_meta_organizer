# 09: Stored roots, scan on start and first run

**What to build:** The library remembers its folders, rescans them when the app starts, and a new user is guided from empty library to scanned photos.

**Blocked by:** 05 One scan pipeline (R4); 08 Event stream (R5b)

**Status:** ready-for-agent

- [ ] Roots are stored in the library and scanned on start; users never need to know the word 'sync'
- [ ] An empty library shows: choose a folder, watch the scan live, optional AI setup
- [ ] An existing library with no roots is offered the folders found in its files as a checkbox list; nothing is watched silently; skipping leaves watching off and manual 'Scan folder' works
