""""Check now" with no group runs every active group through check_single_group.

It used to call check_keywords(None): every keyword on the global collectors,
social groups' keywords through the news pipeline, inactive groups included,
no social evaluator. The "Auto-ingest now" button read an empty table with a
broken query and stamped the topic 'general'. Both now go through
check_all_groups. No database: the facade is a stub.
"""
import asyncio
from types import SimpleNamespace

from app.tasks.keyword_monitor import KeywordMonitor


def _monitor(groups, outcomes):
    mon = KeywordMonitor.__new__(KeywordMonitor)
    mon.db = SimpleNamespace(facade=SimpleNamespace(get_active_keyword_groups=lambda: groups))
    seen = []

    async def single(group, progress_callback=None, username=None):
        seen.append(group["id"])
        out = outcomes[group["id"]]
        if isinstance(out, Exception):
            raise out
        return out

    async def never(*a, **k):
        raise AssertionError("check_keywords(None) must not run")

    mon.check_single_group = single
    mon.check_keywords = never
    return mon, seen


def test_every_active_group_runs_through_check_single_group():
    groups = [{"id": 9, "name": "AI"}, {"id": 17, "name": "SOC Social"}, {"id": 34, "name": "EV"}]
    outcomes = {9: {"success": True, "new_articles": 5, "keywords_processed": 3},
                17: {"success": False, "error": "quota", "new_articles": 0},
                34: RuntimeError("boom")}
    mon, seen = _monitor(groups, outcomes)
    res = asyncio.new_event_loop().run_until_complete(mon.check_all_groups())
    assert seen == [9, 17, 34]
    assert res["success"] and res["groups_checked"] == 2 and res["new_articles"] == 5
    assert [e["group_id"] for e in res["errors"]] == [17, 34]


def test_all_groups_failing_is_a_failure():
    mon, _ = _monitor([{"id": 1, "name": "x"}], {1: {"success": False, "error": "down"}})
    res = asyncio.new_event_loop().run_until_complete(mon.check_all_groups())
    assert res["success"] is False
