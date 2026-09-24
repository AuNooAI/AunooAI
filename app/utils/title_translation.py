"""English headlines and text for articles collected in other languages.

The analysis step writes the summary in English whatever language the article
is in, but only for news that passes the relevance gate. Everything else keeps
the text the collector delivered: social posts (whose "summary" is the post
itself), and news the gate rejected. On a Japanese customer site that is most
of the feed. This module decides whether a title or a piece of text needs
translating and asks a cheap model for the English version. The original is
kept alongside on the article as ``original_title`` / ``original_summary``.

Detection is deliberately cheap and offline:

* any character outside the Latin script (CJK, kana, Hangul, Cyrillic, Arabic,
  Hebrew, Thai, Greek, Devanagari, ...) means "not English";
* accented Latin letters (ä, é, ç, ...) mean "probably not English";
* a plain Latin-script title is treated as English when it contains at least
  one English function word that is not also a common word in German, French,
  Spanish, Italian or Dutch, so no model call is made for the bulk of English
  news;
* everything else (French, German, Spanish, Italian, ... and short English
  titles with no function word) goes to the model, which returns the title
  unchanged when it is already English.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

TRANSLATION_MODEL = "nova-lite"

_ENGLISH_STOPWORDS = frozenset(
    # Function words that do not double as common words in German, French,
    # Spanish, Italian or Dutch. "an", "in", "on", "is", "was", "die", "man",
    # "will" and the like are left out on purpose: a German headline such as
    # "Anbieter kündigt neue Plattform an" would otherwise pass as English.
    "the and of to for with by from as are were this that these those its into "
    "over after before how what why who when would could should can may new "
    "says said about against amid between among have than then their there "
    "they you your our we us up out more most".split()
)

# Includes the Turkish letters (ğ ı ş İ Ğ Ş): a SOCNova post announcing PARS
# in Turkish passed as English and was never translated (Sep 2026).
_DIACRITIC_RE = re.compile(r"[àâäáãåæçèéêëìíîïñòóôöõøùúûüýÿßœğışÀÂÄÁÃÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÖÕØÙÚÛÜÝŒĞİŞ]")

# Function words of the languages we actually collect in Latin script. Used
# only for post/summary text: a Latin-script text with none of these and no
# English function word either (hashtags, a product name, "lol") is treated
# as English rather than sent to the model, because on a social-heavy site
# that call would run for thousands of English posts a day.
_FOREIGN_STOPWORDS = frozenset(
    # Words that are also ordinary English ("do", "per", "con", "van", "met",
    # "plus", "com", "os", "um") are left out on purpose.
    # German
    "der die das und ist nicht ein eine einen einem einer auf des den sich "
    "auch zu von im bei wird sind wir ich noch aber oder nur schon wenn "
    # French
    "de le la les une pas pour dans que qui sur au aux du ce cette ces mais avec en "
    "nous vous ils elle sont "
    # Spanish
    "el los las es por para del se lo como pero sus este esta muy "
    # Italian
    "il gli di che della delle nel nella sono anche "
    # Dutch
    "het een niet voor zijn dat ook naar bij nog wel je "
    # Portuguese
    "uma dos das mais".split()
)
_FOREIGN_STOPWORDS -= _ENGLISH_STOPWORDS

TEXT_TRANSLATE_LIMIT = 3000   # characters sent to the model per text
SOCIAL_TITLE_LIMIT = 120      # xpoz derives a post's title from body[:120]

_WORD_RE = re.compile(r"[A-Za-z']+")
_model = None


def _default_model():
    global _model
    if _model is None:
        from app.ai_models import AIModelFactory
        _model = AIModelFactory.get_model(TRANSLATION_MODEL)
    return _model


NON_LATIN_SHARE = 0.15   # share of letters outside Latin script that means "not English"


def _non_latin_share(text: str) -> float:
    """Share of the letters in ``text`` that are not Latin script.

    A share, not a single-character test, so an English abstract with a Greek
    letter or a "≥" is not sent for translation, while a Japanese post with a
    brand name and a URL in it still is.
    """
    latin = other = 0
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if name.startswith("LATIN"):
            latin += 1
        else:
            other += 1
    total = latin + other
    return other / total if total else 0.0


def _has_non_latin_script(text: str) -> bool:
    return _non_latin_share(text) > NON_LATIN_SHARE


def looks_english(title: str) -> bool:
    """True when the title is clearly English and no model call is needed."""
    if not title or not title.strip():
        return True
    if _has_non_latin_script(title):
        return False
    if _DIACRITIC_RE.search(title):
        # Accented Latin letters: almost always another language. A name like
        # "Zürich" in an English title only costs one model call, which
        # returns the title unchanged.
        return False
    words = [w.lower() for w in _WORD_RE.findall(title)]
    if not words:
        return True
    return any(w in _ENGLISH_STOPWORDS for w in words)


def looks_english_text(text: str) -> bool:
    """Cheaper judgement for post bodies and summaries.

    Same script rule as :func:`looks_english`, then English function words are
    weighed against German/French/Spanish/Italian/Dutch/Portuguese ones. A
    text with more English than foreign function words is English even when
    it carries an accented name; one with more foreign words, or accents and
    no English words, is not. A text with neither (hashtags, a product name,
    "lol") is treated as English rather than sent to the model, because on a
    social-heavy site that call would run for thousands of English posts a day.
    """
    if not text or not text.strip():
        return True
    if _has_non_latin_script(text):
        return False
    words = [w.lower() for w in _WORD_RE.findall(text)]
    english = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
    foreign = sum(1 for w in words if w in _FOREIGN_STOPWORDS)
    if english > foreign:
        return True
    if foreign > english:
        return False
    return not _DIACRITIC_RE.search(text)


def _clean_model_title(text: str) -> str:
    text = (text or "").strip()
    # First non-empty line only; models sometimes add a note on a second line.
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    text = re.sub(r"^(english( title| headline)?|translation|title)\s*:\s*", "", text, flags=re.I)
    return _strip_wrapping_quotes(text)


def _strip_wrapping_quotes(text: str) -> str:
    """Remove quotes the model wrapped the whole reply in, never a leading one alone.

    Also drops lone surrogate code points: a JSON reply cut inside an emoji
    escape decodes to one, and PostgreSQL rejects the string.
    """
    text = "".join(ch for ch in text if not 0xD800 <= ord(ch) <= 0xDFFF).strip()
    pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"))
    for open_q, close_q in pairs:
        if len(text) > 1 and text.startswith(open_q) and text.endswith(close_q):
            inner = text[1:-1]
            if open_q not in inner and close_q not in inner:
                return inner.strip()
    return text


def translate_title(title: str, ai_model=None) -> Optional[str]:
    """Return the English headline for ``title``, or None when it cannot be had.

    ``ai_model`` is any object with ``generate_response(messages)``; when it is
    None the cheap default model is loaded by name.
    """
    if not title or not title.strip():
        return None
    try:
        if ai_model is None:
            ai_model = _default_model()
        messages = [
            {"role": "system", "content": (
                "You translate news headlines into English. Reply with the English headline only, "
                "no quotes, no explanation. Keep names, brands and numbers as they are. "
                "If the headline is already in English, reply with it exactly as given."
            )},
            {"role": "user", "content": title.strip()},
        ]
        raw = ai_model.generate_response(messages)
        english = _clean_model_title(raw if isinstance(raw, str) else str(raw or ""))
    except Exception as e:  # never let a headline translation break ingest
        logger.warning(f"Title translation failed for {title[:60]!r}: {e}")
        return None
    if not english or len(english) > max(300, 4 * len(title)):
        return None
    if _non_latin_share(english) > 0.5:
        return None
    return english


def translate_text(text: str, ai_model=None) -> Optional[str]:
    """Return the English version of a post or summary, or None.

    Only the first ``TEXT_TRANSLATE_LIMIT`` characters are translated; a
    longer text gets an ellipsis so the cut is visible. The original is kept
    in full by the caller.
    """
    if not text or not text.strip():
        return None
    src = text.strip()
    cut = len(src) > TEXT_TRANSLATE_LIMIT
    if cut:
        src = src[:TEXT_TRANSLATE_LIMIT]
    try:
        if ai_model is None:
            ai_model = _default_model()
        messages = [
            {"role": "system", "content": (
                "You translate social media posts and news text into English. Reply with the "
                "English text only, no quotes, no notes. Keep @handles, #hashtags, URLs, names, "
                "brands and numbers exactly as they are. If the text is already in English, "
                "reply with it exactly as given."
            )},
            {"role": "user", "content": src},
        ]
        raw = ai_model.generate_response(messages)
        english = (raw if isinstance(raw, str) else str(raw or "")).strip()
        english = re.sub(r"^(english( text| translation)?|translation)\s*:\s*", "", english, flags=re.I)
        english = _strip_wrapping_quotes(english)
    except Exception as e:  # never let a translation break ingest
        logger.warning(f"Text translation failed for {text[:60]!r}: {e}")
        return None
    if not english or len(english) > max(1500, 4 * len(src)):
        return None
    if _non_latin_share(english) > 0.5:
        # Not a translation: the small model sometimes answers a Japanese
        # post with Japanese-looking nonsense (33 of 3,682 on sunstar).
        return None
    return english + (" …" if cut else "")


def _headline_from_text(text: str, limit: int) -> str:
    """The first ``limit`` characters of ``text``, cut on a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    if " " in head[limit // 2:]:
        head = head[:head.rfind(" ")]
    return head


def same_headline(a: str, b: str) -> bool:
    """True when two headlines differ only in case, spacing or punctuation."""
    norm = lambda t: re.sub(r"[^0-9a-z\u00c0-\uffff]+", "", (t or "").lower())
    return norm(a) == norm(b)


def english_title(title: str, ai_model=None) -> Tuple[str, Optional[str]]:
    """Return ``(title_to_show, original_or_None)``.

    ``original`` is None when the title was already English or the translation
    failed, so callers can write ``original_title`` only when it means something.
    """
    if looks_english(title):
        return title, None
    english = translate_title(title, ai_model)
    if not english or same_headline(english, title):
        return title, None
    return english, title


def english_fields(article: dict, ai_model=None) -> bool:
    """Translate a collected article's title and summary in place.

    Meant for the first insert of a collected row, before any analysis. Sets
    ``original_title`` / ``original_summary`` next to the translated fields,
    only for the fields that were actually translated, and returns True when
    anything changed. A social post's title is the head of its body, so the
    title is derived from the translated body rather than translated twice.
    """
    title = (article.get("title") or "").strip()
    summary = (article.get("summary") or "").strip()
    changed = False

    english_summary = None
    if summary and not looks_english_text(summary):
        english_summary = translate_text(summary, ai_model)
        if english_summary and not same_headline(english_summary, summary):
            article["summary"] = english_summary
            article["original_summary"] = summary
            changed = True
        else:
            english_summary = None

    if not title:
        return changed
    # Bluesky titles are "@handle: body"; xpoz titles are the body's first
    # 120 characters. Either way the title is the body, so it takes the body's
    # translation rather than a second model call.
    prefix, head = "", title
    m = re.match(r"^(@\S+:\s*)(.*)$", title, flags=re.S)
    if m and summary.startswith(m.group(2).rstrip(" ….")):
        prefix, head = m.group(1), m.group(2)
    if english_summary and summary.startswith(head.rstrip(" ….")):
        shown = english_summary if same_headline(head, summary) else \
            _headline_from_text(english_summary, max(SOCIAL_TITLE_LIMIT, len(head)))
        article["title"] = prefix + shown
        article["original_title"] = title
        return True
    if summary and not english_summary and looks_english_text(summary) \
            and not _has_non_latin_script(title):
        # An English body has an English title. Without this, a Reddit title
        # with no function word ("BV Questions") goes to the model, which
        # "tidies" it and the tidy-up is stored as a translation. A title in
        # another script over an English body is still translated.
        return changed
    shown, original = english_title(title, ai_model)
    if original:
        article["title"] = shown
        article["original_title"] = original
        changed = True
    return changed
