"""Emerging-topics API: who may call what, and how the stream is framed.

Two things are checked here.

Authorization: detection and every endpoint that mutates a global emerging-topic
record are admin-only. They were all merely session-checked, so any logged-in
user could start a detection run, clear every detected theme, retire a topic, or
rewrite the notification settings. The check reads the real router object, so a
route added later without ``require_admin`` fails the suite instead of shipping
open.

SSE framing: the stream must be valid Server-Sent Events — a named event, one
data line, and a terminating blank line — for progress, completion, and failure
alike. The old writer emitted a bare ``data:`` line and left the client to guess
the outcome from the payload's shape.
"""

import asyncio
import json

import pytest
from fastapi.routing import APIRoute

from app.routes import emerging_topics_routes as routes
from app.security.session import require_admin, verify_session

# Endpoints that change global state: they start runs, delete or retire topics
# other users can see, or rewrite the schedule and notification settings.
ADMIN_ONLY = {
    ("POST", "/api/emerging-topics/detect"),
    ("POST", "/api/emerging-topics/detect/sync"),
    ("POST", "/api/emerging-topics/detect/batch"),
    ("DELETE", "/api/emerging-topics/topics"),
    ("DELETE", "/api/emerging-topics/topics/{topic_id}"),
    ("POST", "/api/emerging-topics/topics/{topic_id}/retire"),
    ("POST", "/api/emerging-topics/topics/{topic_id}/restore"),
    ("POST", "/api/emerging-topics/topics/{topic_id}/save-horizons"),
    ("POST", "/api/emerging-topics/schedule/settings"),
    ("POST", "/api/emerging-topics/schedule/run-now"),
    ("POST", "/api/emerging-topics/notifications/settings"),
    ("POST", "/api/emerging-topics/notifications/test"),
}

# Per-user bookmarks. A normal user manages their own.
USER_SCOPED = {
    ("POST", "/api/emerging-topics/topics/{topic_id}/track"),
    ("DELETE", "/api/emerging-topics/topics/{topic_id}/track"),
}


def _dependency_calls(route):
    seen = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call is not None:
                seen.add(sub.call)
            walk(sub)

    walk(route.dependant)
    return seen


def _api_routes():
    return [r for r in routes.router.routes if isinstance(r, APIRoute)]


def _method_paths(route):
    return [(m, route.path) for m in sorted(route.methods) if m != "HEAD"]


def test_every_endpoint_requires_a_session():
    api_routes = _api_routes()
    assert api_routes, "no routes found — the check would pass vacuously"

    open_routes = [
        f"{m} {p}"
        for route in api_routes
        for (m, p) in _method_paths(route)
        if not ({verify_session, require_admin} & _dependency_calls(route))
    ]
    assert not open_routes, f"unauthenticated endpoints: {open_routes}"


def test_global_mutations_require_admin():
    found = {}
    for route in _api_routes():
        for key in _method_paths(route):
            found[key] = _dependency_calls(route)

    missing = [k for k in ADMIN_ONLY if k not in found]
    assert not missing, f"these endpoints moved or were removed: {missing}"

    not_gated = [f"{m} {p}" for (m, p) in ADMIN_ONLY if require_admin not in found[(m, p)]]
    assert not not_gated, f"global mutations reachable by any user: {not_gated}"


def test_writes_beyond_the_admin_set_are_deliberate():
    """A new POST/DELETE must be classified, not quietly left session-only."""
    unclassified = []
    for route in _api_routes():
        for (method, path) in _method_paths(route):
            if method not in ("POST", "PUT", "PATCH", "DELETE"):
                continue
            if (method, path) in ADMIN_ONLY or (method, path) in USER_SCOPED:
                continue
            # Future Horizons only computes a projection; it writes nothing.
            if path.endswith("/future-horizons"):
                continue
            unclassified.append(f"{method} {path}")
    assert not unclassified, (
        "these write endpoints are neither admin-gated nor per-user; classify "
        f"them in this test: {unclassified}"
    )


# ---------------------------------------------------------------------------
# SSE framing
# ---------------------------------------------------------------------------

def parse_frames(raw):
    """Split a serialized SSE stream the way a conforming client would."""
    frames = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        frames.append((event, data))
    return frames


def test_frames_are_named_and_blank_line_terminated():
    raw = routes.sse_frame({"event": "progress", "progress": 25, "message": "x"})
    assert raw.startswith("event: progress\ndata: ")
    assert raw.endswith("\n\n")
    assert len(parse_frames(raw)) == 1


def test_error_frames_carry_a_machine_readable_code():
    raw = routes.sse_error("encoder is down", code="embedding_unavailable", run_id=7)
    (event, payload), = parse_frames(raw)
    assert event == "error"
    assert payload["status"] == "failed"
    assert payload["code"] == "embedding_unavailable"
    assert payload["run_id"] == 7


def test_payloads_never_break_the_framing():
    """A newline inside a message must not look like the end of a frame."""
    raw = routes.sse_frame({
        "event": "progress",
        "message": "line one\nline two\n\nlooks like a frame break",
    })
    frames = parse_frames(raw)
    assert len(frames) == 1
    assert "line two" in frames[0][1]["message"]


class StubStreamService:
    """Yields a fixed sequence of service events."""

    def __init__(self, events):
        self.events = events
        self.lock_seen = None

    async def run_detection_streaming(self, topic_filter=None, days_back=None,
                                      run_lock=None):
        self.lock_seen = run_lock
        for event in self.events:
            yield event


class SpyLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


def drive_stream(service, lock, request=None):
    request = request or routes.DetectionRequest(topic="climate")
    original = routes._build_service
    routes._build_service = lambda req: service
    try:
        async def run():
            return "".join([
                chunk async for chunk in routes.stream_detection(request, lock)
            ])
        return asyncio.run(run())
    finally:
        routes._build_service = original


def test_stream_emits_progress_then_complete_and_releases_the_lock():
    service = StubStreamService([
        {"event": "progress", "progress": 10, "message": "starting", "run_id": 1},
        {"event": "complete", "status": "completed", "progress": 100,
         "emerging_topics": [], "total_emerging_topics": 0, "run_id": 1},
    ])
    lock = SpyLock()

    frames = parse_frames(drive_stream(service, lock))

    assert [event for event, _ in frames] == ["progress", "complete"]
    assert frames[-1][1]["status"] == "completed"
    assert lock.released
    assert service.lock_seen is lock, "the endpoint's lock must be reused, not re-taken"


def test_stream_forwards_a_failure_as_an_error_frame():
    service = StubStreamService([
        {"event": "progress", "progress": 10, "message": "starting"},
        {"event": "error", "status": "failed", "code": "embedding_unavailable",
         "message": "DeBERTa encoder unreachable", "run_id": 3},
    ])
    lock = SpyLock()

    frames = parse_frames(drive_stream(service, lock))

    assert [event for event, _ in frames] == ["progress", "error"]
    assert frames[-1][1]["code"] == "embedding_unavailable"
    assert lock.released


def test_an_exception_inside_the_stream_becomes_an_error_frame():
    class Exploding:
        async def run_detection_streaming(self, **kwargs):
            yield {"event": "progress", "progress": 5, "message": "starting"}
            raise RuntimeError("connection reset")

    lock = SpyLock()
    frames = parse_frames(drive_stream(Exploding(), lock))

    assert frames[-1][0] == "error"
    assert "connection reset" in frames[-1][1]["message"]
    assert lock.released, "the lock must be released even when the run explodes"


def test_lock_conflict_is_a_409_with_a_code():
    from app.services.emerging_topics import DetectionAlreadyRunning

    exc = routes._lock_conflict(DetectionAlreadyRunning("climate"))

    assert exc.status_code == 409
    assert exc.detail["code"] == "detection_already_running"
    assert exc.detail["topic_filter"] == "climate"


# ---------------------------------------------------------------------------
# Notification settings validation
# ---------------------------------------------------------------------------

def test_notification_settings_reject_unknown_filters():
    with pytest.raises(Exception):
        routes.NotificationSettingsRequest(detection_type_filters=["banana"])


def test_notification_settings_store_legacy_values_under_their_v2_name():
    request = routes.NotificationSettingsRequest(
        detection_type_filters=["new_cluster", "accelerating"]
    )
    assert request.detection_type_filters == ["llm_proposed", "accelerating"]
