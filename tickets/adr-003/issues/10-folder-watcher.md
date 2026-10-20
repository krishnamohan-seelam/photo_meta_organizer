# 10: Folder watcher and offline roots

**What to build:** New and changed photos appear without a manual scan, and an unplugged drive is handled calmly.

**Blocked by:** 09 Stored roots, scan on start and first run

**Status:** ready-for-agent

- [ ] A FolderWatcher port with a watchfiles implementation and a fake for tests; runs in the backend only while the desktop backend or API runs, never from the CLI
- [ ] Events collect into a set of directories; after 5 s of quiet only those directories are scanned, with a full root scan above 1,000 distinct directories
- [ ] An unreadable root is shown as offline with missing badges and no error toast; it is re-checked on a timer and on a device-change hint
