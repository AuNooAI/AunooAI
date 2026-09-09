"""English headlines for articles collected in other languages.

The analysis step already writes the summary in English whatever language the
article is in, but the headline stays as the collector delivered it, so a
Japanese or French story shows a foreign title over an English summary. This
module decides whether a title needs translating and asks a cheap model for
the English version. The original is kept alongside on the article as
``original_title``.

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

_DIACRITIC_RE = re.compile(r"[àâäáãåæçèéêëìíîïñòóôöõøùúûüýÿßœÀÂÄÁÃÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÖÕØÙÚÛÜÝŒ]")

_WORD_RE = re.compile(r"[A-Za-z']+")
_model = None


def _default_model():
    global _model
    if _model is None:
        from app.ai_models import AIModelFactory
        _model = AIModelFactory.get_model(TRANSLATION_MODEL)
    return _model


def _has_non_latin_script(text: str) -> bool:
    for ch in text:
        if ch.isspace() or not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if not (name.startswith("LATIN") or name.startswith("DIGIT")):
            return True
    return False


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


def _clean_model_title(text: str) -> str:
    text = (text or "").strip()
    # First non-empty line only; models sometimes add a note on a second line.
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    text = re.sub(r"^(english( title| headline)?|translation|title)\s*:\s*", "", text, flags=re.I)
    text = text.strip().strip('"').strip("'").strip("“”‘’").strip()
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
    return english


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
