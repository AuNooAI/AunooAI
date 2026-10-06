"""TheNewsAPI returns Japanese results whose page does not contain the search
term (111 of 181 rows on Sunstar's Japan topic, 5 Oct 2026). The guard keeps
the provider's match claim out of the feed unless the page carries the term."""
from app.tasks import keyword_monitor as km


# Real pair from the 5 October sweep: the provider matched this article for
# 歯周病 (periodontal disease); the page is about a student cycling to campus.
TERM = "歯周病 心疾患"
PHANTOM_TITLE = "20 minutes from home by bike: A female university student aspiring to be a nurse"
PHANTOM_SUMMARY = "She commutes from her parents' home and studies nursing."


class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


def test_tokens_of_a_two_word_japanese_term():
    assert km._term_tokens(TERM) == ["歯周病", "心疾患"]
    assert km._term_tokens('"花王 歯磨き"') == ["花王", "歯磨き"]


def test_phantom_row_is_missing_the_term_in_its_own_text():
    assert km._tokens_missing(f"{PHANTOM_TITLE} {PHANTOM_SUMMARY}", km._term_tokens(TERM)) == ["歯周病", "心疾患"]


def test_page_without_the_term_is_a_phantom(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(200, "<html><body><p>自転車で通学する看護学生</p></body></html>"))
    assert km._page_carries_tokens("https://news.example.jp/a", ["歯周病", "心疾患"]) is False


def test_page_with_the_term_is_kept(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(200, "<html><script>x</script><p>歯周病と心疾患の関係</p></html>"))
    assert km._page_carries_tokens("https://news.example.jp/b", ["歯周病", "心疾患"]) is True


def test_unreadable_page_is_not_evidence_either_way(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(404, ""))
    assert km._page_carries_tokens("https://news.example.jp/c", ["歯周病"]) is None

    def boom(*a, **k):
        raise OSError("timeout")
    monkeypatch.setattr(requests, "get", boom)
    assert km._page_carries_tokens("https://news.example.jp/d", ["歯周病"]) is None
