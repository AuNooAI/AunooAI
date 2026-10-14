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


def test_combine_puts_the_headline_members_articles_first():
    # The write-up reads the first few articles, so they must be the ones the
    # kept headline is about, not the earliest in the group.
    early = {"name": "Medicare breach", "significance": "medium", "article_uris": ["au1", "au2"],
             "slice_day": "2026-09-24"}
    later = {"name": "US sites disclosure", "significance": "high", "article_uris": ["us1"],
             "slice_day": "2026-09-26"}
    out = svc._combine([early, later])
    assert out["name"] == "US sites disclosure"
    assert out["article_uris"] == ["us1", "au1", "au2"]


def test_merge_names_each_group_and_shows_the_name_next_round(monkeypatch):
    seen = []

    class Model:
        async def agenerate_response(self, messages, **kw):
            seen.append(messages[-1]["content"])
            return json.dumps([{"event": "Agent breached Australia's Medicare portal", "ids": [0, 1]}])

    class Factory:
        @staticmethod
        def get_instance(name):
            return Model()
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Factory)
    monkeypatch.setattr(ai, "extract_content", lambda r: r)
    cands = [{"name": f"n{i}", "description": f"what {i}", "significance": "medium",
              "article_uris": [str(i)]} for i in range(2)]
    out, _ = asyncio.run(svc._merge_chunk(cands, 5, ["T"], date(2026, 10, 1), date(2026, 10, 2), "m"))
    assert out[0]["merge_event"] == "Agent breached Australia's Medicare portal"
    assert "n0 — what 0" in seen[0]
    asyncio.run(svc._merge_chunk(out, 5, ["T"], date(2026, 10, 1), date(2026, 10, 2), "m"))
    assert "Agent breached Australia's Medicare portal" in seen[1]


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
    assert method.startswith("ranked")
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


def test_merge_refuses_an_implausibly_large_group(monkeypatch):
    big = json.dumps([{"ids": list(range(30))}, {"ids": [30]}])

    class Model:
        async def agenerate_response(self, messages, **kw):
            return big

    class Factory:
        @staticmethod
        def get_instance(name):
            return Model()
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Factory)
    monkeypatch.setattr(ai, "extract_content", lambda r: r)
    cands = [{"name": f"n{i}", "significance": "medium", "article_uris": [str(i)]} for i in range(31)]
    out, method = asyncio.run(svc.merge_and_rank(cands, ["T"], date(2026, 10, 1), date(2026, 10, 2),
                                                 "m", limit=5))
    assert method.startswith("llm")
    assert [o["name"] for o in out] == ["n30"]     # the 30-finding lump was not merged


def test_each_topic_gets_its_places(monkeypatch):
    class Boom:
        @staticmethod
        def get_instance(name):
            raise RuntimeError("no model")      # plain ranking keeps the test offline
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Boom)
    big = [{"name": f"big{i}", "topic": "Big", "significance": "high", "article_uris": [f"b{i}"]}
           for i in range(10)]
    small = [{"name": f"small{i}", "topic": "Small", "significance": "low", "article_uris": [f"s{i}"]}
             for i in range(5)]
    out, _ = asyncio.run(svc.merge_and_rank(big + small, ["Big", "Small"], date(2026, 10, 1),
                                            date(2026, 10, 2), "m", limit=4, per_topic=2))
    assert [o["topic"] for o in out[:4]] == ["Big"] * 4      # the open places go to significance
    assert [o["name"] for o in out[4:]] == ["small0", "small1"]
    assert all(o.get("topic_place") for o in out[4:])


def _model_answering(monkeypatch, answer):
    class Model:
        async def agenerate_response(self, messages, **kw):
            return answer(messages[-1]["content"])

    class Factory:
        @staticmethod
        def get_instance(name):
            return Model()
    import app.ai_models as ai
    monkeypatch.setattr(ai, "LiteLLMModel", Factory)
    monkeypatch.setattr(ai, "extract_content", lambda r: r)


def test_merge_keeps_apart_a_group_that_would_pass_the_cap_across_rounds(monkeypatch):
    # Two groups from an earlier round, 15 findings each: one more merge would
    # make a 30-finding card, so they stay two cards, in the group's place.
    _model_answering(monkeypatch, lambda p: json.dumps([{"event": "campaign", "ids": [0, 1]}, {"ids": [2]}]))
    items = [{"name": "a", "significance": "high", "merged_from": 15, "article_uris": ["a"]},
             {"name": "b", "significance": "high", "merged_from": 15, "article_uris": ["b"]},
             {"name": "c", "significance": "low", "article_uris": ["c"]}]
    out, used_llm = asyncio.run(svc._merge_chunk(items, 5, ["T"], date(2026, 10, 1), date(2026, 10, 2), "m"))
    assert used_llm
    assert [o["name"] for o in out] == ["a", "b", "c"]
    assert all("merge_event" not in o for o in out[:2])


def test_topic_places_skip_a_repeat_of_a_chosen_card(monkeypatch):
    def answer(prompt):
        if "OFFERED cards" in prompt:
            return json.dumps({"repeats": [0]})      # small0 repeats a chosen card
        return json.dumps([{"ids": [i]} for i in range(30)])
    _model_answering(monkeypatch, answer)
    big = [{"name": f"big{i}", "topic": "Big", "significance": "high", "article_uris": [f"b{i}"]}
           for i in range(4)]
    small = [{"name": f"small{i}", "topic": "Small", "significance": "low", "article_uris": [f"s{i}"]}
             for i in range(5)]
    out, _ = asyncio.run(svc.merge_and_rank(big + small, ["Big", "Small"], date(2026, 10, 1),
                                            date(2026, 10, 2), "m", limit=4, per_topic=2))
    assert [o["name"] for o in out if o.get("topic_place")] == ["small1", "small2"]

