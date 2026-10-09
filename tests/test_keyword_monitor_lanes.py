"""The keyword monitor's lanes: a slow group must not hold the others back.

Uses fake monitors, so no collector, database or network is touched.
"""

from __future__ import annotations

import asyncio

from app.tasks import keyword_monitor as km


class _Facade:
    def __init__(self, due):
        self.due = due
        self.claimed = []

    def get_due_keyword_groups(self):
        # A claim moves next_check_at forward, as the real UPDATE does.
        claimed = {g for g, _ in self.claimed}
        return [dict(g) for g in self.due if g["id"] not in claimed]

    def claim_keyword_group(self, group_id, retry_seconds):
        self.claimed.append((group_id, retry_seconds))


class _Db:
    def __init__(self, facade):
        self.facade = facade


class _Monitor:
    """Runs a group by waiting on the event named for it."""

    def __init__(self, db, gates):
        self.db = db
        self.gates = gates
        self.ran = []

    async def check_single_group(self, group):
        self.ran.append(group["id"])
        await self.gates[group["id"]].wait()
        return {"success": True, "new_articles": 1}


def _setup(due_ids, lanes):
    gates = {g: asyncio.Event() for g in due_ids}
    facade = _Facade([{"id": g, "name": f"g{g}"} for g in due_ids])
    db = _Db(facade)
    monitors = [_Monitor(db, gates) for _ in range(lanes)]
    return gates, facade, monitors


def test_a_slow_group_occupies_one_lane_and_the_next_group_runs_beside_it():
    async def go():
        gates, facade, monitors = _setup([10, 32, 440], lanes=2)
        running = {}
        await km._dispatch_due_groups(monitors, running)
        await asyncio.sleep(0)
        assert set(running) == {10, 32}          # two lanes, two groups
        assert [g for g, _ in facade.claimed] == [10, 32]

        gates[32].set()                          # the small group finishes
        await asyncio.sleep(0)
        out = await km._dispatch_due_groups(monitors, running)
        await asyncio.sleep(0)
        assert out["groups_checked"] == 1 and out["total_articles"] == 1
        assert set(running) == {10, 440}         # 10 still running, 440 started
        for g in gates.values():
            g.set()
        await asyncio.gather(*(t for t, _m, _n in running.values()))
    asyncio.run(go())


def test_a_running_group_is_never_started_twice():
    async def go():
        gates, facade, monitors = _setup([10], lanes=2)
        running = {}
        await km._dispatch_due_groups(monitors, running)
        facade.claimed.clear()          # as if the claim failed: still due in the DB
        await km._dispatch_due_groups(monitors, running)
        await asyncio.sleep(0)
        assert sum(m.ran.count(10) for m in monitors) == 1
        gates[10].set()
        await asyncio.gather(*(t for t, _m, _n in running.values()))
    asyncio.run(go())


def test_lane_count_reads_the_environment_and_stays_in_bounds(monkeypatch):
    monkeypatch.setenv("KEYWORD_MONITOR_LANES", "3")
    assert km._lane_count() == 3
    monkeypatch.setenv("KEYWORD_MONITOR_LANES", "99")
    assert km._lane_count() == 6
    monkeypatch.setenv("KEYWORD_MONITOR_LANES", "nope")
    assert km._lane_count() == 2
    monkeypatch.delenv("KEYWORD_MONITOR_LANES")
    assert km._lane_count() == 2
