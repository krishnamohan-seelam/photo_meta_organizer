"""Roots: the folders a library scans on its own (ADR-003 R11, ticket 09; see GLOSSARY.md).

A library that predates roots knows its photos only by their files' paths.
:func:`suggest_roots` turns those paths into a short list of folders to offer, so the user
ticks the ones to watch. Nothing is ever added silently.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MIN_SIBLINGS_TO_MERGE = 3  # this many sibling folders become one suggestion for their parent


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
