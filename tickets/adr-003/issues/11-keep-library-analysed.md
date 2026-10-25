# 11: Keep the library analysed

**What to build:** After a scan, new photos can be analysed automatically, safely, and only if the user opts in.

**Blocked by:** 07 Persisted jobs (R5a); 09 Stored roots, scan on start and first run

**Status:** done (2026-10-25). `application/keep_analysed.KeepAnalysed` (setting `keep_analysed` in the library's `library_state`, via the new `StateStore` port/`SqliteStateStore`; off by default) checks every 30 s and starts an ordinary `analyze` job only when: the AI runtime and model are installed (never downloads), no more than `Settings.keep_analysed_max` (`PMO_KEEP_ANALYSED_MAX`, default 2,000) photos wait (above it the state is `needs_approval`: the job pill shows the count with an Analyse button), no job is active and none is paused, the user has been still for 30 s (`ActivityTracker`, touched by every non-GET request except the recheck hint), and, on the desktop app (`Settings.ac_power_only`), the computer is not on battery (`infrastructure/power.on_battery`: Windows API, `pmset`, sysfs; unknown means plugged in). A run that analysed nothing is not repeated until the count of waiting photos changes. `GET/PUT /api/analysis/keep`; `JobManager.pause` + `POST /api/jobs/{id}/pause` end a job `interrupted` (message 'Paused. ...') so Resume / Dismiss apply; the pill has Pause and Cancel for every job but the model download. UI: `KeepAnalysedToggle` in the AI setup dialog says in words what it is doing.

- [x] A setting, off by default
- [x] Runs only when the model is installed, the pending count is under a threshold (default 2,000, otherwise the count is shown and the user is asked), the app is idle (and on AC power in the desktop app)
- [x] The job is pausable and cancellable from the job pill
