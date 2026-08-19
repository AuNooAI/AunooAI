"""What the encoder is actually sent, and what happens when it misbehaves.

The encoder takes a title and a content field separately. Article indexing used
to hand it one blob and let it split on the first newline, which meant the
"title" it embedded was whatever line the body happened to start with — a
dateline, a standfirst, a "Sign up for our newsletter" banner. The title is
known; it should be passed as the title.

Also covered: the encoder's failure modes stay loud (no silent placeholder
vector), and the async paths do not run blocking HTTP on the event loop.
"""

import asyncio
import time

import pytest

from app import vector_store_pgvector as vs


class RecordingClient:
    """Stands in for httpx.Client and records the JSON body it was given."""

    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None):
        RecordingClient.calls.append(json)
        return FakeResponse({"embedding": [0.0] * vs.EMBEDDING_DIM})


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self._payload


@pytest.fixture
def recorded(monkeypatch):
    RecordingClient.calls = []
    import httpx

    monkeypatch.setattr(httpx, "Client", RecordingClient)
    return RecordingClient.calls


# ---------------------------------------------------------------------------
# Encoder input construction
# ---------------------------------------------------------------------------

def test_the_real_title_is_sent_as_the_title_even_when_raw_text_exists():
    title, content = vs.build_article_encoder_input({
        "title": "ASML halts China shipments",
        "raw": "AMSTERDAM, Aug 19 (Reuters) - The company said on Tuesday...",
    })

    assert title == "ASML halts China shipments"
    assert content.startswith("AMSTERDAM")
    assert "ASML halts" not in content


def test_the_title_is_used_when_only_a_summary_exists():
    title, content = vs.build_article_encoder_input({
        "title": "Export licence revoked",
        "summary": "The regulator withdrew the licence on Monday.",
    })

    assert title == "Export licence revoked"
    assert content == "The regulator withdrew the licence on Monday."


def test_raw_text_wins_over_summary_for_the_body():
    _, content = vs.build_article_encoder_input({
        "title": "T",
        "raw": "full article text",
        "summary": "short summary",
    })
    assert content == "full article text"


def test_a_title_only_article_still_embeds():
    title, content = vs.build_article_encoder_input({"title": "Just a headline"})
    assert title == "Just a headline"
    assert content == ""


def test_tags_lead_the_content_so_truncation_cannot_drop_them():
    title, content = vs.build_article_encoder_input({
        "title": "Niche Brand in the news",
        "tags": ["Niche Brand", "supply chain"],
        "raw": "x" * 200,
    })

    assert title == "Niche Brand in the news"
    assert content.startswith("Tags: Niche Brand, supply chain\n")
    assert content.rstrip().endswith("x")


def test_a_string_tag_field_is_accepted():
    _, content = vs.build_article_encoder_input({
        "title": "T", "tags": "one, two", "summary": "body",
    })
    assert content.startswith("Tags: one, two")


def test_an_article_with_nothing_to_embed_is_skipped():
    assert vs.build_article_encoder_input({"uri": "u"}) == ("", "")
    assert vs.build_article_encoder_input({"title": "  ", "raw": ""}) == ("", "")


def test_the_encoder_payload_carries_title_and_content_separately(recorded):
    vs._encode_fields("A headline", "Tags: x\nThe body")

    assert recorded == [{
        "title": "A headline",
        "description": "",
        "content": "Tags: x\nThe body",
    }]


def test_upsert_sends_the_article_title_not_the_first_line_of_the_body(recorded, monkeypatch):
    captured = {}

    class FakeConn:
        def execute(self, *a, **kw):
            captured["executed"] = True

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class FakeDB:
        def _temp_get_connection(self):
            return FakeConn()

    monkeypatch.setattr(vs, "get_database_instance", lambda: FakeDB())

    vs.upsert_article({
        "uri": "u1",
        "title": "Chip export rules tighten",
        "raw": "By Jane Roe\nAMSTERDAM — the rules changed on Tuesday.",
    })

    assert recorded[0]["title"] == "Chip export rules tighten"
    assert recorded[0]["content"].startswith("By Jane Roe")
    assert captured.get("executed")


def test_a_query_is_embedded_as_a_title(recorded):
    vs.embed_query("semiconductor export controls")
    assert recorded[0]["title"] == "semiconductor export controls"


def test_an_empty_query_is_refused():
    with pytest.raises(RuntimeError, match="empty query"):
        vs.embed_query("   ")


# ---------------------------------------------------------------------------
# Failure modes stay loud
# ---------------------------------------------------------------------------

def _client_returning(payload, status=200, raises=None):
    class Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None):
            if raises:
                raise raises
            return FakeResponse(payload, status)

    return Client


@pytest.mark.parametrize("payload,status,raises,match", [
    ({"embedding": [0.0] * 1536}, 200, None, "1536d, expected 768d"),
    ({"embedding": "not a list"}, 200, None, "non-list embedding"),
    ({"unexpected": True}, 200, None, "unexpected payload"),
    (None, 500, None, "unreachable"),
    (None, 200, ConnectionError("refused"), "unreachable"),
])
def test_encoder_problems_raise_rather_than_returning_a_placeholder(
    monkeypatch, payload, status, raises, match
):
    import httpx

    monkeypatch.setattr(httpx, "Client", _client_returning(payload, status, raises))
    with pytest.raises(RuntimeError, match=match):
        vs._encode_fields("title", "content")


def test_embedding_empty_text_is_refused():
    with pytest.raises(RuntimeError, match="empty text"):
        vs._encode_fields("", "")


# ---------------------------------------------------------------------------
# Async safety
# ---------------------------------------------------------------------------

def test_a_slow_encoder_does_not_block_the_event_loop(monkeypatch):
    """The heartbeat must keep ticking while the encoder takes its time."""

    class SlowClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None):
            time.sleep(0.4)  # blocking, as a real HTTP call is
            return FakeResponse({"embedding": [0.0] * vs.EMBEDDING_DIM})

    import httpx

    monkeypatch.setattr(httpx, "Client", SlowClient)

    from app.services.emerging_topics.theme_proposer import ThemeProposer

    async def scenario():
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.02)
                ticks += 1

        proposer = ThemeProposer()
        beat = asyncio.create_task(heartbeat())
        await proposer._get_embedding("a query")
        await beat
        return ticks

    ticks = asyncio.run(scenario())
    assert ticks >= 15, (
        "the event loop stalled during the encoder call — the blocking HTTP "
        f"request is running on the loop (only {ticks} heartbeats)"
    )


def test_encoder_errors_reach_the_caller_through_the_thread_boundary(monkeypatch):
    import httpx

    monkeypatch.setattr(
        httpx, "Client", _client_returning(None, 200, ConnectionError("refused"))
    )

    from app.services.emerging_topics.theme_proposer import ThemeProposer

    proposer = ThemeProposer()
    with pytest.raises(RuntimeError, match="unreachable"):
        asyncio.run(proposer._get_embedding("a query"))
