"""The event bus behind ``GET /api/events`` (ADR-003 R5b)."""

import threading

from photo_meta_organizer.application.events import EventBus


def test_ids_only_grow() -> None:
    bus = EventBus()
    ids = [bus.publish("library_changed").id for _ in range(3)]
    assert ids == [1, 2, 3] and bus.last_id == 3


def test_a_reader_gets_what_came_after_its_last_id() -> None:
    bus = EventBus()
    for i in range(3):
        bus.publish("job_progress", {"n": i})
    events = bus.read_after(1, timeout=0)
    assert [e.id for e in events or []] == [2, 3]
    assert events and events[0].data == {"n": 1}


def test_a_reader_with_nothing_new_waits_then_gets_an_empty_list() -> None:
    bus = EventBus()
    bus.publish("library_changed")
    assert bus.read_after(1, timeout=0.05) == []


def test_a_waiting_reader_wakes_when_something_is_published() -> None:
    bus = EventBus()
    got: list = []
    reader = threading.Thread(target=lambda: got.append(bus.read_after(0, timeout=5)))
    reader.start()
    bus.publish("library_changed")
    reader.join(5)
    assert [e.id for e in got[0]] == [1]


def test_only_the_last_events_are_kept_and_an_older_gap_is_a_resync() -> None:
    bus = EventBus(capacity=3)
    for _ in range(5):
        bus.publish("job_progress")
    assert [e.id for e in bus.read_after(2, timeout=0) or []] == [3, 4, 5]  # just reaches
    assert bus.read_after(1, timeout=0) is None  # event 2 is gone


def test_an_id_from_another_run_is_a_resync() -> None:
    bus = EventBus()
    bus.publish("library_changed")
    assert bus.read_after(40, timeout=0) is None


def test_closing_releases_a_waiting_reader() -> None:
    bus = EventBus()
    got: list = []
    reader = threading.Thread(target=lambda: got.append(bus.read_after(0, timeout=30)))
    reader.start()
    bus.close()
    reader.join(5)
    assert not reader.is_alive() and got == [[]] and bus.closed


def test_wire_ids_carry_the_run_and_only_this_runs_ids_are_trusted() -> None:
    bus, other = EventBus(), EventBus()
    assert bus.run_id != other.run_id
    assert bus.parse_wire_id(bus.wire_id(7)) == (7, False)
    assert bus.parse_wire_id(other.wire_id(7)) == (None, True)
    assert bus.parse_wire_id(None) == (None, False)
    assert bus.parse_wire_id("7") == (None, False)
