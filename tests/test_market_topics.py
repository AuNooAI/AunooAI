"""The arithmetic behind "Being discussed" and "Emerging".

Pure functions only: headline cleaning, parsing the model's subjects,
building the counts from members, and ranking. The gather and the model
call are exercised against the live tenant by hand (see docs/changes.md).
"""

from __future__ import annotations

from app.services import market_topics as mt


def _cluster(cid, n_recent, n_total, rise, name="Subject %d"):
    return {"id": cid, "name": (name % cid) if name and "%d" in name else name,
            "summary": "s", "n_recent": n_recent, "n_total": n_total,
            "n_prior": n_total - n_recent, "rise": rise,
            "top_vendors": [], "top_sources": [], "sample": [], "uris": []}


def test_clean_headline_strips_handle_and_vendor_prefixes():
    assert mt.clean_headline("@natalie-reed.bsky.social: 7AI just raised $130M") == "7AI just raised $130M"
    assert mt.clean_headline("Prophet Security: How to grade your AI SOC") == "How to grade your AI SOC"
    assert mt.clean_headline("something\n  odd  spacing") == "something odd spacing"
    assert mt.clean_headline(None) == ""


def test_rise_is_the_shrunk_recent_share_over_the_corpus_share():
    # Corpus share 0.2; a subject with 14 of 38 this week (0.37) reads 1.8x.
    share = 0.2
    rise = ((14 + mt.RISE_PRIOR * share) / (38 + mt.RISE_PRIOR)) / share
    assert 1.7 < rise < 1.9
    # Three of three is not 5x: the prior pulls a tiny subject back.
    small = ((3 + mt.RISE_PRIOR * share) / (3 + mt.RISE_PRIOR)) / share
    assert small < 3.5


def test_parse_subjects_validates_members_and_gives_a_headline_to_one_subject():
    raw = ('```json\n{"subjects": [{"name": "' + "x" * 80 + '", "summary": "' + "y" * 300 + '",'
           ' "members": [1, 2, 3, 999, "4", "junk"]},'
           ' {"name": "Overlap", "members": [3, 4, 5, 6]},'
           ' {"name": "Too small", "members": [7, 8]}, "junk"]}\n```')
    out = mt._parse_subjects(raw, 10)
    # "Overlap" keeps only 5 and 6 once 3 and 4 are taken, so it falls under
    # MIN_CLUSTER and is dropped, like "Too small".
    assert [s["name"][:5] for s in out] == ["xxxxx"]
    assert out[0]["members"] == [1, 2, 3, 4] and len(out[0]["name"]) == 60
    assert len(out[0]["summary"]) == 200
    out2 = mt._parse_subjects('{"subjects": [{"name": "A", "members": [1, 2, 3]},'
                              ' {"name": "B", "members": [3, 4, 5, 6]}]}', 10)
    assert [s["members"] for s in out2] == [[1, 2, 3], [4, 5, 6]]


def test_parse_subjects_accepts_a_bare_list():
    out = mt._parse_subjects('[{"name": "Bare", "members": [1, 2, 3]}]', 5)
    assert out and out[0]["name"] == "Bare"


def test_build_clusters_counts_recent_members_and_sorts_by_them():
    items = [{"uri": f"u{i}", "title": f"t{i}", "published": p, "news_source": "s",
              "vendors": [{"brand_id": 1, "vendor": "Acme"}] if i % 2 else []}
             for i, p in enumerate(["2026-09-06", "2026-09-05", "2026-08-10",
                                    "2026-08-11", "2026-08-12", "2026-09-04"])]
    result = {"items": items, "recent_since": "2026-09-01T00:00:00", "corpus_recent_share": 0.5}
    mt._build_clusters(result, [
        {"name": "Old", "summary": None, "members": [3, 4, 5]},
        {"name": "New", "summary": "s", "members": [1, 2, 6]},
    ])
    names = [c["name"] for c in result["clusters"]]
    assert names == ["New", "Old"]                      # most recent first
    new = result["clusters"][0]
    assert (new["n_recent"], new["n_total"], new["id"]) == (3, 3, 0)
    assert new["uris"] == ["u0", "u1", "u5"]           # members newest first
    assert new["top_vendors"] == [{"brand_id": 1, "vendor": "Acme", "n": 2}]
    assert result["assigned"] == 6 and result["k"] == 2


def test_rank_orders_discussed_by_recent_count_and_keeps_emerging_distinct():
    r = {"clusters": [
        _cluster(0, 18, 58, 1.04), _cluster(1, 18, 51, 1.18), _cluster(2, 12, 47, 0.86),
        _cluster(3, 11, 25, 1.44), _cluster(4, 9, 13, 2.15), _cluster(5, 8, 33, 0.82),
        _cluster(6, 5, 11, 1.44), _cluster(7, 2, 4, 1.45),
    ]}
    mt.rank(r)
    assert r["being_discussed"] == [0, 1, 2, 3, 4]
    # 7 has only two this week; 3 and 4 are already discussed, so 6 remains.
    assert r["emerging"] == [6]


def test_rank_leaves_emerging_empty_rather_than_repeating():
    r = {"clusters": [_cluster(0, 9, 13, 2.15), _cluster(1, 3, 20, 0.5)]}
    mt.rank(r)
    assert r["being_discussed"] == [0, 1]
    assert r["emerging"] == []


def test_rank_skips_unnamed_and_too_quiet_subjects():
    r = {"clusters": [_cluster(0, 9, 13, 2.15, name=None),
                      _cluster(2, 4, 13, 1.6, name="Real subject"),
                      _cluster(3, 2, 13, 1.9, name="Too few this week")]}
    mt.rank(r)
    assert r["being_discussed"] == [2]
    assert r["emerging"] == []


def test_listed_returns_clusters_in_stored_order():
    r = {"clusters": [_cluster(0, 1, 1, 1), _cluster(1, 1, 1, 1)],
         "being_discussed": [1, 0], "emerging": [0, 9]}
    out = mt.listed(r)
    assert [c["id"] for c in out["being_discussed"]] == [1, 0]
    assert [c["id"] for c in out["emerging"]] == [0]
    assert mt.listed(None) == {"being_discussed": [], "emerging": []}
