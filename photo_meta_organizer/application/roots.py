"""Roots: the folders a library scans on its own (ADR-003 R11, ticket 09; see GLOSSARY.md).

A library that predates roots knows its photos only by their files' paths.
:func:`suggest_roots` turns those paths into a short list of folders to offer, so the user
ticks the ones to watch. Nothing is ever added silently.

:func:`scan_roots` is the one automatic piece of work (ADR-003 R5a): at start, every root that
can be read is scanned, one job each.
"""

import logging
import os
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from photo_meta_organizer.application.interfaces.root_store import RootStore
from photo_meta_organizer.application.jobs import JobConflictError, JobManager, Work

logger = logging.getLogger(__name__)

MIN_SIBLINGS_TO_MERGE = 3  # this many sibling folders become one suggestion for their parent

# What a scan of a root does: add new photos and re-read edited ones; never remove anything.
# Stored with the job, so resuming it runs the same scan.
SCAN_PARAMS: dict[str, Any] = {
    "remove_missing": False,
    "reprocess_modified": True,
    "index_new": True,
}

# (folder, params) -> the work of a scan job; built by whoever composes the application.
WorkFactory = Callable[[str, dict[str, Any]], Work]


@dataclass(frozen=True)
class Root:
    """A folder the library scans: when the app starts, and when the user asks."""

    path: str
    added_at: datetime


@dataclass(frozen=True)
class SuggestedRoot:
    """A folder worth watching, with how many recorded files lie in it."""

    path: str
    file_count: int


def suggest_roots(folder_counts: Mapping[str, int]) -> list[SuggestedRoot]:
    """Fewest folders that cover every folder in ``folder_counts`` (folder -> file count).

    A folder inside another listed folder is folded into it. Three or more sibling folders
    become their parent, unless the parent is a drive or filesystem root, which is far
    too broad to scan. The user can untick any suggestion, so this errs towards short lists.
    Pure: it looks at the strings, never at the disk.
    """
    kept: dict[Path, int] = {}
    for folder in sorted(folder_counts, key=lambda f: len(Path(f).parts)):
        path = Path(folder)
        owner = next((k for k in kept if path.is_relative_to(k)), path)
        kept[owner] = kept.get(owner, 0) + folder_counts[folder]

    by_parent: dict[Path, list[Path]] = defaultdict(list)
    for path in kept:
        by_parent[path.parent].append(path)
    merged: dict[Path, int] = {}
    for parent, children in by_parent.items():
        too_broad = parent == parent.parent  # a drive or "/"
        if len(children) >= MIN_SIBLINGS_TO_MERGE and not too_broad:
            merged[parent] = sum(kept[c] for c in children)
        else:
            merged.update({c: kept[c] for c in children})
    return [SuggestedRoot(str(p), n) for p, n in sorted(merged.items(), key=lambda kv: str(kv[0]))]


def is_online(path: str) -> bool:
    """Whether a root can be read right now (an unplugged drive cannot)."""
    return os.path.isdir(path)


def start_scan(jobs: JobManager, make_work: WorkFactory, folder: str) -> str | None:
    """Start a scan job of ``folder``; its id, or ``None`` if another job holds the folder."""
    try:
        return jobs.submit("sync", folder, make_work(folder, SCAN_PARAMS), params=SCAN_PARAMS).id
    except JobConflictError:
        return None


def scan_roots(
    roots: RootStore,
    jobs: JobManager,
    make_work: WorkFactory,
    online: Callable[[str], bool] = is_online,
) -> list[str]:
    """Scan every root that can be read; returns the ids of the jobs started.

    A root that is offline is skipped quietly, a root whose folder is already being scanned is
    left to that job, and one scan failing to start never stops the others: the app must start
    whatever state its roots are in.
    """
    started = []
    for root in roots.list_roots():
        if not online(root.path):
            continue
        try:
            job_id = start_scan(jobs, make_work, root.path)
        except Exception:  # noqa: BLE001 - startup must survive a bad root
            logger.exception("Could not start the scan of %s", root.path)
            continue
        if job_id is not None:
            started.append(job_id)
    return started
