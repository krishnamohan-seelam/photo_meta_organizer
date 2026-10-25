"""The real folder watcher, once: a file written under a watched folder is reported (ticket 10)."""

import threading

from photo_meta_organizer.infrastructure.watching.watchfiles_watcher import (
    WatchfilesFolderWatcher,
)


def test_a_new_file_under_a_watched_folder_is_reported(tmp_path):
    seen: list[str] = []
    heard = threading.Event()

    def on_change(path: str) -> None:
        seen.append(path)
        heard.set()

    handle = WatchfilesFolderWatcher().start([str(tmp_path)], on_change)
    try:
        heard.wait(0.5)  # let the watch settle before the change
        (tmp_path / "new.jpg").write_bytes(b"x")
        assert heard.wait(10), "no change was reported"
    finally:
        handle.stop()
        handle.stop()  # safe to stop twice
    assert any(p.endswith("new.jpg") for p in seen)


def test_a_watch_of_a_missing_folder_ends_quietly(tmp_path):
    handle = WatchfilesFolderWatcher().start([str(tmp_path / "not-there")], lambda path: None)
    handle.stop()
