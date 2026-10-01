"""The registry proposal script (scripts/propose_tracking_params.py).

Only the pure grouping is tested: rows in, proposals out. The script's
database read is a separate function it never calls from ``propose``.
Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 30.
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "propose_tracking_params", os.path.join(ROOT, "scripts", "propose_tracking_params.py"))
ptp = importlib.util.module_from_spec(_spec)
sys.modules["propose_tracking_params"] = ptp
_spec.loader.exec_module(ptp)

SA = "https://seekingalpha.com/news/4647846-volkswagen-and-gotion-high-tech-to-invest-322b"
SM = "https://www.streamingmedia.com/Articles/News/Online-Video-News/x.aspx"
PUB = "2026-09-29T07:00:00+00:00"


def _row(uri, title, pub=PUB):
    return {"uri": uri, "title": title, "publication_date": pub}


def test_two_variants_with_the_same_title_are_proposed_with_evidence():
    rows = [
        _row(SA, "Volkswagen and Gotion to invest $3.22B"),
        _row(SA + "?mystery=news", "Volkswagen and Gotion to invest $3.22B", "2026-09-29T09:00:00+00:00"),
    ]
    out = ptp.propose(rows)
    assert "seekingalpha.com" in out
    entry = out["seekingalpha.com"]["mystery"]
    assert entry["count"] == 1 and entry["already_in_registry"] is False
    assert entry["examples"] == [[SA, SA + "?mystery=news"]]


def test_a_parameter_the_registry_already_strips_is_marked():
    rows = [_row(SA, "T"), _row(SA + "?feed_item_type=news", "T")]
    out = ptp.propose(rows)
    assert out["seekingalpha.com"]["feed_item_type"]["already_in_registry"] is True
    assert ptp.registry_snippet(out)["hosts"] == {}


def test_different_titles_are_not_evidence():
    rows = [
        _row(SM + "?ArticleID=1", "Streaming platform A launches"),
        _row(SM + "?ArticleID=2", "Streaming platform B shuts down"),
    ]
    assert ptp.propose(rows) == {}


def test_same_title_far_apart_in_time_is_not_evidence():
    rows = [
        _row("https://example.com/weekly?issue=1", "Weekly roundup", "2026-09-01T07:00:00+00:00"),
        _row("https://example.com/weekly?issue=2", "Weekly roundup", "2026-09-08T07:00:00+00:00"),
    ]
    assert ptp.propose(rows) == {}


def test_examples_are_capped_and_counts_accumulate():
    rows = [_row(f"https://host.example/p{i}", f"Title {i}") for i in range(5)]
    rows += [_row(f"https://host.example/p{i}?junk=x", f"Title {i}") for i in range(5)]
    out = ptp.propose(rows)
    entry = out["host.example"]["junk"]
    assert entry["count"] == 5 and len(entry["examples"]) == ptp.EXAMPLES_PER_PARAM


def test_registry_snippet_lists_new_parameters_per_host():
    rows = [
        _row("https://a.example/x", "T"), _row("https://a.example/x?src=rss", "T"),
        _row("https://b.example/y", "U"), _row("https://b.example/y?utm_source=rss", "U"),
    ]
    snippet = ptp.registry_snippet(ptp.propose(rows))
    assert snippet["hosts"] == {"a.example": ["src"]}
    assert snippet["version"].endswith("-proposed")


def test_host_and_path_normalisation():
    assert ptp._host_and_path("https://WWW.Example.com/a/b/?x=1") == ("example.com", "/a/b")
    assert ptp._host_and_path("not a url") is None
    assert ptp._param_names("https://e.com/p?A=1&b=2") == frozenset({"a", "b"})
