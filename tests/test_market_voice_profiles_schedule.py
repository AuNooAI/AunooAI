"""The scheduled voice profiling finishes inside the tick.

The market tick runs under asyncio.run on its own thread (97bd00af, 9 Oct
2026). The profiling step used to start a background task and return; when
the tick returned, asyncio.run cancelled that task before it built anything.
From 10 to 14 Oct every scheduled run reported 25 queued and built none, so
aisecwire's voices card held only the 25 Bluesky accounts profiled by hand.
"""
import asyncio
from datetime import datetime, timezone

from app.services import market_voice_profiles as mvp
from app.tasks import market_monitor as mm


class _Conn:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_scheduled_profiling_builds_every_profile_under_asyncio_run(monkeypatch):
    built, closed = [], {}

    async def fake_profile(db, platform, handle, market_name):
        await asyncio.sleep(0.01)  # a real build awaits the platform and the model
        built.append((platform, handle))
        return {"handle": handle}

    voices = [{"platform": p, "author": h, "account": {}}
              for p, h in (("twitter", "a"), ("reddit", "b"), ("bluesky", "c"))]
    monkeypatch.setattr(mvp, "profile_one", fake_profile)
    monkeypatch.setattr(mvp, "PACE_SECONDS", 0)
    monkeypatch.setattr(mm, "_is_due", lambda *a, **k: True)
    monkeypatch.setattr(mm, "get_database_instance", lambda: object())
    monkeypatch.setattr(mm.mc, "open_run", lambda *a, **k: 1)
    monkeypatch.setattr(mm.mc, "close_run", lambda conn, run_id, **kw: closed.update(kw))
    import app.services.market_analysis as man
    monkeypatch.setattr(man, "top_voices", lambda *a, **k: {"voices": voices})
    monkeypatch.setattr(mvp, "link_vendor_accounts", lambda *a, **k: {"linked": 0})
    mvp._JOBS.pop(99, None)

    conn = _Conn()
    asyncio.run(mm._profile_voices(conn, {"id": 99, "name": "Test market"},
                                   datetime.now(timezone.utc)))

    assert sorted(built) == [("bluesky", "c"), ("reddit", "b"), ("twitter", "a")]
    assert closed["status"] == "succeeded" and closed["new"] == 3
    assert mvp.status(99)["state"] == "done"
