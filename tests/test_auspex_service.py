"""AuspexService, QueryRouter and OptimizedContextManager without a model or a database.

Auspex is 1,800 statements of chat orchestration that produce the answers
customers read, and until 11 Oct 2026 the suite touched 9% of it. Nothing
here calls a model or Postgres: the vector store, the reranker, litellm, the
plugin registry and the database wrapper are small fakes that record what
they were asked, so each test states what the orchestration must hand to the
model and what it must save.

The tests that matter most are the ones about message order. Every context
block (tool results, URL lookups, plugin output) must sit before the user's
final message, because a conversation that ends on an assistant turn is a
prefill and the Claude 5 family rejects it outright.
"""

import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace

import pytest

from app.services import auspex_service as aus
from app.services.auspex_service import (
    AuspexService, OptimizedContextManager, QueryRouter,
    classify_query_depth, classify_query_intent, get_format_block,
    build_system_prompt, build_versatile_prompt, _exclude_rejected_filter,
)


def _run(coro):
    return asyncio.run(coro)


async def _collect(agen):
    return [chunk async for chunk in agen]


# ── Fakes ────────────────────────────────────────────────────────────────────

def _art(i, topic="Topic A", **over):
    a = dict(uri=f"https://ex.org/{topic}/{i}", url=f"https://ex.org/{topic}/{i}",
             title=f"Article {i} on {topic}", summary=f"Summary {i}. It will likely increase. Second sentence.",
             category=["Policy", "Funding", "Research"][i % 3],
             sentiment=["Positive", "Negative", "Neutral"][i % 3],
             future_signal="Weak Signal", time_to_impact="Short-Term",
             publication_date=f"2026-10-{(i % 28) + 1:02d} 09:00:00", news_source=f"source{i % 4}.org",
             topic=topic, tags="ai,soc", similarity_score=round(0.9 - i * 0.01, 3))
    a.update(over)
    return a


def _vector_hit(a):
    return {"metadata": dict(a), "score": a.get("similarity_score", 0.5)}


class FakeFacade:
    def __init__(self, db):
        self.db = db
        self.topic_counts = {"Topic A": {"article_count": 100}, "Topic B": {"article_count": 50},
                             "Wiley - Brand Watch": {"article_count": 30}}
        self.recent = []
        self.calls = []

    def get_topics_with_article_counts(self):
        return dict(self.topic_counts)

    def get_recent_articles_by_topic(self, topic_name=None, limit=10, start_date=None, end_date=None):
        self.calls.append(("recent", topic_name, limit, start_date, end_date))
        rows = [a for a in self.recent if topic_name is None or a["topic"] == topic_name]
        return rows[:limit]


class FakeDb:
    """What AuspexService and QueryRouter ask of app.database.Database."""
    db_type = "postgresql"

    def __init__(self):
        self.chats = {}
        self.messages = defaultdict(list)
        self.prompts = {}
        self.users = {"alice"}
        self.brands = []            # rows for bw_brands
        self.by_name = {}           # token -> article rows for the named-brand fallback
        self.search_calls = []
        self.search_result = ([], 0)
        self.facade = FakeFacade(self)
        self._next = 1

    # chats
    def create_auspex_chat(self, topic, title=None, user_id=None, profile_id=None, metadata=None):
        cid, self._next = self._next, self._next + 1
        self.chats[cid] = dict(id=cid, topic=topic, title=title, user_id=user_id,
                               profile_id=profile_id, metadata=metadata or {})
        return cid

    def get_auspex_chat(self, chat_id):
        return dict(self.chats[chat_id]) if chat_id in self.chats else None

    def get_auspex_messages(self, chat_id):
        return [dict(m) for m in self.messages[chat_id]]

    def add_auspex_message(self, chat_id, role, content, model_used=None, tokens_used=None, metadata=None):
        self.messages[chat_id].append(dict(role=role, content=content, model_used=model_used,
                                           tokens_used=tokens_used, metadata=metadata))
        return len(self.messages[chat_id])

    def update_auspex_chat_metadata(self, chat_id, metadata):
        self.chats[chat_id]["metadata"].update(metadata)
        return True

    def update_auspex_chat_profile(self, chat_id, profile_id):
        self.chats[chat_id]["profile_id"] = profile_id
        return True

    def delete_auspex_chat(self, chat_id):
        return self.chats.pop(chat_id, None) is not None

    def get_auspex_chats(self, topic=None, user_id=None, limit=50):
        return [c for c in self.chats.values() if topic is None or c["topic"] == topic][:limit]

    # prompts
    def get_auspex_prompt(self, name):
        return self.prompts.get(name)

    def get_default_auspex_prompt(self):
        return next((p for p in self.prompts.values() if p.get("is_default")), None)

    def create_auspex_prompt(self, name, title, content, description=None, is_default=False, user_created=None):
        self.prompts[name] = dict(name=name, title=title, content=content, description=description,
                                  is_default=is_default, user_created=user_created)
        return len(self.prompts)

    def get_auspex_prompts(self):
        return list(self.prompts.values())

    def update_auspex_prompt(self, name, title=None, content=None, description=None):
        return name in self.prompts

    def delete_auspex_prompt(self, name):
        return self.prompts.pop(name, None) is not None

    # users / articles
    def get_user(self, username):
        return {"username": username} if username in self.users else None

    def search_articles(self, **kw):
        self.search_calls.append(kw)
        return self.search_result

    def fetch_all(self, query, params=None):
        if "bw_brands" in query:
            return [{"display_name": b} for b in self.brands]
        if "FROM articles" in query:
            token = (params[0] if params else "%").strip("%")
            return list(self.by_name.get(token, []))
        return []


class FakeAnalyze:
    options = {"categories": ["Policy", "Funding", "Research"], "sentiments": ["Positive", "Negative", "Neutral"],
               "futureSignals": ["Weak Signal"], "timeToImpacts": ["Short-Term"], "driverTypes": []}

    def __init__(self, db=None):
        self.db = db

    def get_topic_options(self, topic=None):
        return dict(self.options)


class FakeRegistry:
    def __init__(self, tool=None, result=None, handler=True):
        self.tool, self.result, self.handler = tool, result, handler
        self.executed = []

    def find_matching_tools(self, query, min_score=0.3):
        return [(self.tool, 0.9)] if self.tool else []

    def get_handler(self, name):
        return object() if self.handler else None

    async def execute_tool(self, name, params, context):
        self.executed.append((name, params, sorted(context)))
        return self.result

    def get_all_tools(self):
        return [self.tool] if self.tool else []


class FakeChartService:
    def generate_chart_marker(self, chart_type, articles, title=None):
        return f"<!-- CHART_DATA:{json.dumps({'type': chart_type, 'n': len(articles), 'title': title})}:END_CHART -->"


class FakeModel:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def generate_response(self, messages):
        self.calls.append(messages)
        return self.reply(messages) if callable(self.reply) else self.reply


def _chunks(*texts):
    async def gen():
        for t in texts:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))])
    return gen()


def _stub_shadows(monkeypatch):
    """The Jev shadows and decisions run on their own threads against the DB; keep them out."""
    from app.services import auspex_route_shadow, auspex_compaction_shadow
    from app.retrieval import rerank_shadow
    monkeypatch.setattr(auspex_route_shadow, "schedule", lambda *a, **k: None)
    monkeypatch.setattr(auspex_route_shadow, "decide_enabled", lambda: False)
    monkeypatch.setattr(auspex_compaction_shadow, "schedule", lambda *a, **k: None)
    monkeypatch.setattr(rerank_shadow, "schedule", lambda *a, **k: None)
    monkeypatch.setattr(rerank_shadow, "decide_enabled", lambda: False)


@pytest.fixture
def svc(monkeypatch):
    """An AuspexService wired to fakes, skipping the constructor's live lookups."""
    _stub_shadows(monkeypatch)
    monkeypatch.setattr(aus, "AnalyzeDB", FakeAnalyze)
    monkeypatch.setitem(aus._dedicated_bw_cache, "block", "")
    monkeypatch.setitem(aus._dedicated_bw_cache, "at", 1e18)

    async def _no_rerank(query, candidates, *, top_k, **kw):
        return list(candidates)[:top_k]
    monkeypatch.setattr(aus, "rerank", _no_rerank)
    monkeypatch.setattr(aus, "overfetch_limit", lambda k: k)

    s = AuspexService.__new__(AuspexService)
    s.db = FakeDb()
    s.tools = None
    s.search_router = None
    s.chart_service = FakeChartService()
    s.tool_registry = FakeRegistry()
    s.context_manager = OptimizedContextManager(model_context_limit=128000)
    s.query_router = QueryRouter(s.db, analyze_db=FakeAnalyze(s.db))
    s._last_chat_articles = []
    return s


def _stream(monkeypatch, *texts):
    """Make litellm.acompletion stream the given chunks; return the recorded call kwargs."""
    calls = []

    async def fake(**kw):
        calls.append(kw)
        return _chunks(*texts)
    monkeypatch.setattr(aus.litellm, "acompletion", fake)
    return calls


# ── Pure classifiers and prompt builders ─────────────────────────────────────

@pytest.mark.parametrize("q,depth", [
    ("what is the sentiment on AI regulation?", "quick"),
    ("how many articles mention Nvidia", "quick"),
    ("Give me a comprehensive analysis of the SOC automation market", "deep"),
    ("Compare and contrast vendor strategies and funding and hiring trends", "deep"),
    ("Why did funding fall? And which vendors were hit?", "deep"),
    ("Summarise the main themes in coverage of battery recycling this month", "standard"),
])
def test_query_depth(q, depth):
    assert classify_query_depth(q) == depth


@pytest.mark.parametrize("q,intent", [
    ("hello", "casual"), ("Thanks!", "casual"), ("good morning", "casual"),
    ("what can you do", "system"), ("Can you help me?", "system"),
    ("what are the latest news developments on Nvidia", "research"),
    ("compare coverage between Reuters and the FT", "research"),
    ("Nvidia", "general"),
])
def test_query_intent(q, intent):
    assert classify_query_intent(q) == intent


def test_format_block_defaults_to_standard():
    assert get_format_block("quick") is aus.AUSPEX_QUICK_FORMAT
    assert get_format_block("deep") is aus.AUSPEX_DEEP_FORMAT
    assert get_format_block("nonsense") is aus.AUSPEX_STANDARD_FORMAT


def test_build_system_prompt_adds_the_right_format(svc):
    assert "Response Format: BRIEF" in build_system_prompt("how many articles mention Nvidia")
    assert "DEEP ANALYSIS" in build_system_prompt(query_depth="deep")
    assert "Response Format: STANDARD" in build_system_prompt()
    assert build_system_prompt().startswith(aus.AUSPEX_CORE_PROMPT)


def test_versatile_prompt_always_carries_data_integrity_and_the_date(svc):
    for q in ("hello", "what can you do", "latest news on Nvidia", "Nvidia"):
        p = build_versatile_prompt(q)
        assert "Data Integrity Standards" in p
        assert "Today's date is:" in p and "{current_date}" not in p
    assert "Casual Conversation Style" in build_versatile_prompt("hello")
    assert "Answering Questions About Your Capabilities" in build_versatile_prompt("what can you do")
    assert "Response Format" in build_versatile_prompt("latest news on Nvidia")
    assert "Response Format" not in build_versatile_prompt("Nvidia")


def test_exclude_rejected_filter_composes_with_existing_filters():
    ex = {"ingest_status": {"$ne": "filtered_relevance"}}
    assert _exclude_rejected_filter(None) == ex
    assert _exclude_rejected_filter({}) == ex
    assert _exclude_rejected_filter({"topic": "T"}) == {"$and": [{"topic": "T"}, ex]}
    assert _exclude_rejected_filter({"$and": [{"a": 1}, {"b": 2}]}) == {"$and": [{"a": 1}, {"b": 2}, ex]}


# ── The dedicated Brand Watcher block ────────────────────────────────────────

def _bw_db(brands, topics):
    class _D:
        def fetch_all(self, q, params=None):
            if "bw_brands" in q:
                return [{"display_name": n, "is_primary": p} for n, p in brands]
            return [{"topic": t} for t in topics]
    return _D()


def test_bw_block_names_brands_and_real_topic_strings(monkeypatch):
    import app.database as dbmod
    monkeypatch.setitem(aus._dedicated_bw_cache, "block", None)
    monkeypatch.setattr(dbmod, "get_database_instance",
                        lambda: _bw_db([("Wiley", True), ("Elsevier", False)],
                                       ["Wiley - Brand Watch", "Market Monitoring Publishing"]))
    monkeypatch.delenv("BW_DEDICATED_MODE", raising=False)
    block = aus._dedicated_bw_block()
    assert "Wiley (primary), Elsevier" in block
    assert '"Wiley - Brand Watch", "Market Monitoring Publishing"' in block
    assert "Coverage Topics in This Workspace" in block
    assert "Dedicated Brand Monitoring Workspace" not in block
    # cached: a second call does not hit the database
    monkeypatch.setattr(dbmod, "get_database_instance", lambda: (_ for _ in ()).throw(RuntimeError("no")))
    assert aus._dedicated_bw_block() == block


def test_bw_block_is_empty_when_nothing_to_map_and_strict_when_dedicated(monkeypatch):
    import app.database as dbmod
    monkeypatch.setitem(aus._dedicated_bw_cache, "block", None)
    monkeypatch.setattr(dbmod, "get_database_instance", lambda: _bw_db([], []))
    monkeypatch.delenv("BW_DEDICATED_MODE", raising=False)
    assert aus._dedicated_bw_block() == ""

    monkeypatch.setitem(aus._dedicated_bw_cache, "block", None)
    monkeypatch.setenv("BW_DEDICATED_MODE", "1")
    monkeypatch.setattr(dbmod, "get_database_instance", lambda: _bw_db([("Oviva", True)], []))
    block = aus._dedicated_bw_block()
    assert "Dedicated Brand Monitoring Workspace" in block and "Oviva (primary)" in block
    assert "steer back" in block


def test_bw_block_survives_a_database_error(monkeypatch):
    import app.database as dbmod
    monkeypatch.setitem(aus._dedicated_bw_cache, "block", None)
    monkeypatch.setattr(dbmod, "get_database_instance", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.delenv("BW_DEDICATED_MODE", raising=False)
    assert aus._dedicated_bw_block() == ""


# ── OptimizedContextManager ──────────────────────────────────────────────────

def test_budget_allocation_scales_with_context_and_favours_articles_on_mega_models():
    small = OptimizedContextManager(100_000).allocate_context_budget("comprehensive")
    assert small == {"system_prompt": 12_000, "articles": 73_000, "instructions": 10_000, "response_buffer": 5_000}
    mega = OptimizedContextManager(1_000_000).allocate_context_budget("comprehensive")
    assert mega["articles"] == 850_000
    assert OptimizedContextManager(1000).allocate_context_budget("unknown") == \
        OptimizedContextManager(1000).allocate_context_budget("comprehensive")


@pytest.mark.parametrize("msg,kind", [
    ("latest trends in funding", "trend_analysis"), ("a detailed look at vendors", "detailed_analysis"),
    ("quick overview please", "quick_summary"), ("who is buying whom", "comprehensive"),
])
def test_query_type(msg, kind):
    assert OptimizedContextManager(1000).determine_query_type(msg) == kind


def test_compress_article_keeps_links_and_tags_uncut():
    cm = OptimizedContextManager(1000)
    a = _art(1, title="T" * 200, tags=["Nvidia", "SOC", None], summary="One. Two will increase. Three.")
    c = cm.compress_article(a, relevance_score=0.9)
    assert c["title"] == "T" * 100 and c["uri"] == a["uri"] and c["url"] == a["url"]
    assert c["tags"] == "Nvidia, SOC" and c["score"] == 0.9
    assert cm.compress_article(a, relevance_score=0.6)["title"] == "T" * 80
    low = cm.compress_article(dict(a, similarity_score=0.42), relevance_score=0.0)
    assert low["title"] == "T" * 60 and low["score"] == 0.42
    assert cm.compress_article({"title": None, "tags": "x,y"})["id"] == "unknown"
    assert cm.compress_article({"tags": "x,y"})["tags"] == "x,y"


def test_key_sentences_prefer_forward_looking_ones():
    cm = OptimizedContextManager(1000)
    text = "Boring intro. Revenue will likely increase next year. Another dull line. Impact expected soon."
    out = cm.extract_key_sentences(text, max_sentences=2)
    assert "Revenue will likely increase" in out and "Impact expected soon" in out
    assert "Boring intro" not in out
    assert cm.extract_key_sentences("", 2) == ""
    assert cm.extract_key_sentences("One. Two", 2) == "One. Two"


def test_ensure_diversity_spreads_across_categories_and_never_duplicates():
    cm = OptimizedContextManager(1000)
    pool = [_art(i, category=f"Cat{i % 5}", sentiment=["Positive", "Negative", "Neutral", "Critical"][i % 4])
            for i in range(60)]
    picked = cm.ensure_diversity(pool, 20)
    assert len(picked) == 20
    assert len({p["uri"] for p in picked}) == 20
    assert len({p["category"] for p in picked}) == 5
    assert cm.ensure_diversity([], 5) == [] and cm.ensure_diversity(pool, 0) == []
    few = pool[:4]
    assert cm.ensure_diversity(few, 5) == few


def test_clustering_folds_near_duplicate_titles():
    cm = OptimizedContextManager(1000)
    dup = [_art(i, title="Nvidia buys a chip startup for two billion", category="Deals",
                similarity_score=0.5 + i * 0.1) for i in range(3)]
    words = ["apple orchard harvest", "quantum chip cooling", "lithium mine permit", "satellite launch delay",
             "hospital staffing audit", "wheat export tariff", "video codec patent", "ferry route closure",
             "museum funding cut"]
    others = [_art(10 + i, title=words[i], category=f"C{i}") for i in range(9)]
    reps = cm.cluster_similar_articles(dup + others, max_clusters=8)
    titles = [r["title"] for r in reps]
    assert titles.count("Nvidia buys a chip startup for two billion") == 1
    assert len(reps) == 8                                   # ten clusters, capped at eight
    best = [r for r in reps if r["title"].startswith("Nvidia")][0]
    assert best["similarity_score"] == pytest.approx(0.7)
    assert cm.cluster_similar_articles(others[:3], max_clusters=8) == others[:3]


def test_optimize_selection_respects_user_limit_and_token_budget():
    cm = OptimizedContextManager(128_000)
    pool = [_art(i) for i in range(200)]
    out = cm.optimize_article_selection(pool, "overview of funding", budget_tokens=50_000, user_limit=15)
    assert len(out) == 15 and all("uri" in a and "summary" in a for a in out)
    tight = cm.optimize_article_selection(pool, "overview", budget_tokens=300)
    assert 1 <= len(tight) <= 3
    assert cm.optimize_article_selection([], "x", 1000) == []


def test_format_optimized_context_groups_by_category_and_names_the_focus():
    cm = OptimizedContextManager(1000)
    arts = [cm.compress_article(_art(i)) for i in range(3)]
    ctx = cm.format_optimized_context(arts, "funding trends", "trend_analysis")
    assert "## Policy (1 articles)" in ctx and "## Funding (1 articles)" in ctx
    assert "URL: https://ex.org/Topic A/0" in ctx and "Tags: ai,soc" in ctx
    assert ctx.rstrip().endswith("emerging developments.")
    assert cm.format_optimized_context([], "q", "x") == "No articles available for analysis."
    assert "strategic insights" in cm.format_optimized_context(arts, "q", "other")


# ── QueryRouter ──────────────────────────────────────────────────────────────

@pytest.fixture
def router(svc):
    return svc.query_router


@pytest.mark.parametrize("q,kind", [
    ("what are the latest trends in SOC automation", "temporal_analysis"),
    ("tell me about OpenAI's strategy", "entity_focused"),
    ("articles mentioning Sundar Pichai", "entity_focused"),
    ("what is the impact of tariffs", "semantic_search"),
    ("sentiment analysis of Microsoft Corp coverage", "comprehensive"),  # analysis term suppresses entity
    ("vendors", "comprehensive"),
])
def test_router_classification(router, q, kind):
    assert router.classify_query(q) == kind


def test_time_period_and_subject_terms(router):
    assert router.extract_time_period("over the last 30 days") == 30
    assert router.extract_time_period("recent news") == 7
    assert router.has_explicit_time_period("last quarter") and not router.has_explicit_time_period("recent")
    assert router._subject_terms("what are the latest trends?") == []
    assert router._subject_terms("overview recent Wiley Glassdoor reviews") == ["wiley", "glassdoor", "reviews"]
    assert router._subject_terms("recent news from the last 30 days") == []


def test_topic_allocations_min_plus_proportional(router):
    alloc = router.calculate_topic_allocations({"A": 300, "B": 100}, 100)
    assert alloc["A"] == 10 + 60 and alloc["B"] == 10 + 20
    assert router.calculate_topic_allocations({"A": 1, "B": 1, "C": 1}, 12) == {"A": 4, "B": 4, "C": 4}
    assert router.calculate_topic_allocations({}, 50) == {}
    assert router.calculate_topic_allocations({"A": 0, "B": 0}, 100) == {"A": 10, "B": 10}


def test_topic_balanced_sampling_keeps_every_topic_and_sorts_by_date(router):
    arts = [_art(i, topic="A") for i in range(40)] + [_art(i, topic="B") for i in range(15)]
    out = router._sample_topic_balanced(arts, 20)
    assert len(out) == 20
    assert {a["topic"] for a in out} == {"A", "B"}
    assert [a["publication_date"] for a in out] == sorted((a["publication_date"] for a in out), reverse=True)
    assert router._sample_topic_balanced(arts[:3], 20) == arts[:3]


def test_simple_queries_skip_expansion(router):
    assert router._is_simple_query("Nvidia funding")
    assert router._is_simple_query("x" * 60)
    assert not router._is_simple_query("compare the funding of Nvidia and AMD between 2024 and 2026 please")


def test_named_brand_tokens_match_possessives_and_skip_generic_words(router):
    router.db.brands = ["Wiley", "Dropzone AI", "Cyber Security Labs", "Exa"]
    named = router._named_brand_tokens("Did Wiley's rating drop? What about dropzone and Exa?")
    assert ("Wiley", "wiley") in named and ("Dropzone AI", "dropzone") in named
    assert ("Exa", "exa") in named              # no 4-letter token: the whole name is the token
    assert router._named_brand_tokens("") == []
    assert ("Cyber Security Labs", "cyber") not in named


def test_named_brand_fallback_pulls_articles_by_name_when_the_search_missed_them(router):
    router.db.brands = ["Wiley"]
    router.db.by_name["wiley"] = [{"uri": "u-w", "title": "Wiley reports", "summary": "", "category": None,
                                  "sentiment": None, "publication_date": "2026-10-01", "news_source": None,
                                  "topic": "Wiley - Brand Watch"}]
    extra = router._named_brand_fallback("what about Wiley?", [_art(1, title="Elsevier only")], 20)
    assert [a["uri"] for a in extra] == ["u-w"]
    assert extra[0]["category"] == "Uncategorized" and extra[0]["similarity_score"] == 1.0
    # already surfaced: nothing added
    assert router._named_brand_fallback("what about Wiley?", [_art(1, title="Wiley reports")], 20) == []
    assert router._named_brand_fallback("no brands here", [], 20) == []


def test_scoping_drops_other_brands_and_tops_up_from_the_brand_topic(router, monkeypatch):
    router.db.brands = ["Wiley"]
    mixed = [_art(1, title="Wiley Glassdoor rating", topic="Topic A"),
             _art(2, title="Elsevier layoffs", topic="Topic A"),
             _art(3, title="Pearson results", topic="Topic A")]
    topped = [_art(9, topic="Wiley - Brand Watch", title="Wiley staff survey")]

    async def fake_topic_search(query, topic, limit):
        return {"articles": topped if topic == "Wiley - Brand Watch" else [], "topic": topic}
    monkeypatch.setattr(router, "_vector_search_topic", fake_topic_search)

    out = _run(router._scope_to_named_brands("did Wiley's rating drop?", {"articles": mixed, "search_method": "x"}, 10))
    uris = [a["uri"] for a in out["articles"]]
    assert uris == [mixed[0]["uri"], topped[0]["uri"]]
    assert out["search_method"] == "x+brand_scoped"
    assert out["metadata"]["brand_scoped"] == {"brands": ["Wiley"], "before": 3, "after": 2,
                                               "dropped": 2, "added_from_brand_topics": 1}


def test_scoping_leaves_results_alone_without_a_named_brand(router):
    res = {"articles": [_art(1)], "search_method": "x"}
    assert _run(router._scope_to_named_brands("anything", res, 10)) is res


def test_direct_vector_search_maps_hits_and_excludes_rejects(router, monkeypatch):
    seen = {}

    def fake_vs(query, top_k, metadata_filter):
        seen.update(query=query, top_k=top_k, filter=metadata_filter)
        return [_vector_hit(_art(1)), {"metadata": {}, "score": 0.1}, _vector_hit(_art(2))]
    monkeypatch.setattr(aus, "vector_search_articles", fake_vs)
    out = _run(router._direct_vector_search("funding", "Topic A", 5))
    assert out["search_method"] == "direct_vector"
    assert [a["uri"] for a in out["articles"]] == [_art(1)["uri"], _art(2)["uri"]]
    assert seen["filter"] == {"$and": [{"topic": "Topic A"}, {"ingest_status": {"$ne": "filtered_relevance"}}]}
    assert out["articles"][0]["topic"] == "Topic A"


def test_direct_vector_search_failure_is_an_empty_result_not_an_exception(router, monkeypatch):
    monkeypatch.setattr(aus, "vector_search_articles", lambda **k: (_ for _ in ()).throw(RuntimeError("pgvector down")))
    out = _run(router._direct_vector_search("q", "T", 5))
    assert out["articles"] == [] and "pgvector down" in out["error"]


def test_cross_topic_search_allocates_per_topic_and_dedups(router, monkeypatch):
    async def fake_topic_search(query, topic, limit):
        n = {"Topic A": 3, "Topic B": 2, "Wiley - Brand Watch": 1}[topic]
        arts = [_art(i, topic=topic) for i in range(n)]
        if topic == "Topic B":
            arts.append(dict(_art(0, topic="Topic A")))   # same uri as a Topic A hit
        return {"articles": arts, "topic": topic}
    monkeypatch.setattr(router, "_vector_search_topic", fake_topic_search)
    out = _run(router._cross_topic_semantic_search("what is new", 50))
    md = out["metadata"]
    assert md["topics_searched"] == 3 and md["total_found"] == 7 and md["unique_after_dedup"] == 6
    assert md["allocations"]["Topic A"] > md["allocations"]["Wiley - Brand Watch"] >= 10
    assert out["search_method"] == "cross_topic_parallel_vector"


def test_cross_topic_search_with_no_topics(router):
    router.db.facade.topic_counts = {}
    out = _run(router._cross_topic_semantic_search("q", 10))
    assert out["articles"] == [] and out["metadata"] == {"error": "No topics found"}


def test_smart_search_expands_complex_queries_and_merges(router, monkeypatch):
    monkeypatch.setattr(router, "_generate_search_queries", _async_const(["nvidia funding", "amd funding"]))
    calls = []

    async def fake_direct(query, topic, limit):
        calls.append((query, limit))
        return {"articles": [_art(1, similarity_score=0.5), _art(2, similarity_score=0.9)]}
    monkeypatch.setattr(router, "_direct_vector_search", fake_direct)
    q = "compare the funding of Nvidia and AMD between 2024 and 2026 in detail please"
    out = _run(router._smart_vector_search(q, "Topic A", 20))
    assert [c[0] for c in calls] == ["nvidia funding", "amd funding"] and calls[0][1] == 10
    assert out["search_method"] == "smart_vector_expanded"
    assert [a["uri"] for a in out["articles"]] == [_art(2)["uri"], _art(1)["uri"]]
    assert out["metadata"]["generated_queries"] == ["nvidia funding", "amd funding"]


def test_smart_search_goes_direct_for_short_queries(router, monkeypatch):
    monkeypatch.setattr(router, "_direct_vector_search", _async_const({"articles": [], "search_method": "direct_vector"}))
    monkeypatch.setattr(router, "_generate_search_queries", _async_const(["should not be called"]))
    assert _run(router._smart_vector_search("Nvidia funding", "T", 10))["search_method"] == "direct_vector"
    # citation_limit above limit widens the search
    seen = {}

    async def fake_direct(query, topic, limit):
        seen["limit"] = limit
        return {"articles": []}
    monkeypatch.setattr(router, "_direct_vector_search", fake_direct)
    _run(router._smart_vector_search("Nvidia", "T", 10, citation_limit=40))
    assert seen["limit"] == 40


def test_generate_search_queries_parses_a_json_array_and_falls_back(router, monkeypatch):
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel('Here you go: ["a b", "c d", "e"] thanks'))
    assert _run(router._generate_search_queries("long question", "Topic A")) == ["a b", "c d", "e"]
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("no json here"))
    assert _run(router._generate_search_queries("long question", "Topic A")) == ["long question"]
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel(lambda msgs: (_ for _ in ()).throw(RuntimeError("x"))))
    assert _run(router._generate_search_queries("q", None)) == ["q"]


def _async_const(value):
    async def f(*a, **k):
        return value
    return f


def test_temporal_fetch_with_a_subject_searches_it_newest_first(router, monkeypatch):
    found = [_art(1, publication_date="2026-09-01"), _art(2, publication_date="2026-10-05"),
             _art(3, publication_date="2026-07-01")]
    monkeypatch.setattr(router, "_smart_vector_search",
                        _async_const({"articles": found, "search_method": "direct_vector", "metadata": {}}))
    out = _run(router._temporal_fetch("recent Wiley Glassdoor reviews", "Topic A", 10))
    assert [a["publication_date"] for a in out["articles"]] == ["2026-10-05", "2026-09-01", "2026-07-01"]
    assert out["search_method"] == "direct_vector+recency"
    assert out["metadata"]["subject_terms"] == ["wiley", "glassdoor", "reviews"]
    assert out["metadata"]["days_back"] is None
    assert router.db.facade.calls == []     # no date-window fetch


def test_temporal_fetch_applies_an_explicit_window_as_a_cutoff(router, monkeypatch):
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    new = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    found = [_art(1, publication_date=old), _art(2, publication_date=new), _art(3, publication_date="")]
    monkeypatch.setattr(router, "_cross_topic_semantic_search",
                        _async_const({"articles": found, "search_method": "cross", "metadata": {}}))
    out = _run(router._temporal_fetch("Wiley reviews from the last 30 days", None, 10))
    assert {a["uri"] for a in out["articles"]} == {_art(2)["uri"], _art(3)["uri"]}
    assert out["metadata"]["days_back"] == 30 and out["metadata"]["topic"] == "All Topics"


def test_temporal_fetch_without_a_subject_uses_the_date_window(router):
    router.db.facade.recent = [_art(i, topic=t) for t in ("A", "B") for i in range(15)]
    out = _run(router._temporal_fetch("what are the latest trends?", None, 10))
    assert out["search_method"] == "temporal_sql_fetch"
    assert len(out["articles"]) == 10 and {a["topic"] for a in out["articles"]} == {"A", "B"}
    kind, topic, limit, start, end = router.db.facade.calls[-1]
    assert topic is None and limit == 40 and start < end
    assert out["metadata"] == {"query_type": "temporal_analysis", "days_back": 7, "topic": "All Topics",
                               "total_found": 30, "sampled": 10}


def test_temporal_fetch_falls_back_to_the_window_when_the_subject_finds_nothing(router, monkeypatch):
    monkeypatch.setattr(router, "_smart_vector_search", _async_const({"articles": []}))
    router.db.facade.recent = [_art(i, topic="Topic A") for i in range(3)]
    out = _run(router._temporal_fetch("recent Wiley reviews", "Topic A", 10))
    assert out["search_method"] == "temporal_sql_fetch" and len(out["articles"]) == 3
    router.db.facade.recent = []
    out = _run(router._temporal_fetch("recent Wiley reviews", "Topic A", 10))
    assert out["articles"] == [] and out["metadata"]["total_found"] == 0


def test_route_merges_named_brand_fallback_into_a_topic_scoped_search(router, monkeypatch):
    router.db.brands = ["Wiley"]
    router.db.by_name["wiley"] = [{"uri": "u-w", "title": "Wiley reports", "summary": "", "category": "C",
                                  "sentiment": "Neutral", "publication_date": "2026-10-01",
                                  "news_source": "s", "topic": "Wiley - Brand Watch"}]
    monkeypatch.setattr(router, "_smart_vector_search",
                        _async_const({"articles": [_art(1, title="Elsevier only")], "search_method": "direct_vector"}))
    out = _run(router.route("what about Wiley?", "Topic A", 10))
    assert [a["uri"] for a in out["articles"]][0] == "u-w"
    assert out["search_method"] == "direct_vector+named_brand_keyword"
    assert out["metadata"]["named_brand_articles"] == 1


def test_route_picks_the_branch_by_query_type(router, monkeypatch):
    seen = []

    def tag(name):
        async def f(*a, **k):
            seen.append(name)
            return {"articles": [], "search_method": name}
        return f
    monkeypatch.setattr(router, "_temporal_fetch", tag("temporal"))
    monkeypatch.setattr(router, "_cross_topic_semantic_search", tag("cross"))
    monkeypatch.setattr(router, "_smart_vector_search", tag("smart"))
    _run(router.route("latest trends", "Topic A", 10))
    _run(router.route("what is the impact of tariffs", None, 10))
    _run(router.route("what is the impact of tariffs", "Topic A", 10))
    _run(router.route("tell me about OpenAI Inc", "__all__", 10))
    assert seen == ["temporal", "cross", "smart", "smart"]


def test_route_never_breaks_on_a_fallback_error(router, monkeypatch):
    monkeypatch.setattr(router, "_smart_vector_search", _async_const({"articles": [_art(1)], "search_method": "s"}))
    monkeypatch.setattr(router, "_named_brand_fallback", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = _run(router.route("anything", "Topic A", 10))
    assert len(out["articles"]) == 1


# ── AuspexService helpers ────────────────────────────────────────────────────

def test_entity_names_are_extracted_from_natural_phrasing(svc):
    assert "Dropzone AI" in svc._extract_entity_names("summarize articles about Dropzone AI")
    assert "Neil Armstrong" in svc._extract_entity_names("articles mentioning Neil Armstrong")
    assert "J.R.R. Tolkien" in svc._extract_entity_names("references to J.R.R. Tolkien")
    assert svc._extract_entity_names("Research focus: AI. Please use your tools to find context from the topic") == []
    assert svc._extract_entity_names("what is happening") == []


def test_entity_content_filter_matches_with_and_without_suffix(svc):
    arts = [_art(1, title="Dropzone raises money", summary=""),
            _art(2, title="Nothing relevant", summary="plain"),
            _art(3, title="", summary="DropzoneAI launches")]
    kept = svc._filter_articles_by_entity_content(arts, ["Dropzone AI"])
    assert [a["uri"] for a in kept] == [arts[0]["uri"], arts[2]["uri"]]
    assert svc._filter_articles_by_entity_content(arts, []) is arts


def test_sql_entity_validation_counts_only_articles_that_name_the_entity(svc):
    svc.db.search_result = ([{"title": "Acme Security raises", "summary": ""}, {"title": "Other", "summary": "x"}], 2)
    assert svc._validate_entity_in_sql_database(["Acme Security"], "Topic A") == 1
    kw = svc.db.search_calls[-1]
    assert kw["keyword"] == "Acme Security" and kw["exclude_ingest_status"] == aus.REJECTED_INGEST_STATUSES
    assert svc._validate_entity_in_sql_database([], "T") == 0


def test_sql_entity_articles_are_reshaped_and_deduplicated(svc):
    rows = [{"uri": "u1", "title": "Acme Security raises", "summary": "", "tags": "a,b"},
            {"uri": "u1", "title": "Acme Security raises", "summary": ""},
            {"uri": "u2", "title": "Unrelated", "summary": ""}]
    svc.db.search_result = (rows, 3)
    out = svc._get_entity_articles_from_sql(["Acme Security"], "Topic A", 10)
    assert [a["uri"] for a in out] == ["u1"]
    assert out[0]["tags"] == ["a", "b"] and out[0]["similarity_score"] == 1.0 and out[0]["url"] == "u1"


def test_citation_limit_bounds(svc):
    assert svc.get_citation_limit(1000) == aus.DEFAULT_CITATION_LIMIT
    assert svc.get_citation_limit(10) == 10
    assert svc.get_citation_limit(1000, user_override=2) == aus.MIN_CITATION_LIMIT
    assert svc.get_citation_limit(1000, user_override=5000) == aus.MAX_CITATION_LIMIT
    assert svc.get_citation_limit(40, user_override=100) == 40


def test_should_use_tools_only_skips_pure_greetings(svc):
    for m in ("hello", "Thanks!", "ok", "see you", "Good morning."):
        assert not _run(svc._should_use_tools(m))
    for m in ("hello, what is new on Nvidia?", "Nvidia", "thanks for that, now compare vendors"):
        assert _run(svc._should_use_tools(m))


@pytest.mark.parametrize("msg,chart", [
    ("show sentiment over time", "sentiment_timeline"), ("article volume please", "volume"),
    ("top categories chart", "category_bar"), ("radar chart of signals", "radar"),
    ("give me a pie chart", "sentiment_donut"), ("create a chart", "sentiment_donut"),
    ("[include charts] what is new", "sentiment_donut"), ("no chart words here", None),
])
def test_chart_request_detection(svc, msg, chart):
    assert svc._detect_chart_request(msg) == chart


def test_tools_status_lines(svc):
    assert svc._format_tools_status(None).startswith("DISABLED")
    assert svc._format_tools_status({"a": False}) == "DISABLED - All tools are turned off"
    assert svc._format_tools_status({"a": True, "b": True}).startswith("FULLY ENABLED")
    assert svc._format_tools_status({"a": True, "b": False}) == "PARTIALLY ENABLED - You have access to these tools: a"
    assert svc._format_active_tools(None) == "None available"
    assert svc._format_active_tools({"a": False}) == "All disabled"
    assert svc._format_active_tools({"search_news": True, "custom": True}) == "Active: Real-time News, custom"


def test_select_diverse_articles_prefers_new_categories_and_sources(svc):
    pool = [_art(i, category="Same", news_source="same.org", similarity_score=0.1 * i) for i in range(8)]
    pool.append(_art(99, category="Rare", news_source="rare.org", similarity_score=0.95))
    out = svc._select_diverse_articles(pool, 5)
    assert len(out) == 5 and any(a["category"] == "Rare" for a in out)
    assert svc._select_diverse_articles(pool[:3], 5) == pool[:3]
    assert svc._select_diverse_articles_original(pool, 5) == out


def test_json_extraction_from_a_chatty_reply(svc):
    assert svc._extract_json_from_response_original('Sure! {{"queries": [1]}} done') == '{"queries": [1]}'
    assert svc._extract_json_from_response_original("no braces") == "no braces"


def test_search_strategy_from_message_and_options(svc):
    opts = FakeAnalyze.options
    trend = svc._determine_search_strategy("funding trends over time", opts)
    assert trend[0]["params"]["date_range"] == "90" and trend[0]["params"]["keyword"] is None
    cat = svc._determine_search_strategy("anything about funding", opts)
    assert cat[0]["params"]["category"] == ["Funding"]
    sent = svc._determine_search_strategy("negative coverage", opts)
    assert sent[0]["params"]["sentiment"] == "Negative"
    sig = svc._determine_search_strategy("any weak signal?", opts)
    assert sig[0]["params"]["future_signal"] == "Weak Signal"
    default = svc._determine_search_strategy("gizmos", opts)
    assert default == [{"description": "General keyword search",
                        "params": {"category": None, "keyword": "gizmos", "sentiment": None,
                                   "future_signal": None, "tags": None, "date_range": "30"}}]


def test_articles_summary_has_stats_details_and_tags(svc):
    arts = [_art(i, tags=["Nvidia", "SOC"] if i == 0 else "ai") for i in range(30)]
    s = svc._format_articles_summary(arts, "vector", detail_limit=10)
    assert "Total Articles: 30" in s and "Detailed Context Provided: 10 articles" in s
    assert "Unique Sources: 4" in s
    assert "Tags: Nvidia, SOC" in s and "... and 20 more articles available" in s
    assert "Similarity:" in s
    assert s.count("\n[") == 10
    assert svc._format_articles_summary([], "vector") == "No articles found via vector"
    small = svc._format_articles_summary(arts[:3], "sql", detail_limit=1)   # clamped up to the minimum
    assert "Detailed Context Provided: 3 articles" in small and "more articles" not in small


def test_plugin_result_formatting(svc):
    from app.services.tool_plugin_base import ToolResult
    r = ToolResult(success=True, message="ok", execution_time_ms=42, data={
        "summary": "S", "trends": [{"description": "up"}], "article_count": 7,
        "analysis": {"sentiment": {"trend_direction": "improving", "distribution": {"pos": 1}},
                     "categories": {"emerging": [{"category": "X", "growth": 50}]}},
        "chart_data": {"sentiment_timeline": {"layout": {"title": "Mood"}, "data": []}}})
    out = svc._format_plugin_result("trend", r)
    assert out.startswith("\n[TOOL: trend]") and "Status: ok" in out and "Summary:\nS" in out
    assert "- up" in out and "Sentiment: improving" in out and "X (+50%)" in out
    assert "Articles analyzed: 7" in out and "Execution time: 42ms" in out
    marker = out.split("<!-- CHART_DATA:")[1].split(":END_CHART -->")[0]
    assert json.loads(marker)["title"] == "Mood" and json.loads(marker)["format"] == "json"


def test_available_plugin_tools_listing(svc):
    tool = SimpleNamespace(name="trend", version="1", description="d", category="c",
                           parameters=[SimpleNamespace(name="p", type="str", required=False, default=None, description="x")])
    svc.tool_registry = FakeRegistry(tool=tool, handler=False)
    out = svc.get_available_plugin_tools()
    assert out == [{"name": "trend", "version": "1", "description": "d", "category": "c", "has_handler": False,
                    "parameters": [{"name": "p", "type": "str", "required": False, "default": None, "description": "x"}]}]


def test_check_plugin_tools_returns_a_final_response_with_charts(svc):
    from app.services.tool_plugin_base import ToolResult
    tool = SimpleNamespace(name="trend")
    result = ToolResult(success=True, data={"analysis": "A" * 300,
                                            "chart_data": {"volume": {"layout": {}, "data": [1]}}})
    svc.tool_registry = FakeRegistry(tool=tool, result=result)
    text, final = _run(svc._check_plugin_tools("show me trends over the last 30 days", "Topic A", chat_id=None))
    assert final and text.startswith("A" * 300)
    assert "<!-- CHART_DATA:" in text and json.loads(text.split("<!-- CHART_DATA:")[1].split(":END_CHART")[0])["title"] == "Volume"
    name, params, ctx_keys = svc.tool_registry.executed[0]
    assert name == "trend" and params == {"topic": "Topic A", "time_period": "30d"}
    assert ctx_keys == ["ai_model", "db", "profile_context", "topic", "vector_store"]


def test_check_plugin_tools_formats_context_when_not_final(svc):
    from app.services.tool_plugin_base import ToolResult
    svc.tool_registry = FakeRegistry(tool=SimpleNamespace(name="trend"),
                                     result=ToolResult(success=True, data={"summary": "short"}))
    text, final = _run(svc._check_plugin_tools("trends last week", "T"))
    assert not final and "[TOOL: trend]" in text and "Summary:\nshort" in text
    assert svc.tool_registry.executed[0][1]["time_period"] == "7d"


def test_check_plugin_tools_no_match_no_handler_or_failure(svc):
    from app.services.tool_plugin_base import ToolResult
    assert _run(svc._check_plugin_tools("anything", "T")) == (None, False)
    svc.tool_registry = FakeRegistry(tool=SimpleNamespace(name="t"), handler=False)
    assert _run(svc._check_plugin_tools("anything", "T")) == (None, False)
    svc.tool_registry = FakeRegistry(tool=SimpleNamespace(name="t"), result=ToolResult(success=False, error="boom"))
    assert _run(svc._check_plugin_tools("anything", "T")) == (None, False)


def test_followup_resolution(svc, monkeypatch):
    prior = [{"role": "user", "content": "did Wiley's Glassdoor rating drop?"},
             {"role": "assistant", "content": "<!-- ARTICLE_STATS:{}:END_STATS --> It fell to 3.2."}]
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel('"recent Wiley Glassdoor employee reviews"'))
    out = _run(svc._resolve_followup_query("overview recent reviews", prior))
    assert out == "recent Wiley Glassdoor employee reviews"
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("recent Wiley reviews\nsecond line ignored"))
    assert _run(svc._resolve_followup_query("overview recent reviews", prior)) == "recent Wiley reviews"

    assert _run(svc._resolve_followup_query("overview recent reviews", [])) == "overview recent reviews"
    assert _run(svc._resolve_followup_query("x" * 400, prior)) == "x" * 400
    assert _run(svc._resolve_followup_query("q", [{"role": "assistant", "content": "a"}])) == "q"
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("overview RECENT reviews"))
    assert _run(svc._resolve_followup_query("overview recent reviews", prior)) == "overview recent reviews"
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel(lambda msgs: (_ for _ in ()).throw(RuntimeError("x"))))
    assert _run(svc._resolve_followup_query("overview recent reviews", prior)) == "overview recent reviews"


def test_followup_prompt_carries_a_trimmed_transcript(svc, monkeypatch):
    model = FakeModel("Wiley reviews")
    monkeypatch.setattr(aus, "get_ai_model", lambda m: model)
    prior = [{"role": "user", "content": f"turn {i}"} if i % 2 == 0 else {"role": "assistant", "content": "a" * 1000}
             for i in range(10)]
    _run(svc._resolve_followup_query("more", prior))
    prompt = model.calls[0][1]["content"]
    assert "turn 0" not in prompt and "turn 4" in prompt            # last six turns only
    assert "a" * 600 in prompt and "a" * 601 not in prompt           # assistant text capped


def test_search_query_extraction_only_for_long_templates(svc, monkeypatch):
    seen = {}

    def fake_completion(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="  battery recycling costs  "))])
    monkeypatch.setattr(aus.litellm, "completion", fake_completion)
    short = "what about battery recycling?"
    assert _run(svc._extract_search_query(short)) == short
    long_plain = "battery " * 100
    assert _run(svc._extract_search_query(long_plain)) == long_plain and not seen
    template = "## Instructions\n### Format\n" + "please follow the template structure " * 30
    assert _run(svc._extract_search_query(template)) == "battery recycling costs"
    assert seen["temperature"] == 0.0 and seen["max_tokens"] == 100
    assert len(seen["messages"][0]["content"]) < 3600
    monkeypatch.setattr(aus.litellm, "completion", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert _run(svc._extract_search_query(template)) == template


def test_system_prompt_lookup_falls_back_to_the_built_in_default(svc):
    assert svc.get_system_prompt()["content"] == aus.DEFAULT_AUSPEX_PROMPT
    svc.db.create_auspex_prompt("mine", "Mine", "custom", is_default=True)
    assert svc.get_system_prompt()["content"] == "custom"
    assert svc.get_system_prompt("mine")["title"] == "Mine"
    assert svc.get_system_prompt("missing")["name"] == "default"


def test_prompt_crud_passes_through_and_errors_become_http_or_false(svc):
    assert svc.create_prompt("p", "T", "C", user_created="u") == 1
    assert svc.get_all_prompts()[0]["name"] == "p"
    assert svc.update_prompt("p", content="x") and not svc.update_prompt("nope")
    assert svc.delete_prompt("p") and not svc.delete_prompt("p")
    from fastapi import HTTPException
    svc.db.create_auspex_prompt = lambda **k: (_ for _ in ()).throw(RuntimeError("db"))
    with pytest.raises(HTTPException) as e:
        svc.create_prompt("p", "T", "C")
    assert e.value.status_code == 500


def test_ensure_default_prompt_creates_once(svc):
    svc._ensure_default_prompt()
    assert svc.db.prompts["default"]["content"] == aus.DEFAULT_AUSPEX_PROMPT
    svc.db.prompts["default"]["content"] = "edited"
    svc._ensure_default_prompt()
    assert svc.db.prompts["default"]["content"] == "edited"


def test_create_chat_session_handles_oauth_and_unknown_users(svc):
    cid = _run(svc.create_chat_session("Topic A", user_id="alice", profile_id=3))
    chat = svc.db.chats[cid]
    assert chat["user_id"] == "alice" and chat["title"] == "Chat about Topic A" and chat["profile_id"] == 3
    assert svc.db.messages[cid][0]["role"] == "system"
    assert svc.db.messages[cid][0]["metadata"] == {"prompt_name": "default"}

    cid = _run(svc.create_chat_session("Topic A", user_id={"email": "x@y.z"}, title="T"))
    assert svc.db.chats[cid]["user_id"] is None and svc.db.chats[cid]["metadata"]["oauth_user"] == "x@y.z"

    cid = _run(svc.create_chat_session("Topic A", user_id="stranger"))
    assert svc.db.chats[cid]["user_id"] is None and svc.db.chats[cid]["metadata"]["oauth_user"] == "stranger"

    from fastapi import HTTPException
    svc.db.create_auspex_chat = lambda **k: (_ for _ in ()).throw(RuntimeError("db"))
    with pytest.raises(HTTPException):
        _run(svc.create_chat_session("Topic A"))


def test_chat_session_reads_and_deletes_swallow_errors(svc):
    cid = svc.db.create_auspex_chat("Topic A", title="t")
    assert svc.get_chat_sessions(topic="Topic A")[0]["id"] == cid
    assert svc.get_chat_history(cid) == []
    assert svc.delete_chat_session(cid) and not svc.delete_chat_session(cid)
    svc.db.get_auspex_chats = lambda **k: (_ for _ in ()).throw(RuntimeError("x"))
    assert svc.get_chat_sessions() == []


def test_model_limits_are_capped_at_the_ceiling(svc):
    assert svc._get_model_context_limit("bedrock-kimi-k2-5") == AuspexService.CONTEXT_CEILING
    assert svc._get_model_output_limit("bedrock-kimi-k2-5") == 64000
    svc._update_context_manager_for_model("bedrock-kimi-k2-5")
    assert svc.context_manager.context_limit == AuspexService.CONTEXT_CEILING


# ── System prompt assembly ───────────────────────────────────────────────────

def _profile_row(**over):
    row = dict(id=1, name="Acme", industry="Widgets", organization_type="Manufacturer",
               key_concerns=json.dumps(["cost", "tariffs"]), strategic_priorities=None,
               risk_tolerance="Low", innovation_appetite="High", decision_making_style="Fast",
               stakeholder_focus=json.dumps(["customers"]), competitive_landscape=None,
               regulatory_environment=None)
    row.update(over)
    return row


def test_enhanced_prompt_without_a_chat_is_the_base_prompt(svc):
    p = svc.get_enhanced_system_prompt(999, query="latest news on Nvidia")
    assert p["name"] == "default" and "Response Format" in p["content"]
    assert "TOPIC-SPECIFIC CONTEXT" not in p["content"]


def test_enhanced_prompt_injects_topic_options_default_profile_and_tool_state(svc, monkeypatch):
    from app.database_query_facade import DatabaseQueryFacade
    monkeypatch.setattr(DatabaseQueryFacade, "get_default_organisational_profile", lambda self: _profile_row())
    cid = svc.db.create_auspex_chat("Topic A", title="t")
    p = svc.get_enhanced_system_prompt(cid, tools_config={"search_news": True, "x": False},
                                       include_charts=True, query="latest news on Nvidia")
    c = p["content"]
    assert p["name"] == "enhanced_topic_a"
    assert "perspective of Acme (Manufacturer in Widgets)" in c
    assert "Key Concerns: cost, tariffs" in c and "Strategic Priorities: Growth and sustainability" in c
    assert "TOPIC-SPECIFIC CONTEXT FOR TOPIC A:" in c
    assert "Policy, Funding, Research" in c
    assert "TOOLS STATUS: PARTIALLY ENABLED - You have access to these tools: search_news" in c
    assert "Tools: Active: Real-time News" in c
    assert "Charts: ENABLED" in c and "Profile: None" in c    # no profile on the chat itself
    assert c.index("perspective of Acme") < c.index("TOPIC-SPECIFIC CONTEXT")


def test_enhanced_prompt_uses_the_chats_own_profile_and_cross_topic_labels(svc, monkeypatch):
    from app.database_query_facade import DatabaseQueryFacade
    monkeypatch.setattr(DatabaseQueryFacade, "get_organisational_profile",
                        lambda self, pid: _profile_row(name=f"Profile {pid}"))
    cid = svc.db.create_auspex_chat("__all__", title="t", profile_id=7)
    p = svc.get_enhanced_system_prompt(cid, query="hello")
    assert "perspective of Profile 7" in p["content"]
    assert "TOPIC-SPECIFIC CONTEXT FOR ALL TOPICS:" in p["content"]
    assert "Profile: Profile 7" in p["content"] and "Cross-topic analysis" in p["content"]
    assert "Casual Conversation Style" in p["content"]     # casual intent uses the versatile prompt
    assert "Charts: Not enabled" in p["content"]


def test_enhanced_prompt_takes_jevs_depth_when_given(svc):
    cid = svc.db.create_auspex_chat("Topic A")
    p = svc.get_enhanced_system_prompt(cid, query="latest news on Nvidia", query_depth="deep")
    assert "DEEP ANALYSIS" in p["content"]


def test_enhanced_prompt_survives_a_topic_options_failure(svc, monkeypatch):
    class Broken(FakeAnalyze):
        def get_topic_options(self, topic=None):
            raise RuntimeError("db")
    monkeypatch.setattr(aus, "AnalyzeDB", Broken)
    cid = svc.db.create_auspex_chat("Topic A")
    p = svc.get_enhanced_system_prompt(cid, query="latest news on Nvidia")
    assert p["name"] == "default" and "TOPIC-SPECIFIC" not in p["content"]


# ── Model calls ──────────────────────────────────────────────────────────────

def test_streaming_response_sizes_max_tokens_and_skips_empty_chunks(svc, monkeypatch):
    calls = _stream(monkeypatch, "Hel", None, "lo")
    msgs = [{"role": "system", "content": "s" * 4000}, {"role": "user", "content": "q"}]
    out = _run(_collect(svc._generate_streaming_response(msgs, "bedrock-kimi-k2-5")))
    assert out == ["Hel", "lo"]
    kw = calls[0]
    assert kw["stream"] is True and kw["messages"] is msgs
    budget = kw.get("max_tokens", kw.get("max_completion_tokens"))   # reasoning models take the other name
    assert budget == min(64000, AuspexService.CONTEXT_CEILING - (4001 // 3) - 1000)


def test_streaming_response_turns_a_provider_error_into_text(svc, monkeypatch):
    async def boom(**kw):
        raise RuntimeError("rate limited")
    monkeypatch.setattr(aus.litellm, "acompletion", boom)
    out = _run(_collect(svc._generate_streaming_response([{"role": "user", "content": "q"}], "bedrock-kimi-k2-5")))
    assert out == ["Error generating response: rate limited"]


def _completion(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_structured_analysis_returns_bare_json_even_when_fenced(svc, monkeypatch):
    calls = []

    async def fake(**kw):
        calls.append(kw)
        return _completion('Here:\n```json\n{"a": 1, "b": [2]}\n```')
    monkeypatch.setattr(aus.litellm, "acompletion", fake)
    out = _run(svc.generate_structured_analysis("sys", "user", model="claude-sonnet-4-5", max_tokens=1234))
    assert json.loads(out) == {"a": 1, "b": [2]}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["messages"][0] == {"role": "system", "content": "sys"}


def test_structured_analysis_falls_back_without_json_mode(svc, monkeypatch):
    calls = []

    async def fake(**kw):
        calls.append(kw)
        if "response_format" in kw:
            raise RuntimeError("json mode unsupported")
        return _completion('{"ok": true}')
    monkeypatch.setattr(aus.litellm, "acompletion", fake)
    assert json.loads(_run(svc.generate_structured_analysis("s", "u", model="claude-sonnet-4-5"))) == {"ok": True}
    assert len(calls) == 2 and "response_format" not in calls[1]


def test_structured_analysis_rejects_non_json_and_empty_replies(svc, monkeypatch):
    from fastapi import HTTPException

    async def prose(**kw):
        return _completion("I cannot do that.")
    monkeypatch.setattr(aus.litellm, "acompletion", prose)
    with pytest.raises(HTTPException) as e:
        _run(svc.generate_structured_analysis("s", "u", model="claude-sonnet-4-5"))
    assert e.value.status_code == 500 and "invalid JSON" in e.value.detail

    async def empty(**kw):
        return SimpleNamespace(choices=[])
    monkeypatch.setattr(aus.litellm, "acompletion", empty)
    with pytest.raises(HTTPException) as e:
        _run(svc.generate_structured_analysis("s", "u", model="claude-sonnet-4-5"))
    assert e.value.detail == "No response from AI model"


def test_suggest_options_splits_the_list_and_fails_as_502(svc, monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message={"content": " Alpha, Beta\nGamma ,, "})])
    monkeypatch.setattr(aus.litellm, "completion", fake)
    assert svc.suggest_options("categorization", "Scenario", "desc") == ["Alpha", "Beta", "Gamma"]
    prompt = seen["messages"][0]["content"]
    assert "Scenario description: desc." in prompt and "type 'categorization'" in prompt
    from fastapi import HTTPException
    monkeypatch.setattr(aus.litellm, "completion",
                        lambda **k: SimpleNamespace(choices=[SimpleNamespace(message={"content": "  "})]))
    with pytest.raises(HTTPException) as e:
        svc.suggest_options("keywords", "S")
    assert e.value.status_code == 502


# ── The retrieval step behind a chat turn ────────────────────────────────────

def _vector(monkeypatch, hits):
    seen = []

    def fake_vs(query, top_k, metadata_filter):
        seen.append(dict(query=query, top_k=top_k, filter=metadata_filter))
        return hits
    monkeypatch.setattr(aus, "vector_search_articles", fake_vs)
    return seen


def test_rich_vector_results_become_an_optimised_context(svc, monkeypatch):
    seen = _vector(monkeypatch, [_vector_hit(_art(i)) for i in range(30)])
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("unused"))
    out = _run(svc._original_chat_database_logic("which vendors raised funding this year?", "Topic A", 12))
    assert out.startswith("## Search Method: Context-Optimized Semantic Search")
    assert "**Found**: 30 semantically relevant articles" in out
    assert "**Optimized to**: 12 diverse" in out
    assert len(svc._last_chat_articles) == 12
    assert seen[0]["filter"] == {"$and": [{"topic": "Topic A"}, {"ingest_status": {"$ne": "filtered_relevance"}}]}
    assert seen[0]["top_k"] == 12


def test_citation_limit_widens_the_vector_fetch(svc, monkeypatch):
    seen = _vector(monkeypatch, [_vector_hit(_art(i)) for i in range(30)])
    _run(svc._original_chat_database_logic("which vendors raised funding this year?", "Topic A", 12, citation_limit=100))
    assert seen[0]["top_k"] == 100


def test_explicit_date_words_become_a_vector_filter_and_a_fallback_cutoff(svc, monkeypatch):
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    new = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    hits = [_vector_hit(_art(i, publication_date=old if i < 5 else new)) for i in range(30)]
    seen = _vector(monkeypatch, hits)
    out = _run(svc._original_chat_database_logic("recycling costs in the last 30 days", "Topic A", 50))
    f = seen[0]["filter"]["$and"]
    assert f[0] == {"topic": "Topic A"} and "$gte" in f[1]["publication_date"]
    assert "**Found**: 25 semantically relevant articles" in out


def test_entity_query_with_no_matching_articles_says_so_after_checking_sql(svc, monkeypatch):
    _vector(monkeypatch, [_vector_hit(_art(i, title="Nothing about them")) for i in range(30)])
    svc.db.search_result = ([], 0)
    out = _run(svc._original_chat_database_logic("summarize articles about Acme Security", "Topic A", 10))
    assert out.startswith("## No Articles Found for Specific Entity")
    assert "Acme Security" in out and "Found 30 articles" in out
    assert "Acme Security" in {c["keyword"] for c in svc.db.search_calls}   # entity order is a set's


def test_entity_query_recovers_articles_from_sql_when_the_vector_store_lags(svc, monkeypatch):
    _vector(monkeypatch, [_vector_hit(_art(i, title="Nothing about them")) for i in range(30)])
    rows = [{"uri": f"u{i}", "title": f"Acme Security story {i}", "summary": "s", "tags": "",
             "category": "C", "sentiment": "Neutral", "news_source": "x"} for i in range(12)]
    svc.db.search_result = (rows, 12)
    out = _run(svc._original_chat_database_logic("summarize articles about Acme Security", "Topic A", 10))
    assert "Context-Optimized Semantic Search" in out
    assert "**Found**: 10 semantically relevant articles" in out      # capped at the limit


def test_thin_vector_results_fall_through_to_a_structured_sql_search(svc, monkeypatch):
    _vector(monkeypatch, [_vector_hit(_art(1))])
    strategy = {"queries": [{"description": "funding", "params": {"category": ["Funding"], "date_range": "30"}},
                            {"description": "kw", "params": {"keyword": "layoffs", "sentiment": "Negative",
                                                              "tags": "jobs", "date_range": "all"}}]}
    # Pretty-printed, as the planner prompt's example shows; compact JSON breaks the
    # extractor (see test_json_extractor_corrupts_compact_nested_objects).
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("```" + json.dumps(strategy, indent=2) + "```"))
    rows = [{"uri": f"u{i}", "title": f"Row {i}", "summary": "s", "tags": "", "category": "Funding",
             "sentiment": "Neutral", "publication_date": "2026-10-01"} for i in range(4)]
    svc.db.search_result = (rows, 4)
    out = _run(svc._original_chat_database_logic("funding and layoffs", "Topic A", 10))
    assert "## Search Method: Structured Keyword Search" in out
    assert "- Categories: Funding" in out and "- Keywords: layoffs" in out and "- Tags: jobs" in out
    assert "Found 8 total matching articles" in out and "Analyzing the 4 most recent articles" in out
    cat_call, kw_call = svc.db.search_calls[-2:]
    assert cat_call["category"] == ["Funding"] and cat_call["pub_date_start"] is not None
    assert kw_call["keyword"] == "layoffs" and kw_call["sentiment"] == ["Negative"] and kw_call["tags"] == ["jobs"]
    assert kw_call["pub_date_start"] is None
    assert "Title: Row 0" in out and "User Question: funding and layoffs" in out


def test_garbage_from_the_planner_means_a_basic_keyword_search(svc, monkeypatch):
    _vector(monkeypatch, [])
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("not json at all"))
    svc.db.search_result = ([{"uri": "u", "title": "T", "summary": "s", "tags": ""}], 1)
    out = _run(svc._original_chat_database_logic("gizmos", "Topic A", 10))
    assert "## Basic Search (Fallback)" in out and "Keyword search for: gizmos" in out
    assert svc.db.search_calls[-1]["keyword"] == "gizmos"


def test_empty_planner_strategy_means_a_fallback_keyword_search(svc, monkeypatch):
    _vector(monkeypatch, [])
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel('{"queries": []}'))
    svc.db.search_result = ([], 0)
    out = _run(svc._original_chat_database_logic("gizmos", "Topic A", 10))
    assert out.startswith('## No Articles Found for Query: "gizmos"')
    assert svc.db.search_calls[-1]["keyword"] == "gizmos"


def test_invalid_inputs_are_reported_not_raised(svc):
    assert _run(svc._original_chat_database_logic("", "Topic A", 10)).startswith("## Search Error")
    assert _run(svc._original_chat_database_logic("q", "Topic A", 0)).startswith("## Search Error")


def test_a_vector_store_failure_falls_back_to_sql(svc, monkeypatch):
    monkeypatch.setattr(aus, "vector_search_articles", lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(aus, "get_ai_model",
                        lambda m: FakeModel(json.dumps({"queries": [{"params": {"keyword": "x"}}]}, indent=2)))
    svc.db.search_result = ([{"uri": "u", "title": "T", "summary": "s", "tags": ""}], 1)
    out = _run(svc._original_chat_database_logic("x", "Topic A", 10))
    assert "Structured Keyword Search" in out


def test_temporal_queries_go_through_the_router(svc, monkeypatch):
    svc.db.facade.recent = [_art(i) for i in range(20)]
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("unused"))
    out = _run(svc._original_chat_database_logic("what are the latest trends?", "Topic A", 10))
    assert "Context-Optimized Semantic Search" in out
    assert svc.db.facade.calls and svc.db.facade.calls[-1][1] == "Topic A"


def test_use_mcp_tools_resolves_the_chat_topic(svc, monkeypatch):
    seen = {}

    async def fake_logic(message, topic, limit, citation_limit=None, sampling_strategy=None):
        seen.update(message=message, topic=topic, limit=limit)
        return "ctx"
    monkeypatch.setattr(svc, "_original_chat_database_logic", fake_logic)
    assert _run(svc._use_mcp_tools("q", 404, 10)) is None
    cid = svc.db.create_auspex_chat("__all__")
    assert _run(svc._use_mcp_tools("q", cid, 10)) == "ctx" and seen["topic"] is None
    cid = svc.db.create_auspex_chat("Topic A")
    _run(svc._use_mcp_tools("q", cid, 7))
    assert seen["topic"] == "Topic A" and seen["limit"] == 7


# ── A whole chat turn ────────────────────────────────────────────────────────

def _turn(svc, monkeypatch, message, *, hits=None, stream=("Answer ", "text"), **kw):
    _vector(monkeypatch, hits if hits is not None else [_vector_hit(_art(i)) for i in range(30)])
    monkeypatch.setattr(aus, "get_ai_model", lambda m: FakeModel("unused"))
    calls = _stream(monkeypatch, *stream)
    cid = kw.pop("chat_id", None) or svc.db.create_auspex_chat("Topic A", title="t")
    chunks = _run(_collect(svc.chat_with_tools(cid, message, **kw)))
    return cid, chunks, calls


def test_a_research_turn_hands_tools_context_before_the_users_message(svc, monkeypatch):
    cid, chunks, calls = _turn(svc, monkeypatch, "which vendors raised funding this year?")
    llm_messages = calls[0]["messages"]
    assert llm_messages[0]["role"] == "system" and "TOPIC-SPECIFIC CONTEXT FOR TOPIC A" in llm_messages[0]["content"]
    assert llm_messages[-1] == {"role": "user", "content": "which vendors raised funding this year?"}
    tools = [m for m in llm_messages if m["role"] == "assistant" and m["content"].startswith("[TOOLS]")]
    assert len(tools) == 1 and "Context-Optimized Semantic Search" in tools[0]["content"]
    assert llm_messages.index(tools[0]) == len(llm_messages) - 2

    assert chunks[0].startswith("<!-- ARTICLE_STATS:") and chunks[1:] == ["Answer ", "text"]
    stats = json.loads(chunks[0].split("<!-- ARTICLE_STATS:")[1].split(":END_STATS -->")[0])
    assert stats["total_articles"] == 30 or stats["total_articles"] > 0

    saved = svc.db.messages[cid]
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1]["content"] == chunks[0] + "Answer text"
    assert saved[1]["model_used"] == aus.DEFAULT_MODEL
    assert saved[1]["metadata"] == {"used_tools": True, "tools_config": None}


def test_a_pure_greeting_skips_retrieval(svc, monkeypatch):
    cid, chunks, calls = _turn(svc, monkeypatch, "hello", stream=("Hi!",))
    assert chunks == ["Hi!"]
    assert all(not m["content"].startswith("[TOOLS]") for m in calls[0]["messages"])
    assert "Casual Conversation Style" in calls[0]["messages"][0]["content"]
    assert svc.db.messages[cid][1]["metadata"]["used_tools"] is False


def test_tools_switched_off_means_no_retrieval_and_no_url_lookup(svc, monkeypatch):
    looked = []

    async def fake_lookup(urls, **kw):
        looked.append(urls)
        return "ctx"
    monkeypatch.setattr(aus, "lookup_urls_in_message", fake_lookup)
    msg = "analyse https://ex.org/a and https://ex.org/b"
    cid, chunks, calls = _turn(svc, monkeypatch, msg, tools_config={"search_articles": False})
    assert looked == []
    assert all(not m["content"].startswith("[TOOLS]") for m in calls[0]["messages"])
    assert "TOOLS STATUS: DISABLED - All tools are turned off" in calls[0]["messages"][0]["content"]


def test_a_url_question_gets_lookup_context_before_the_users_message(svc, monkeypatch):
    async def fake_lookup(urls, **kw):
        return f"looked up {urls[0]}"
    monkeypatch.setattr(aus, "lookup_urls_in_message", fake_lookup)
    cid, chunks, calls = _turn(svc, monkeypatch, "what does https://ex.org/story say?", hits=[])
    msgs = calls[0]["messages"]
    url_ctx = [m for m in msgs if "[URL LOOKUP RESULTS]" in m["content"]]
    assert len(url_ctx) == 1 and "looked up https://ex.org" in url_ctx[0]["content"]
    assert msgs.index(url_ctx[0]) < len(msgs) - 1 and msgs[-1]["role"] == "user"


def test_a_custom_prompt_replaces_the_system_prompt(svc, monkeypatch):
    cid, chunks, calls = _turn(svc, monkeypatch, "anything", custom_prompt="You are terse.", hits=[])
    assert calls[0]["messages"][0] == {"role": "system", "content": "You are terse."}


def test_a_profile_id_is_written_onto_the_chat(svc, monkeypatch):
    cid, *_ = _turn(svc, monkeypatch, "hello", profile_id=5, stream=("x",))
    assert svc.db.chats[cid]["profile_id"] == 5


def test_a_chart_request_yields_a_marker_from_the_same_articles(svc, monkeypatch):
    cid, chunks, calls = _turn(svc, monkeypatch, "show me a pie chart of sentiment on recycling")
    markers = [c for c in chunks if c.startswith("<!-- CHART_DATA:")]
    assert len(markers) == 1
    chart = json.loads(markers[0].split("<!-- CHART_DATA:")[1].split(":END_CHART -->")[0])
    assert chart["type"] == "sentiment_donut" and chart["n"] == len(svc._last_chat_articles) > 0
    assert chart["title"] == "Sentiment Distribution for Topic A"
    assert chunks.index(markers[0]) == 1          # stats first, then the chart, then the answer


def test_a_plugin_final_response_bypasses_the_model(svc, monkeypatch):
    from app.services.tool_plugin_base import ToolResult
    svc.tool_registry = FakeRegistry(tool=SimpleNamespace(name="trend"),
                                     result=ToolResult(success=True, data={"analysis": "P" * 300}))
    cid, chunks, calls = _turn(svc, monkeypatch, "trends over the last 30 days", hits=[])
    assert chunks == ["P" * 300] and calls == []
    assert svc.db.messages[cid][1]["content"] == "P" * 300


def test_plugin_context_rides_before_the_users_message_and_its_charts_are_yielded(svc, monkeypatch):
    from app.services.tool_plugin_base import ToolResult
    svc.tool_registry = FakeRegistry(tool=SimpleNamespace(name="trend"),
                                     result=ToolResult(success=True, data={"summary": "short",
                                                                           "chart_data": {"volume": {"layout": {}}}}))
    cid, chunks, calls = _turn(svc, monkeypatch, "trends over the last 30 days", hits=[])
    msgs = calls[0]["messages"]
    plugin = [m for m in msgs if "[TOOL: trend]" in m["content"]]
    assert len(plugin) == 1 and msgs.index(plugin[0]) < len(msgs) - 1
    assert any(c.startswith("<!-- CHART_DATA:") for c in chunks)


def test_an_error_inside_the_turn_is_reported_and_saved(svc, monkeypatch):
    svc.db.get_auspex_messages = lambda cid: (_ for _ in ()).throw(RuntimeError("db gone"))
    cid = svc.db.create_auspex_chat("Topic A")
    chunks = _run(_collect(svc.chat_with_tools(cid, "hello")))
    assert chunks == ["I apologize, but I encountered an error: db gone"]
    assert svc.db.messages[cid][-1]["metadata"]["error"] is True


def test_a_long_history_is_compacted_before_the_model_sees_it(svc, monkeypatch):
    cid = svc.db.create_auspex_chat("Topic A")
    for i in range(40):
        svc.db.add_auspex_message(cid, "user" if i % 2 == 0 else "assistant", f"turn {i} " + "x" * 6000)
    compacted = SimpleNamespace(messages=[{"role": "user", "content": "summary of the past"}],
                                metrics=SimpleNamespace(compaction_applied=True), summary_context="s")
    monkeypatch.setattr(aus, "compact_conversation", _async_const(compacted))
    monkeypatch.setattr(aus, "get_compaction_status", lambda m: {"applied": True})
    cid, chunks, calls = _turn(svc, monkeypatch, "hello", stream=("ok",), chat_id=cid)
    msgs = calls[0]["messages"]
    assert [m["content"] for m in msgs[1:]] == ["summary of the past", "hello"]
    assert svc.db.chats[cid]["metadata"]["last_compaction"] == {"applied": True}


# ── Defects found while writing these tests, fixed the same day ─────────────

def test_json_extractor_keeps_compact_nested_objects(svc):
    raw = '{"queries": [{"params": {"keyword": "x"}}]}'
    assert json.loads(svc._extract_json_from_response_original(raw)) == json.loads(raw)


def test_lower_case_phrases_are_not_entities(svc):
    assert svc._extract_entity_names("what about battery recycling costs") == []


def test_url_detector_keeps_the_path():
    from app.services.url_detector import detect_urls
    assert detect_urls("what does https://ex.org/world/story-123 say?") == ["https://ex.org/world/story-123"]
