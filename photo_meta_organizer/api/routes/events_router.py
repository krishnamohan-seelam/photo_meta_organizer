"""``GET /api/events``: what changed, pushed as server-sent events (ADR-003 R5b).

Same origin as the UI, so the ``pmo_token`` cookie rides along and ``api/auth.py`` needs no
change. See :mod:`photo_meta_organizer.application.events` for the ids and the replay buffer.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from photo_meta_organizer.api.dependencies import get_event_bus
from photo_meta_organizer.api.routes.photos_router import job_response
from photo_meta_organizer.application.events import (
    JOB_FINISHED,
    LIBRARY_CHANGED,
    RESYNC,
    Event,
    EventBus,
)
from photo_meta_organizer.application.jobs import Job

events_router = APIRouter(prefix="/api/events", tags=["events"])

KEEPALIVE_SECONDS = 15.0  # an idle connection gets a comment this often so proxies keep it
RETRY_MS = 3000  # how long the browser waits before reconnecting

# Methods and path prefixes whose success changes what the library shows. Searches are POSTs
# too but only read; jobs announce their own end.
_MUTATING_METHODS = frozenset({"POST", "PATCH", "DELETE", "PUT"})
_LIBRARY_PREFIXES = ("/api/photos", "/api/collections", "/api/ai-tags", "/api/files")


def changes_library(method: str, path: str, status_code: int) -> bool:
    """Whether a finished request edited photos, collections or AI suggestions."""
    return method in _MUTATING_METHODS and status_code < 400 and path.startswith(_LIBRARY_PREFIXES)


def job_event_handler(bus: EventBus) -> Callable[[str, Job], None]:
    """The ``JobManager`` callback: publish the job, and say the library may have changed
    when one ends (even a failed or cancelled job may have saved some photos)."""

    def publish(event_type: str, job: Job) -> None:
        bus.publish(event_type, job_response(job).model_dump(mode="json"))
        if event_type == JOB_FINISHED:
            bus.publish(LIBRARY_CHANGED, {"reason": job.kind})

    return publish


def _frame(event: Event) -> str:
    return f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(event.data)}\n\n"


async def _stream(bus: EventBus, cursor: int | None) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    if cursor is None:
        cursor = bus.last_id  # a new connection hears what happens from now on
    while True:
        events = await asyncio.to_thread(bus.read_after, cursor, KEEPALIVE_SECONDS)
        if events is None:  # missed more than the buffer holds, or an id from another run
            cursor = bus.last_id
            yield _frame(Event(cursor, RESYNC))
        elif events:
            for event in events:
                yield _frame(event)
            cursor = events[-1].id
        elif bus.closed:  # the server is stopping and everything has been sent
            return
        else:
            yield ": keepalive\n\n"


@events_router.get(
    "",
    summary="Stream job progress and library changes",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_events(
    bus: EventBus = Depends(get_event_bus),
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Server-sent events: ``job_progress``, ``job_finished``, ``library_changed`` and
    ``resync``, each with an increasing ``id``.

    Reconnect with ``Last-Event-ID`` to be replayed what you missed (the last 200 events are
    kept). If you were away longer, or the server restarted, you get one ``resync`` event:
    reload the photos, facets and jobs instead. Job events carry the job as
    ``GET /api/jobs/{id}`` shows it.
    """
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    return StreamingResponse(
        _stream(bus, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
