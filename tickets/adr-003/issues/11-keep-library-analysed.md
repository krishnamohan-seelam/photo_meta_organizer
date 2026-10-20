# 11: Keep the library analysed

**What to build:** After a scan, new photos can be analysed automatically, safely, and only if the user opts in.

**Blocked by:** 07 Persisted jobs (R5a); 09 Stored roots, scan on start and first run

**Status:** ready-for-agent

- [ ] A setting, off by default
- [ ] Runs only when the model is installed, the pending count is under a threshold (default 2,000, otherwise the count is shown and the user is asked), the app is idle (and on AC power in the desktop app)
- [ ] The job is pausable and cancellable from the job pill
