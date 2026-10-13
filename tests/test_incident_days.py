"""Incident tracking over a whole window (app/services/incident_days.py)."""
import asyncio
import json
from datetime import date

from app.services import incident_days as svc


def _arts(day, n, start=0):
    return [{"uri": f"u{day}-{i}", "publication_date": f"{day}T10:00:00Z", "title": f"t{i}",
             "summary": "s", "news_source": "src"} for i in range(start, start + n)]


def test_pack_shares_batches_across_small_days_and_splits_big_ones():
    arts = _arts("2026-10-01", 30) + _arts("2026-10-02", 50) + _arts("2026-10-03", 230)
    batches = svc._pack("T", ["2026-10-01", "2026-10-02", "2026-10-03"], arts)
    sizes = [len(b["articles"]) for b in batches]
    assert sum(sizes) == 310                      # every article goes in a batch
    assert max(sizes) <= svc.BATCH_SIZE
    assert batches[0]["days"] == ["2026-10-01", "2026-10-02"]
    assert all(b["days"] == ["2026-10-03"] for b in batches[1:])


def test_combine_keeps_strongest_wording_and_every_article():
    a = {"name": "weak", "significance": "low", "article_uris": ["x"], "slice_day": "2026-10-02",
         "published": "2026-10-02"}
    b = {"name": "strong", "significance": "high", "article_uris": ["y", "z"],
         "slice_day": "2026-10-01", "published": "2026-10-01"}
    out = svc._combine([a, b])
    assert out["name"] == "strong"
    assert out["article_uris"] == ["y", "z", "x"]  # in day order
    assert out["published"] == "2026-10-01"
    assert out["merged_from"] == 2


def test_merge_falls_back_to_ranking_when_the_call_fails(monkeypatch):
    class Boom:
        @staticmethod
        def get_instance(name):
            raise RuntimeError("no model")
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Boom)
    cands = [{"name": "A thing", "significance": "low", "article_uris": ["1"]},
             {"name": "a thing", "significance": "high", "article_uris": ["2"]},
             {"name": "Other", "significance": "medium", "article_uris": ["3"]}]
    out, method = asyncio.run(svc.merge_and_rank(cands, ["T"], date(2026, 10, 1), date(2026, 10, 2),
                                                 "m", limit=5))
    assert method == "ranked"
    assert [o["name"] for o in out] == ["a thing", "Other"]   # duplicate name dropped, high first


def test_read_batch_maps_article_numbers_to_uris(monkeypatch):
    answer = json.dumps([
        {"n": "Acme fined", "t": "incident", "st": "regulatory_action", "s": "high", "a": [2, 1],
         "d": "2026-10-01", "x": "A regulator fined Acme."},
        {"n": "No source", "t": "event", "s": "low", "a": [9], "d": None, "x": "?"},
        {"n": "Bad date", "t": "event", "s": "medium", "a": [3], "d": "2027", "x": "Plan."},
    ])

    class Model:
        async def agenerate_response(self, messages, **kw):
            return answer

    class Factory:
        @staticmethod
        def get_instance(name):
            return Model()
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Factory)
    monkeypatch.setattr(ai, "extract_content", lambda r: r)

    class Req:
        model = "m"
    arts = _arts("2026-10-01", 2) + _arts("2026-10-02", 1, start=5)
    out = asyncio.run(svc._read_batch(Req(), "T", arts, ""))
    assert [o["name"] for o in out] == ["Acme fined", "Bad date"]   # uncited record dropped
    assert out[0]["article_uris"] == ["u2026-10-01-1", "u2026-10-01-0"]
    assert out[0]["event_date"] == "2026-10-01" and out[0]["published"] == "2026-10-01"
    assert out[1]["event_date"] is None                              # "2027" is not a date
