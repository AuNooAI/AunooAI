"""The citation guard on analysis pieces: what it reads, what it stores,
and what stops an approval. The model call is mocked; the live check
ran against piece 18 on 6 Sep 2026 (docs/changes.md)."""

from __future__ import annotations

import json

from app.services import piece_citations as pc


class _Conn:
    """A connection that knows two articles."""
    def __init__(self):
        self.rows = {"https://a/1": ("Launch story", "CrowdStrike announced multi-agent investigations."),
                     "https://a/2": ("Evaluation guide", "Eight criteria for judging AI SOC platforms.")}
    def execute(self, stmt, params=None):
        uri = (params or {}).get("u")
        row = self.rows.get(uri)
        class _R:
            def __init__(self, r): self._r = r
            def mappings(self): return self
            def first(self): return {"title": self._r[0], "summary": self._r[1]} if self._r else None
        return _R(row)


def _row(body, index):
    return {"id": 18, "report_content": body, "facts": {"citation_index": index}}


def test_missing_index_entry_is_a_blocking_finding_without_a_model(monkeypatch):
    calls = []
    monkeypatch.setattr("litellm.completion", lambda **kw: calls.append(kw) or (_ for _ in ()).throw(AssertionError))
    findings = pc.check(_Conn(), _row("A claim [C9].", {}))
    assert findings == [{"check": "citation", "id": "C9", "severity": "no",
                         "detail": "C9: no source in the citation index"}]
    assert not calls


def test_verdicts_become_findings_and_only_no_blocks(monkeypatch):
    class _Msg:  content = json.dumps({"citations": [
        {"id": "C1", "supports": "partly", "why": "The launch story gives no reason about triage."},
        {"id": "C2", "supports": "no", "why": "It is about Astra, not an evaluation guide."}]})
    class _Choice: message = _Msg()
    class _Resp: choices = [_Choice()]
    monkeypatch.setattr("litellm.completion", lambda **kw: _Resp())
    monkeypatch.setattr("app.ai_models.resolve_litellm_call_params", lambda m: {"model": m})
    body = "CrowdStrike's launch [C1] gives the reason. Prophet published a guide [C2]."
    index = {"C1": {"uri": "https://a/1", "title": "Launch story"},
             "C2": {"uri": "https://a/2", "title": "Evaluation guide"}}
    findings = pc.check(_Conn(), _row(body, index))
    assert [f["severity"] for f in findings] == ["partly", "no"]
    assert "only partly supports" in findings[0]["detail"] and "does not support" in findings[1]["detail"]
    assert [b["id"] for b in pc.blocking(findings)] == ["C2"]


def test_merge_lint_replaces_only_citation_entries():
    existing = [{"check": "slop", "detail": "x"}, {"check": "citation", "id": "C1", "severity": "no", "detail": "old"}]
    out = pc.merge_lint(json.dumps(existing), [{"check": "citation", "id": "C3", "severity": "partly", "detail": "new"}])
    assert [l["check"] for l in out] == ["slop", "citation"] and out[1]["id"] == "C3"
    assert pc.blocking(out) == []
