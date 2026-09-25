"""Swiss election disinformation monitor: service layer.

One structured extraction per approved article of the topic, narratives
matched across languages by embedding, outlets as actors with a tier, and
the queries behind every panel. Design: docs/SWISS_ELECTION_DISINFO_MONITOR_SPEC.md.

All DB access goes through SQLAlchemy connections from
Database._temp_get_connection() with named parameters, the same way the
module monitors do. Callers in async routes wrap the sync methods in
asyncio.to_thread so a slow query does not stall the event loop.
"""
import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)

DEFAULT_TOPIC = "Swiss Federal Elections 2027 Disinfo Monitoring"
EUROPE_TOPIC = "European Election Interference"
DEFAULT_MODEL = "bedrock-kimi-k2-5"
BRIEF_MODEL = "gpt-5.4"
NARRATIVE_MATCH_THRESHOLD = 0.90  # shortlist floor only; the model decides

STANCES = ("promotes", "reports", "debunks")
ATTRIBUTIONS = ("russia", "china", "other_state", "domestic", "unattributed")
TECHNIQUES = (
    "deepfake", "synthetic_text", "bot_amplification", "fake_account",
    "forged_document", "doctored_quote", "decontextualised_media",
    "astroturfing", "state_media_placement", "none_reported",
)
TIERS = ("state_media", "alt_media", "mainstream", "party", "fact_checker",
         "institution", "research", "social", "unknown")
# A social post reaches the extraction only above this alignment. The three days
# social ran in September produced hits at 0.70-1.00 and junk at 0.00-0.30
# (single-word matches), so the line sits between them.
SOCIAL_MIN_ALIGNMENT = 0.5
LANGUAGES = ("de", "fr", "it", "en")

# Federal vote calendar. Election day is the fixed one; vote Sundays are the
# Federal Council's published dates. Seeded as timeline mementos, scope topic.
CALENDAR = [
    (date(2026, 9, 27), "Federal votes 27 September 2026 (incl. neutrality initiative)"),
    (date(2026, 11, 29), "Federal votes 29 November 2026"),
    (date(2027, 3, 7), "Federal votes 7 March 2027"),
    (date(2027, 6, 13), "Federal votes 13 June 2027"),
    (date(2027, 9, 26), "Federal votes 26 September 2027"),
    (date(2027, 10, 24), "Federal Elections 24 October 2027"),
]

# Each scope is one watch: its own articles, narratives, prompt framing and
# calendar. They share the tables (topic column) and every panel.
SCOPES: Dict[str, Dict[str, Any]] = {
    DEFAULT_TOPIC: {
        "label": "Swiss Election Watch",
        "blurb": "Disinformation and influence operations aimed at Swiss voters, "
                 "Federal Elections 2027 and the votes before them.",
        "subject": "Swiss voters, in the run-up to the Federal Elections of October 2027 "
                   "and the federal votes before them",
        "angle_rule": "The article must concern Switzerland: Swiss politics, voters, votes, "
                      "parties, institutions or media. A piece about another country's election, "
                      "or about Ukraine, with no Swiss angle is on_topic false whatever the source.",
        "calendar": CALENDAR,
    },
    EUROPE_TOPIC: {
        "label": "European Interference Watch",
        "blurb": "Foreign and domestic interference in European elections and referendums, "
                 "read as the playbook that gets aimed at Switzerland next.",
        "subject": "voters in European countries, at any election or referendum",
        "angle_rule": "The article must describe interference, manipulation or an information "
                      "operation touching an election, referendum or political process in Europe "
                      "(the EU, the UK, Switzerland, the Western Balkans, Moldova, Ukraine, "
                      "Georgia or Armenia). Organisational housekeeping from a research body — "
                      "job adverts, merchandise, newsletters about itself — is on_topic false. "
                      "So is reporting with no election or political-process angle.",
        "calendar": [],
    },
}


def scope(topic: str) -> Dict[str, Any]:
    return SCOPES.get(topic, SCOPES[DEFAULT_TOPIC])

# The ten techniques, the five target types and the source tiers were passed to
# the model as bare enum values, so it was labelling them from the words alone
# and the board offered the reader no way to check what a label meant. The same
# text now goes into the prompt as the test to apply AND onto the screen as the
# legend, so what is displayed is what was asked for.
TECHNIQUE_GLOSSARY: List[Dict[str, str]] = [
    {"key": "deepfake", "label": "Synthetic or manipulated media",
     "attack": "Video, audio or still images generated or altered by machine and presented as real — a politician made to say something they did not, or an AI-made campaign picture of a scene that never happened.",
     "criteria": "The article says the media was machine-generated or manipulated. AI-made campaign imagery counts. A real photograph used to describe the wrong event is decontextualised media instead."},
    {"key": "synthetic_text", "label": "Synthetic text",
     "attack": "Machine-written articles, posts or comments passed off as written by people, often filling whole sites.",
     "criteria": "The article reports AI-generated text used to produce or pad content, not merely that AI exists as a worry."},
    {"key": "bot_amplification", "label": "Bot amplification",
     "attack": "Automated accounts inflating how far a message travels.",
     "criteria": "The article reports automated or scripted accounts driving shares, likes, replies or trending position. Volume alone is not enough."},
    {"key": "fake_account", "label": "Fake account",
     "attack": "Accounts impersonating a real person or organisation, or invented personas presented as ordinary citizens.",
     "criteria": "The article says accounts posed as someone they are not. Use bot amplification instead when the point is automation rather than false identity."},
    {"key": "forged_document", "label": "Forged document",
     "attack": "A fabricated document circulated as genuine: a leaked memo, an official letter, a ballot paper, a court filing.",
     "criteria": "The article says the document itself was faked or altered. A document whose contents are merely disputed does not count."},
    {"key": "doctored_quote", "label": "Doctored quote",
     "attack": "Words invented for a real person, or edited so they mean something else.",
     "criteria": "The article says a quotation was fabricated or altered. If the words are real and only the setting is missing, use decontextualised media."},
    {"key": "decontextualised_media", "label": "Decontextualised media",
     "attack": "Real images, video or figures re-used to describe an event they have nothing to do with.",
     "criteria": "The material is genuine and the claim about when, where or what it shows is false."},
    {"key": "astroturfing", "label": "Astroturfing",
     "attack": "A campaign staged to look like a spontaneous citizens' movement.",
     "criteria": "The article reports organised money or coordination behind something presented as grassroots: a committee, a petition, a protest, a wave of letters."},
    {"key": "state_media_placement", "label": "State media placement",
     "attack": "A state-owned or state-directed outlet carrying or seeding the claim into another country's debate.",
     "criteria": "A state outlet is named as the vehicle. This holds whether or not the claim is false, because the placement is the operation."},
    {"key": "none_reported", "label": "None reported",
     "attack": "The article describes no technique.",
     "criteria": "The default. It records that the article named no method, not that no method was used."},
]

TARGET_GLOSSARY: List[Dict[str, str]] = [
    {"key": "vote", "label": "Vote",
     "attack": "A referendum, popular initiative or election that is actually on a ballot.",
     "criteria": "Name it as it appears on the ballot, e.g. \"Neutrality initiative\"."},
    {"key": "party", "label": "Party",
     "attack": "A political party, its candidates as a bloc, or its campaign.",
     "criteria": "Use the common abbreviation, e.g. \"SVP\", \"SP\"."},
    {"key": "person", "label": "Person",
     "attack": "A named individual: a candidate, an officeholder, a journalist, a campaigner.",
     "criteria": "Full name. A deepfake or synthetic text aimed at a person raises an alert on its own."},
    {"key": "institution", "label": "Institution",
     "attack": "A body rather than a person: the Federal Council, a canton, a court, a platform, a newsroom, an election office.",
     "criteria": "The body as commonly named, e.g. \"Federal Council\"."},
    {"key": "policy", "label": "Policy",
     "attack": "A policy area or measure that is not itself on a ballot: neutrality, migration, energy, defence procurement.",
     "criteria": "Use this when no specific vote is named, otherwise prefer vote."},
]

ATTRIBUTION_GLOSSARY: List[Dict[str, str]] = [
    {"key": "russia", "label": "Russia", "attack": "The article names a Russian state actor or Russian state media.", "criteria": ""},
    {"key": "china", "label": "China", "attack": "The article names a Chinese state actor or Chinese state media.", "criteria": ""},
    {"key": "other_state", "label": "Another state", "attack": "The article names a state actor other than Russia or China.", "criteria": ""},
    {"key": "domestic", "label": "Domestic", "attack": "The article points at an actor inside the country: a party, a committee, a campaign, a domestic outlet.", "criteria": ""},
    {"key": "unattributed", "label": "Unattributed", "attack": "The article names nobody. The default.", "criteria": ""},
]

TIER_GLOSSARY: List[Dict[str, str]] = [
    {"key": "state_media", "label": "State media", "attack": "Owned or directed by a state.", "criteria": "A political line pushed at these voters is itself the signal."},
    {"key": "alt_media", "label": "Alternative media", "attack": "Outside the established press, with a campaigning editorial line.", "criteria": "A political line pushed at these voters is itself the signal."},
    {"key": "party", "label": "Party", "attack": "A party's own channel or press office.", "criteria": "A political line pushed at these voters is itself the signal."},
    {"key": "mainstream", "label": "Mainstream", "attack": "An established news organisation.", "criteria": "Ordinary opinion for or against a vote is off topic; manipulation, foreign influence or a false claim is on topic."},
    {"key": "fact_checker", "label": "Fact-checker", "attack": "A verification outfit.", "criteria": "Stricter test, as mainstream."},
    {"key": "institution", "label": "Institution", "attack": "An official or public body.", "criteria": "Stricter test, as mainstream."},
    {"key": "research", "label": "Research", "attack": "An academic or research organisation.", "criteria": "Stricter test, as mainstream."},
    {"key": "social", "label": "Social", "attack": "A social account with no outlet behind it.", "criteria": "Judged on what the account is doing, not on what it is."},
    {"key": "unknown", "label": "Unknown", "attack": "Not yet classified.", "criteria": "Gets the stricter test, so an untiered outlet's storylines are more likely to be dropped."},
]

STANCE_GLOSSARY: List[Dict[str, str]] = [
    {"key": "promotes", "label": "Promotes", "attack": "The article itself pushes the claim.", "criteria": ""},
    {"key": "reports", "label": "Reports", "attack": "The article reports that others push it.", "criteria": ""},
    {"key": "debunks", "label": "Debunks", "attack": "The article fact-checks or refutes it.", "criteria": ""},
]


def _prompt_glossary() -> str:
    """The technique and target definitions, as the model sees them."""
    techs = "\n".join(
        f"- {t['key']}: {t['attack']} Label it when: {t['criteria']}"
        for t in TECHNIQUE_GLOSSARY)
    targets = "\n".join(f"- {t['key']}: {t['attack']}" for t in TARGET_GLOSSARY)
    return ("Technique definitions. Use a technique only when its test is met, and "
            "none_reported when the article names no method:\n" + techs
            + "\n\nTarget types:\n" + targets)


EXTRACTION_PROMPT = """You analyse one item for a monitor of disinformation and influence operations aimed at {subject}. The item is usually a news article; it may be a social-media post, in which case the "source" below is the account handle and the text is short. Output ONLY valid JSON.

Article title: {title}
Original-language title (if different): {original_title}
Summary: {summary}
Source: {source}
Category assigned by the collector: {category}

Return this JSON object:
{{
  "language": "de|fr|it|en",                       // language the article was originally written in
  "on_topic": true|false,                          // true only if this item belongs in a watch of disinformation and influence operations aimed at {subject}. See the scope rule at the end; it decides this field. If you list any narrative below, on_topic must be true.
  "narratives": [                                  // 0-3 items. Each is a claim or storyline the article carries or discusses, as one plain sentence in English, phrased so the same storyline from another article would match it
    {{"statement": "...", "stance": "promotes|reports|debunks"}}
  ],                                               // promotes = the article itself pushes the claim; reports = it reports that others push it; debunks = it fact-checks or refutes it
  "targets": [ {{"type": "vote|party|person|institution|policy", "name": "..."}} ],   // what the manipulation is aimed at. If it is one of the known targets listed below, use that name EXACTLY. Otherwise give the common name, in English, with no qualifiers of your own: "Neutrality initiative", not "Neutrality initiative referendum" or "Neutrality initiative September 2025". Leave targets empty rather than naming something vague such as "public opinion", "referendum campaigns" or "the Swiss population".
  "attribution": {{"actor": "russia|china|other_state|domestic|unattributed", "confidence": 0.0-1.0}},   // who the ARTICLE says is behind it; unattributed if it does not say
  "techniques": ["deepfake","synthetic_text","bot_amplification","fake_account","forged_document","doctored_quote","decontextualised_media","astroturfing","state_media_placement","none_reported"],
  "source_tier": "state_media|alt_media|mainstream|party|fact_checker|institution|research|social|unknown",
  "fact_check": {{"claim": "...", "verdict": "false|misleading|true|unverified", "checker": "..."}} | null,   // only if the article IS a fact-check
  "response": {{"actor": "...", "action": "..."}} | null    // only if a federal body, platform, party or court acted (statement, takedown, complaint, investigation)
}}

This source is known to us as: {known_tier}

Known targets — reuse one of these names exactly when it is what the item is aimed at:
{known_targets}

__GLOSSARY__

Rules:
- Report what the article says; do not add knowledge of your own.
- If the source tier above is state_media, alt_media or party, then an article pushing a political line at Swiss readers IS the thing this monitor watches. Set on_topic true and record what it argues as a narrative with stance "promotes", even when the article alleges no manipulation and simply makes the case. That is the primary signal, not a miss.
- A social post is judged on what the account is doing: an account pushing a political line at these voters is on_topic true with stance "promotes"; a media or official account relaying news is "reports".
- If the source tier is mainstream, fact_checker, research, institution, social or unknown, apply the stricter test: ordinary opinion for or against a vote, with no manipulation, foreign influence or false claim in it, is on_topic false with no narratives.
- {angle_rule}
- Keep statements short and specific: "Switzerland's neutrality initiative is promoted by Russian state media" not "Russia is involved"."""

EXTRACTION_PROMPT = EXTRACTION_PROMPT.replace("__GLOSSARY__", _prompt_glossary())

BRIEF_PROMPT = """You write a short weekly brief for analysts at Swiss federal bodies, parties and platforms who monitor disinformation aimed at Swiss voters. Plain language, no hype, no bullet padding. Only use the data below; if it is thin, say the week was quiet and why that is credible (sources scanned, articles gated).

Period: last {days} days ending {today}
Articles that passed the relevance gate: {article_count}
Articles rejected by the gate: {rejected_count}
Active sources scanned: {source_count}

Narratives (name | statement | articles | languages | attribution | outlets):
{narratives}

Targets (name | type | articles):
{targets}

Techniques seen (technique | count):
{techniques}

Fact-checks and responses:
{responses}

Upcoming votes:
{calendar}

Return ONLY valid JSON:
{{
  "headline": "one sentence",
  "summary": "3-5 sentences on what moved this week",
  "narratives": "what the main storylines are, who carries them, whether they crossed a language border",
  "actors_and_vectors": "which outlets and which attributed actors",
  "targets": "what is being aimed at",
  "outlook": "what to watch before the next vote date",
  "brief_text": "the same content as one continuous 200-300 word note"
}}"""


def _social_handle(social_meta: Any) -> Optional[str]:
    """A Bluesky handle is itself a domain (pssuisse.ch, mediasch.bsky.social),
    so using it as the source domain makes the sd_sources tier lookup work on
    social posts with no special casing."""
    if not social_meta:
        return None
    meta = social_meta
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(meta, dict):
        handle = (meta.get("author") or meta.get("handle") or "").strip().lstrip("@").lower()
        return handle or None
    return None


def _domain(url: Optional[str], news_source: Optional[str]) -> Optional[str]:
    for candidate in (url, news_source):
        if not candidate:
            continue
        c = candidate.strip()
        if "://" not in c and "." in c and " " not in c:
            c = "https://" + c
        try:
            host = urlparse(c).netloc.lower()
        except Exception:
            host = ""
        if host:
            return host[4:] if host.startswith("www.") else host
    return None


def _feed_domain(url: Optional[str]) -> str:
    host = _domain(url, None) or ""
    return host


def _to_vector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"


def _parse_json(text_value: str) -> Dict[str, Any]:
    s = (text_value or "").strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class SwissDisinfoService:
    """Sync service. Routes call it through asyncio.to_thread."""

    def __init__(self, topic: str = DEFAULT_TOPIC):
        self.topic = topic

    # ------------------------------------------------------------------ util
    def _conn(self):
        return get_database_instance()._temp_get_connection()

    @staticmethod
    def _since(days_back: int) -> str:
        return (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # --------------------------------------------------------------- articles
    def get_unprocessed_articles(self, limit: int = 50, process_all: bool = False) -> List[Dict[str, Any]]:
        """Approved articles of the topic with no extraction yet (or all, for a reprocess)."""
        conn = self._conn()
        try:
            join = "" if process_all else "LEFT JOIN sd_extractions e ON e.article_uri = a.uri"
            where_extra = "" if process_all else "AND e.article_uri IS NULL"
            # Social posts never reach 'approved' — the cheap social eval files them
            # as 'social_evaluated' — so the module would never see them. Take them
            # above SOCIAL_MIN_ALIGNMENT, which is where the signal sat and the junk did not.
            rows = conn.execute(text(f"""
                SELECT a.uri, a.title, a.original_title, a.summary, a.category, a.sentiment,
                       a.news_source, a.url, a.publication_date, a.submission_date,
                       a.social_meta, a.ingest_status
                FROM articles a
                {join}
                WHERE a.topic = :topic
                  AND (a.ingest_status = 'approved'
                       OR (a.ingest_status = 'social_evaluated'
                           AND a.topic_alignment_score >= :social_min))
                  {where_extra}
                ORDER BY a.submission_date DESC
                LIMIT :limit
            """), {"topic": self.topic, "limit": limit,
                   "social_min": SOCIAL_MIN_ALIGNMENT}).fetchall()
            return [dict(r._mapping) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------- extraction
    def known_tier(self, domain: Optional[str]) -> str:
        """Curated tier for a domain, or 'unknown'. Read before the LLM call: the
        prompt applies a different on_topic test to state/alt/party sources."""
        if not domain:
            return "unknown"
        conn = self._conn()
        try:
            row = conn.execute(text("SELECT tier FROM sd_sources WHERE domain = :d"), {"d": domain}).fetchone()
            return row[0] if row else "unknown"
        finally:
            conn.close()

    async def extract_with_llm(self, article: Dict[str, Any], model_name: str = DEFAULT_MODEL,
                               known_tier: str = "unknown") -> Dict[str, Any]:
        from app.ai_models import LiteLLMModel
        sc = scope(self.topic)
        prompt = EXTRACTION_PROMPT.format(
            subject=sc["subject"], angle_rule=sc["angle_rule"],
            title=article.get("title") or "",
            original_title=article.get("original_title") or "(same)",
            summary=(article.get("summary") or "No summary available")[:4000],
            source=article.get("news_source") or _domain(article.get("url"), None) or "unknown",
            category=article.get("category") or "unknown",
            known_tier=known_tier,
            known_targets="\n".join("- " + n for n in self.known_target_names()) or "- (none yet)",
        )
        model = LiteLLMModel.get_instance(model_name)
        response = await model.agenerate_response([
            {"role": "system", "content": "You are an analyst of information operations. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ])
        return _parse_json(response)

    @staticmethod
    def _clean_extraction(raw: Dict[str, Any]) -> Dict[str, Any]:
        lang = str(raw.get("language") or "en").lower()[:2]
        if lang not in LANGUAGES:
            lang = "en"
        narratives = []
        for n in raw.get("narratives") or []:
            stmt = (n.get("statement") or "").strip()
            stance = (n.get("stance") or "reports").lower()
            if stmt and stance in STANCES:
                narratives.append({"statement": stmt[:500], "stance": stance})
        targets = []
        for t in raw.get("targets") or []:
            ttype = (t.get("type") or "").lower()
            name = (t.get("name") or "").strip()
            if name and ttype in ("vote", "party", "person", "institution", "policy"):
                targets.append({"type": ttype, "name": name[:200]})
        attr = raw.get("attribution") or {}
        actor = (attr.get("actor") or "unattributed").lower()
        if actor not in ATTRIBUTIONS:
            actor = "unattributed"
        try:
            conf = float(attr.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        techniques = [t for t in (raw.get("techniques") or []) if t in TECHNIQUES]
        # "none reported" is the empty answer, so it cannot stand beside a real
        # technique. The model returned both on a third of the sample.
        real = [t for t in techniques if t != "none_reported"]
        techniques = real or ["none_reported"]
        tier = (raw.get("source_tier") or "unknown").lower()
        if tier not in TIERS:
            tier = "unknown"
        fact_check = raw.get("fact_check") if isinstance(raw.get("fact_check"), dict) else None
        response = raw.get("response") if isinstance(raw.get("response"), dict) else None
        on_topic = bool(raw.get("on_topic", True))
        if narratives and not on_topic:
            logger.info("Extraction returned %s narrative(s) with on_topic false; taking the narratives",
                        len(narratives))
            on_topic = True
        return {
            "language": lang,
            "on_topic": on_topic,
            "narratives": narratives[:3],
            "targets": targets[:6],
            "attribution": actor,
            "attribution_confidence": max(0.0, min(1.0, conf)),
            "techniques": techniques,
            "source_tier": tier,
            "fact_check": fact_check,
            "response": response,
        }

    def _resolve_tier(self, conn, domain: Optional[str], model_tier: str, lang: str, today: date,
                      is_social: bool = False) -> str:
        """Known outlets keep their curated tier; unknown ones get the model's and are recorded."""
        if not domain:
            return model_tier
        row = conn.execute(text("SELECT tier FROM sd_sources WHERE domain = :d"), {"d": domain}).fetchone()
        if row:
            return row[0]
        if is_social:
            model_tier = "social"
        conn.execute(text("""
            INSERT INTO sd_sources (domain, name, tier, language, seeded, first_seen)
            VALUES (:d, :d, :t, :l, false, :day) ON CONFLICT (domain) DO NOTHING
        """), {"d": domain, "t": model_tier, "l": lang, "day": today})
        return model_tier

    def _candidate_narratives(self, statement: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Embedding shortlist. The 768-dim encoder scores every pair of statements
        in this domain between 0.86 and 0.96, so the shortlist is only a shortlist;
        the decision is made by the model in _pick_narrative."""
        from app.vector_store_pgvector import embed_query
        vec = _to_vector_literal(embed_query(statement))
        conn = self._conn()
        try:
            rows = conn.execute(text("""
                SELECT id, name, statement, 1 - (embedding <=> CAST(:v AS vector)) AS sim
                FROM sd_narratives WHERE embedding IS NOT NULL AND topic = :topic
                ORDER BY embedding <=> CAST(:v AS vector) LIMIT 8
            """), {"v": vec, "topic": self.topic}).fetchall()
            return vec, [{"id": int(r.id), "name": r.name, "statement": r.statement, "sim": float(r.sim or 0)}
                         for r in rows if float(r.sim or 0) >= NARRATIVE_MATCH_THRESHOLD]
        finally:
            conn.close()

    async def _pick_narrative(self, statement: str, candidates: List[Dict[str, Any]],
                              model_name: str) -> Optional[int]:
        """Ask the model which existing storyline, if any, the statement belongs to."""
        if not candidates:
            return None
        if candidates[0]["sim"] >= 0.985:
            return candidates[0]["id"]
        from app.ai_models import LiteLLMModel
        listing = "\n".join(f'{c["id"]}: {c["statement"]}' for c in candidates)
        prompt = (
            "You maintain a list of distinct disinformation storylines about Swiss politics. "
            "Decide whether the NEW statement expresses the SAME storyline as one of the EXISTING ones. "
            "Same storyline means the same claim about the same subject, even if worded differently or from the opposite stance "
            "(a debunk of claim X belongs to storyline X). A different claim about a related subject is NOT the same.\n\n"
            f"NEW: {statement}\n\nEXISTING:\n{listing}\n\n"
            'Answer with JSON only: {"match_id": <id or 0>}'
        )
        try:
            model = LiteLLMModel.get_instance(model_name)
            raw = await model.agenerate_response([
                {"role": "system", "content": "Respond only with valid JSON."},
                {"role": "user", "content": prompt}])
            mid = int(_parse_json(raw).get("match_id") or 0)
            return mid if any(c["id"] == mid for c in candidates) else None
        except Exception as e:
            logger.warning("Swiss disinfo narrative pick failed, creating new: %s", e)
            return None

    def _create_narrative(self, conn, statement: str, vec: str, attribution: str,
                          confidence: float, today: date) -> int:
        name = statement if len(statement) <= 120 else statement[:117] + "..."
        return int(conn.execute(text("""
            INSERT INTO sd_narratives (name, statement, topic, attribution, attribution_confidence,
                                       first_seen, last_seen, embedding)
            VALUES (:n, :s, :topic, :a, :c, :d, :d, CAST(:v AS vector))
            RETURNING id
        """), {"n": name, "s": statement, "topic": self.topic, "a": attribution,
               "c": confidence, "d": today, "v": vec}).fetchone()[0])

    async def process_article(self, article: Dict[str, Any], model_name: str = DEFAULT_MODEL) -> Dict[str, Any]:
        """Extract, store, attach narratives. Returns counts for the caller."""
        uri = article["uri"]
        art_date = None
        for key in ("publication_date", "submission_date"):
            v = article.get(key)
            if v:
                try:
                    art_date = datetime.fromisoformat(str(v)[:19]).date()
                    break
                except ValueError:
                    continue
        art_date = art_date or date.today()
        domain = _social_handle(article.get("social_meta")) or _domain(
            article.get("url"), article.get("news_source"))

        try:
            tier_hint = await asyncio.to_thread(self.known_tier, domain)
            raw = await self.extract_with_llm(article, model_name, tier_hint)
            ex = self._clean_extraction(raw)
            ex["targets"] = self.canonical_targets(ex.get("targets") or [])
            error = None
        except Exception as e:  # keep the row so the article is not retried forever
            logger.warning("Swiss disinfo extraction failed for %s: %s", uri, e)
            ex = self._clean_extraction({})
            error = str(e)[:500]

        # Resolve narrative matches first (embedding + model) so no DB connection
        # is held open across an LLM round-trip.
        resolved: List[Tuple[Dict[str, Any], Optional[int], str]] = []
        if ex["on_topic"] and not error:
            for n in ex["narratives"]:
                try:
                    vec, cands = await asyncio.to_thread(self._candidate_narratives, n["statement"])
                    match = await self._pick_narrative(n["statement"], cands, model_name)
                    resolved.append((n, match, vec))
                except Exception as e:
                    logger.warning("Swiss disinfo narrative matching failed for %s: %s", uri, e)

        created = 0
        attached = 0
        conn = self._conn()
        try:
            tier = self._resolve_tier(conn, domain, ex["source_tier"], ex["language"], art_date,
                                      is_social=bool(article.get("social_meta")))
            conn.execute(text("""
                INSERT INTO sd_extractions (article_uri, topic, language, source_domain, source_tier,
                    attribution, attribution_confidence, techniques, targets, narratives,
                    fact_check, response, model, error, article_date, extracted_at)
                VALUES (:uri, :topic, :lang, :dom, :tier, :attr, :conf, :tech, CAST(:targets AS jsonb),
                        CAST(:narr AS jsonb), CAST(:fc AS jsonb), CAST(:resp AS jsonb), :model,
                        :err, :day, NOW())
                ON CONFLICT (article_uri) DO UPDATE SET
                    language = EXCLUDED.language, source_domain = EXCLUDED.source_domain,
                    source_tier = EXCLUDED.source_tier, attribution = EXCLUDED.attribution,
                    attribution_confidence = EXCLUDED.attribution_confidence,
                    techniques = EXCLUDED.techniques, targets = EXCLUDED.targets,
                    narratives = EXCLUDED.narratives, fact_check = EXCLUDED.fact_check,
                    response = EXCLUDED.response, model = EXCLUDED.model, error = EXCLUDED.error,
                    article_date = EXCLUDED.article_date, extracted_at = NOW()
            """), {
                "uri": uri, "topic": self.topic, "lang": ex["language"], "dom": domain, "tier": tier,
                "attr": ex["attribution"], "conf": ex["attribution_confidence"],
                "tech": ex["techniques"], "targets": json.dumps(ex["targets"]),
                "narr": json.dumps(ex["narratives"]),
                "fc": json.dumps(ex["fact_check"]) if ex["fact_check"] else None,
                "resp": json.dumps(ex["response"]) if ex["response"] else None,
                "model": model_name, "err": error, "day": art_date,
            })
            # A reprocess replaces the article's narrative links.
            conn.execute(text("DELETE FROM sd_narrative_articles WHERE article_uri = :uri"), {"uri": uri})
            if ex["on_topic"] and not error:
                for n, match, vec in resolved:
                    if match is None:
                        nid = self._create_narrative(conn, n["statement"], vec, ex["attribution"],
                                                     ex["attribution_confidence"], art_date)
                        created += 1
                    else:
                        nid = match
                    conn.execute(text("""
                        INSERT INTO sd_narrative_articles
                            (narrative_id, article_uri, topic, stance, language, source_domain,
                             source_tier, article_date)
                        VALUES (:nid, :uri, :topic, :stance, :lang, :dom, :tier, :day)
                        ON CONFLICT ON CONSTRAINT uq_sd_narrative_article DO NOTHING
                    """), {"nid": nid, "uri": uri, "topic": self.topic, "stance": n["stance"],
                           "lang": ex["language"], "dom": domain, "tier": tier, "day": art_date})
                    attached += 1
                    conn.execute(text("""
                        UPDATE sd_narratives n SET
                            article_count = (SELECT COUNT(*) FROM sd_narrative_articles WHERE narrative_id = n.id),
                            languages = (SELECT COALESCE(ARRAY_AGG(DISTINCT language), '{}')
                                         FROM sd_narrative_articles WHERE narrative_id = n.id AND language IS NOT NULL),
                            first_seen = LEAST(COALESCE(first_seen, :day), :day),
                            last_seen = GREATEST(COALESCE(last_seen, :day), :day),
                            updated_at = NOW()
                        WHERE n.id = :nid
                    """), {"nid": nid, "day": art_date})
            conn.commit()
        finally:
            conn.close()
        return {"uri": uri, "on_topic": ex["on_topic"], "narratives_created": created,
                "narratives_attached": attached, "error": error}

    def reconcile_narratives(self) -> Dict[str, int]:
        """Recompute every narrative's rollups and drop the ones left with no
        articles. process_article only refreshes narratives it just attached to,
        so a reprocess that moves an article elsewhere leaves the old narrative
        with a stale count, or with none at all (found 2026-09-16 after the
        tier-aware on_topic change re-ran the whole corpus)."""
        conn = self._conn()
        try:
            conn.execute(text("""
                UPDATE sd_narratives n SET
                    article_count = c.n,
                    languages = c.langs,
                    first_seen = c.first_day,
                    last_seen = c.last_day,
                    updated_at = NOW()
                FROM (
                    SELECT narrative_id,
                           COUNT(*) AS n,
                           COALESCE(ARRAY_AGG(DISTINCT language) FILTER (WHERE language IS NOT NULL), '{}') AS langs,
                           MIN(article_date) AS first_day,
                           MAX(article_date) AS last_day
                    FROM sd_narrative_articles GROUP BY narrative_id
                ) c
                WHERE c.narrative_id = n.id
            """))
            removed = conn.execute(text("""
                DELETE FROM sd_narratives n
                WHERE NOT EXISTS (SELECT 1 FROM sd_narrative_articles na WHERE na.narrative_id = n.id)
            """)).rowcount
            conn.commit()
            return {"orphans_removed": int(removed or 0)}
        finally:
            conn.close()

    async def process_batch(self, limit: int = 50, model_name: str = DEFAULT_MODEL,
                            process_all: bool = False, progress=None) -> Dict[str, Any]:
        articles = self.get_unprocessed_articles(limit=limit, process_all=process_all)
        stats = {"processed": 0, "on_topic": 0, "narratives_created": 0, "errors": 0, "total": len(articles)}
        for i, art in enumerate(articles, 1):
            res = await self.process_article(art, model_name)
            stats["processed"] += 1
            stats["on_topic"] += int(res["on_topic"])
            stats["narratives_created"] += res["narratives_created"]
            stats["errors"] += int(bool(res["error"]))
            if progress:
                progress(i, len(articles))
        if articles:
            stats.update(await asyncio.to_thread(self.reconcile_narratives))
        return stats

    # ---------------------------------------------------------------- panels
    def overview(self, days_back: int = 7) -> Dict[str, Any]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            since_prev = self._since(days_back * 2)
            approved, rejected = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE ingest_status = 'approved'),
                       COUNT(*) FILTER (WHERE ingest_status = 'filtered_relevance')
                FROM articles WHERE topic = :t AND submission_date >= :s
            """), {"t": self.topic, "s": since}).fetchone()
            approved_prev = conn.execute(text("""
                SELECT COUNT(*) FROM articles WHERE topic = :t AND ingest_status = 'approved'
                  AND submission_date >= :p AND submission_date < :s
            """), {"t": self.topic, "p": since_prev, "s": since}).fetchone()[0]
            extracted = conn.execute(text(
                "SELECT COUNT(*) FROM sd_extractions WHERE article_date >= CAST(:s AS date) "
                "AND topic = :topic"), {"s": since, "topic": self.topic}).fetchone()[0]
            narratives_active = conn.execute(text("""
                SELECT COUNT(DISTINCT narrative_id) FROM sd_narrative_articles
                WHERE article_date >= CAST(:s AS date) AND topic = :topic
            """), {"s": since, "topic": self.topic}).fetchone()[0]
            narratives_new = conn.execute(text(
                "SELECT COUNT(*) FROM sd_narratives WHERE first_seen >= CAST(:s AS date) "
                "AND topic = :topic"), {"s": since, "topic": self.topic}).fetchone()[0]
            vector_share_row = conn.execute(text("""
                SELECT COUNT(*) FILTER (WHERE source_tier IN ('state_media','alt_media')), COUNT(*)
                FROM sd_extractions WHERE article_date >= CAST(:s AS date) AND topic = :topic
            """), {"s": since, "topic": self.topic}).fetchone()
            vector_share = (vector_share_row[0] / vector_share_row[1]) if vector_share_row[1] else 0.0
            sources_scanned = conn.execute(text("""
                SELECT (SELECT COUNT(*) FROM rss_feeds WHERE topic = :t AND is_active)
                     + (SELECT COUNT(*) FROM keyword_groups WHERE topic = :t AND is_active)
            """), {"t": self.topic}).fetchone()[0]
            stance_series = conn.execute(text("""
                SELECT article_date AS day, stance, COUNT(*)
                FROM sd_narrative_articles WHERE article_date >= CAST(:s AS date) AND topic = :topic
                GROUP BY 1, 2 ORDER BY 1
            """), {"s": since, "topic": self.topic}).fetchall()
            by_day: Dict[str, Dict[str, int]] = {}
            for d, stance, n in stance_series:
                by_day.setdefault(str(d), {"day": str(d), "promotes": 0, "reports": 0, "debunks": 0})[stance] = int(n)
            categories = conn.execute(text("""
                SELECT category, COUNT(*) FROM articles
                WHERE topic = :t AND ingest_status = 'approved' AND submission_date >= :s
                  AND category IS NOT NULL
                GROUP BY 1 ORDER BY 2 DESC LIMIT 14
            """), {"t": self.topic, "s": since}).fetchall()
            attribution = conn.execute(text("""
                SELECT attribution, COUNT(*) FROM sd_extractions
                WHERE article_date >= CAST(:s AS date) AND topic = :topic
                GROUP BY 1 ORDER BY 2 DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            next_vote = next(((d, label) for d, label in scope(self.topic)["calendar"]
                              if d >= date.today()), None)
            return {
                "days_back": days_back,
                "approved": int(approved), "approved_prev": int(approved_prev),
                "rejected": int(rejected), "extracted": int(extracted),
                "narratives_active": int(narratives_active), "narratives_new": int(narratives_new),
                "vector_share": round(vector_share, 3),
                "sources_scanned": int(sources_scanned),
                "next_vote": {"date": next_vote[0].isoformat(), "label": next_vote[1],
                              "days_to": (next_vote[0] - date.today()).days} if next_vote else None,
                "stance_series": list(by_day.values()),
                "categories": [{"category": c, "count": int(n)} for c, n in categories],
                "attribution": [{"actor": a, "count": int(n)} for a, n in attribution],
            }
        finally:
            conn.close()

    def narratives(self, days_back: int = 30, language: Optional[str] = None,
                   stance: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            rows = conn.execute(text("""
                WITH recent AS (
                    SELECT na.narrative_id, na.stance, na.language, na.source_domain, na.article_date
                    FROM sd_narrative_articles na
                    WHERE na.article_date >= CAST(:s AS date) AND na.topic = :topic
                      AND (:lang IS NULL OR na.language = :lang)
                      AND (:stance IS NULL OR na.stance = :stance)
                )
                SELECT n.id, n.name, n.statement, n.attribution, n.attribution_confidence,
                       n.first_seen, n.last_seen, n.article_count, n.languages,
                       COUNT(r.narrative_id) AS recent_count,
                       COUNT(r.narrative_id) FILTER (WHERE r.stance = 'promotes') AS promotes,
                       COUNT(r.narrative_id) FILTER (WHERE r.stance = 'reports') AS reports,
                       COUNT(r.narrative_id) FILTER (WHERE r.stance = 'debunks') AS debunks,
                       COUNT(r.narrative_id) FILTER (WHERE r.article_date >= CURRENT_DATE - 7) AS last7,
                       COUNT(r.narrative_id) FILTER (WHERE r.article_date >= CURRENT_DATE - 14
                                                       AND r.article_date < CURRENT_DATE - 7) AS prev7,
                       (SELECT ARRAY_AGG(d ORDER BY c DESC) FROM (
                            SELECT source_domain d, COUNT(*) c FROM sd_narrative_articles
                            WHERE narrative_id = n.id AND source_domain IS NOT NULL
                            GROUP BY 1 ORDER BY 2 DESC LIMIT 3) x) AS top_outlets
                FROM sd_narratives n
                JOIN recent r ON r.narrative_id = n.id
                GROUP BY n.id
                ORDER BY recent_count DESC, n.last_seen DESC
                LIMIT :limit
            """), {"s": since, "lang": language, "stance": stance, "limit": limit,
                   "topic": self.topic}).fetchall()
            out = []
            for r in rows:
                m = dict(r._mapping)
                m["first_seen"] = m["first_seen"].isoformat() if m["first_seen"] else None
                m["last_seen"] = m["last_seen"].isoformat() if m["last_seen"] else None
                m["languages"] = list(m["languages"] or [])
                m["top_outlets"] = list(m["top_outlets"] or [])
                for k in ("recent_count", "promotes", "reports", "debunks", "last7", "prev7", "article_count"):
                    m[k] = int(m[k] or 0)
                out.append(m)
            return out
        finally:
            conn.close()

    def narrative_detail(self, narrative_id: int) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            n = conn.execute(text("SELECT * FROM sd_narratives WHERE id = :id"), {"id": narrative_id}).fetchone()
            if not n:
                return None
            head = dict(n._mapping)
            head.pop("embedding", None)
            for k in ("first_seen", "last_seen"):
                head[k] = head[k].isoformat() if head[k] else None
            head["created_at"] = head["created_at"].isoformat() if head.get("created_at") else None
            head["updated_at"] = head["updated_at"].isoformat() if head.get("updated_at") else None
            head["languages"] = list(head.get("languages") or [])
            arts = conn.execute(text("""
                SELECT na.article_uri AS uri, a.title, a.news_source, COALESCE(NULLIF(a.url, ''), CASE WHEN a.uri LIKE 'http%' THEN a.uri END) AS url, na.stance, na.language,
                       na.source_domain, na.source_tier, na.article_date, a.topic_alignment_score
                FROM sd_narrative_articles na JOIN articles a ON a.uri = na.article_uri
                WHERE na.narrative_id = :id ORDER BY na.article_date DESC
            """), {"id": narrative_id}).fetchall()
            lang_series = conn.execute(text("""
                SELECT article_date, language, COUNT(*) FROM sd_narrative_articles
                WHERE narrative_id = :id GROUP BY 1, 2 ORDER BY 1
            """), {"id": narrative_id}).fetchall()
            fact_checks = conn.execute(text("""
                SELECT e.article_uri, e.fact_check, e.article_date FROM sd_extractions e
                JOIN sd_narrative_articles na ON na.article_uri = e.article_uri
                WHERE na.narrative_id = :id AND e.fact_check IS NOT NULL
            """), {"id": narrative_id}).fetchall()
            head["articles"] = [
                {**dict(a._mapping), "article_date": a.article_date.isoformat() if a.article_date else None}
                for a in arts]
            head["language_series"] = [
                {"day": d.isoformat(), "language": lang, "count": int(c)} for d, lang, c in lang_series]
            head["fact_checks"] = [
                {"uri": u, "fact_check": fc, "date": d.isoformat() if d else None} for u, fc, d in fact_checks]
            return head
        finally:
            conn.close()

    def sources(self, days_back: int = 30) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            rows = conn.execute(text("""
                SELECT e.source_domain AS domain, COALESCE(s.name, e.source_domain) AS name,
                       COALESCE(s.tier, e.source_tier, 'unknown') AS tier,
                       COALESCE(s.language, MODE() WITHIN GROUP (ORDER BY e.language)) AS language,
                       COUNT(*) AS articles,
                       COUNT(*) FILTER (WHERE e.article_date >= CURRENT_DATE - 7) AS last7,
                       COUNT(DISTINCT na.narrative_id) AS narratives,
                       COUNT(DISTINCT na.narrative_id) FILTER (WHERE na.stance = 'promotes') AS promoted,
                       MIN(e.article_date) AS first_seen, MAX(e.article_date) AS last_seen
                FROM sd_extractions e
                LEFT JOIN sd_sources s ON s.domain = e.source_domain
                LEFT JOIN sd_narrative_articles na ON na.article_uri = e.article_uri
                WHERE e.article_date >= CAST(:s AS date) AND e.topic = :topic
                  AND e.source_domain IS NOT NULL
                GROUP BY 1, 2, 3, s.language
                ORDER BY articles DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            return [{**dict(r._mapping),
                     "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                     "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                     "articles": int(r.articles), "last7": int(r.last7),
                     "narratives": int(r.narratives), "promoted": int(r.promoted)} for r in rows]
        finally:
            conn.close()

    def cooccurrence(self, days_back: int = 30, limit_sources: int = 12, limit_narratives: int = 12) -> Dict[str, Any]:
        """Outlet x narrative counts: three outlets on one statement in 48 hours is what coordination looks like."""
        conn = self._conn()
        try:
            since = self._since(days_back)
            rows = conn.execute(text("""
                SELECT na.source_domain, na.narrative_id, n.name, COUNT(*) AS c
                FROM sd_narrative_articles na JOIN sd_narratives n ON n.id = na.narrative_id
                WHERE na.article_date >= CAST(:s AS date) AND na.topic = :topic
                  AND na.source_domain IS NOT NULL
                GROUP BY 1, 2, 3
            """), {"s": since, "topic": self.topic}).fetchall()
            src_tot: Dict[str, int] = {}
            nar_tot: Dict[int, Tuple[str, int]] = {}
            for d, nid, name, c in rows:
                src_tot[d] = src_tot.get(d, 0) + int(c)
                nar_tot[nid] = (name, nar_tot.get(nid, (name, 0))[1] + int(c))
            top_src = [d for d, _ in sorted(src_tot.items(), key=lambda x: -x[1])[:limit_sources]]
            top_nar = [nid for nid, _ in sorted(nar_tot.items(), key=lambda x: -x[1][1])[:limit_narratives]]
            cells = [{"source": d, "narrative_id": nid, "count": int(c)}
                     for d, nid, _, c in rows if d in top_src and nid in top_nar]
            return {"sources": top_src,
                    "narratives": [{"id": nid, "name": nar_tot[nid][0]} for nid in top_nar],
                    "cells": cells}
        finally:
            conn.close()

    def targets(self, days_back: int = 30) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            rows = conn.execute(text("""
                SELECT t->>'type' AS type, t->>'name' AS name, COUNT(*) AS articles,
                       COUNT(*) FILTER (WHERE e.article_date >= CURRENT_DATE - 7) AS last7,
                       MAX(e.article_date) AS last_seen
                FROM sd_extractions e, jsonb_array_elements(e.targets) t
                WHERE e.article_date >= CAST(:s AS date) AND e.topic = :topic
                GROUP BY 1, 2 ORDER BY articles DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            # Resolved here as well as at write time, so an alias added to the
            # registry today folds yesterday's rows together without a reprocess.
            amap = self._target_aliases()
            merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for r in rows:
                ttype, name = amap.get((r.name or "").strip().lower(), (r.type, r.name))
                key = (ttype, name.lower())
                cur = merged.get(key)
                if cur is None:
                    merged[key] = {"type": ttype, "name": name, "articles": int(r.articles),
                                   "last7": int(r.last7),
                                   "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                                   "seeded": False}
                    continue
                cur["articles"] += int(r.articles)
                cur["last7"] += int(r.last7)
                last = r.last_seen.isoformat() if r.last_seen else None
                if last and (cur["last_seen"] is None or last > cur["last_seen"]):
                    cur["last_seen"] = last
            out = sorted(merged.values(), key=lambda d: -d["articles"])
            seen = set(merged.keys())
            seeded = conn.execute(text("SELECT type, name FROM sd_targets WHERE seeded ORDER BY type, name")).fetchall()
            for ttype, name in seeded:
                if (ttype, name.lower()) not in seen:
                    out.append({"type": ttype, "name": name, "articles": 0, "last7": 0,
                                "last_seen": None, "seeded": True})
            return out
        finally:
            conn.close()

    def techniques(self, days_back: int = 30) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            rows = conn.execute(text("""
                SELECT tech, COUNT(*) AS articles,
                       COUNT(*) FILTER (WHERE e.article_date >= CURRENT_DATE - 7) AS last7,
                       MIN(e.article_date) AS first_seen, MAX(e.article_date) AS last_seen
                FROM sd_extractions e, unnest(e.techniques) tech
                WHERE e.article_date >= CAST(:s AS date) AND e.topic = :topic
                GROUP BY 1 ORDER BY articles DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            found = {r.tech for r in rows}
            out = [{"technique": r.tech, "articles": int(r.articles), "last7": int(r.last7),
                    "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None} for r in rows]
            out += [{"technique": t, "articles": 0, "last7": 0, "first_seen": None, "last_seen": None}
                    for t in TECHNIQUES if t not in found]
            return out
        finally:
            conn.close()

    def languages(self, days_back: int = 30) -> Dict[str, Any]:
        """Per narrative, per language, per week: where a storyline crosses the language border."""
        conn = self._conn()
        try:
            since = self._since(days_back)
            totals = conn.execute(text("""
                SELECT language, COUNT(*) FROM sd_extractions
                WHERE article_date >= CAST(:s AS date) AND topic = :topic GROUP BY 1
            """), {"s": since, "topic": self.topic}).fetchall()
            rows = conn.execute(text("""
                SELECT n.id, n.name, na.language, MIN(na.article_date) AS first_in_lang, COUNT(*) AS c
                FROM sd_narrative_articles na JOIN sd_narratives n ON n.id = na.narrative_id
                WHERE na.article_date >= CAST(:s AS date) AND na.topic = :topic
                  AND na.language IS NOT NULL
                GROUP BY 1, 2, 3
            """), {"s": since, "topic": self.topic}).fetchall()
            per: Dict[int, Dict[str, Any]] = {}
            for nid, name, lang, first, c in rows:
                p = per.setdefault(nid, {"id": nid, "name": name, "by_language": {}, "first_by_language": {}})
                p["by_language"][lang] = int(c)
                p["first_by_language"][lang] = first.isoformat()
            crossings = []
            for p in per.values():
                if len(p["first_by_language"]) >= 2:
                    order = sorted(p["first_by_language"].items(), key=lambda x: x[1])
                    p["crossed_from"] = order[0][0]
                    p["crossed_to"] = [l for l, _ in order[1:]]
                    p["lag_days"] = (date.fromisoformat(order[1][1]) - date.fromisoformat(order[0][1])).days
                    crossings.append(p)
            series = conn.execute(text("""
                SELECT date_trunc('week', article_date)::date AS wk, language, COUNT(*)
                FROM sd_extractions WHERE article_date >= CAST(:s AS date) AND topic = :topic
                GROUP BY 1, 2 ORDER BY 1
            """), {"s": since, "topic": self.topic}).fetchall()
            weeks: Dict[str, Dict[str, Any]] = {}
            for wk, lang, c in series:
                weeks.setdefault(wk.isoformat(), {"week": wk.isoformat(), "de": 0, "fr": 0, "it": 0, "en": 0})[lang] = int(c)
            return {"totals": {lang: int(c) for lang, c in totals},
                    "narratives": sorted(per.values(), key=lambda p: -sum(p["by_language"].values())),
                    "crossings": sorted(crossings, key=lambda p: p["lag_days"]),
                    "weekly": list(weeks.values())}
        finally:
            conn.close()

    def calendar(self, days_back: int = 60, days_ahead: int = 420) -> Dict[str, Any]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            daily = conn.execute(text("""
                SELECT article_date, COUNT(*) AS c,
                       COUNT(*) FILTER (WHERE stance = 'promotes') AS promotes
                FROM sd_narrative_articles WHERE article_date >= CAST(:s AS date) AND topic = :topic
                GROUP BY 1 ORDER BY 1
            """), {"s": since, "topic": self.topic}).fetchall()
            first_seen = conn.execute(text("""
                SELECT id, name, first_seen FROM sd_narratives
                WHERE first_seen >= CAST(:s AS date) AND topic = :topic ORDER BY first_seen
            """), {"s": since, "topic": self.topic}).fetchall()
            events = conn.execute(text("""
                SELECT id, event_type, event_subtype, title, description, significance, event_date
                FROM timeline_events
                WHERE scope_type = 'topic' AND scope_id = :t
                  AND event_date >= CAST(:s AS date)
                  AND event_date <= CURRENT_DATE + :ahead
                ORDER BY event_date
            """), {"t": self.topic, "s": since, "ahead": days_ahead}).fetchall()
            return {
                "daily": [{"day": d.isoformat(), "count": int(c), "promotes": int(p)} for d, c, p in daily],
                "first_seen": [{"id": i, "name": n, "day": d.isoformat()} for i, n, d in first_seen],
                "events": [{**dict(e._mapping), "event_date": e.event_date.isoformat()} for e in events],
                "votes": [{"date": d.isoformat(), "label": label,
                           "days_to": (d - date.today()).days}
                          for d, label in scope(self.topic)["calendar"]],
            }
        finally:
            conn.close()

    def responses(self, days_back: int = 90) -> Dict[str, Any]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            fcs = conn.execute(text("""
                SELECT e.article_uri, e.article_date, e.fact_check, a.title, a.news_source, COALESCE(NULLIF(a.url, ''), CASE WHEN a.uri LIKE 'http%' THEN a.uri END) AS url
                FROM sd_extractions e JOIN articles a ON a.uri = e.article_uri
                WHERE e.fact_check IS NOT NULL AND e.article_date >= CAST(:s AS date)
                  AND e.topic = :topic
                ORDER BY e.article_date DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            resps = conn.execute(text("""
                SELECT e.article_uri, e.article_date, e.response, a.title, a.news_source, COALESCE(NULLIF(a.url, ''), CASE WHEN a.uri LIKE 'http%' THEN a.uri END) AS url
                FROM sd_extractions e JOIN articles a ON a.uri = e.article_uri
                WHERE e.response IS NOT NULL AND e.article_date >= CAST(:s AS date)
                  AND e.topic = :topic
                ORDER BY e.article_date DESC
            """), {"s": since, "topic": self.topic}).fetchall()
            def _row(r, key):
                return {"uri": r.article_uri, "date": r.article_date.isoformat() if r.article_date else None,
                        key: getattr(r, key), "title": r.title, "news_source": r.news_source, "url": r.url}
            return {"fact_checks": [_row(r, "fact_check") for r in fcs],
                    "responses": [_row(r, "response") for r in resps]}
        finally:
            conn.close()

    def articles(self, days_back: int = 30, language: Optional[str] = None, tier: Optional[str] = None,
                 attribution: Optional[str] = None, technique: Optional[str] = None,
                 page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        conn = self._conn()
        try:
            since = self._since(days_back)
            where = ["a.topic = :t", "a.submission_date >= :s",
                     "(a.ingest_status = 'approved' OR (a.ingest_status = 'social_evaluated'"
                     " AND a.topic_alignment_score >= :social_min))"]
            params: Dict[str, Any] = {"t": self.topic, "s": since,
                                      "social_min": SOCIAL_MIN_ALIGNMENT}
            if language:
                where.append("e.language = :lang"); params["lang"] = language
            if tier:
                where.append("e.source_tier = :tier"); params["tier"] = tier
            if attribution:
                where.append("e.attribution = :attr"); params["attr"] = attribution
            if technique:
                where.append(":tech = ANY(e.techniques)"); params["tech"] = technique
            w = " AND ".join(where)
            total = conn.execute(text(f"""
                SELECT COUNT(*) FROM articles a LEFT JOIN sd_extractions e ON e.article_uri = a.uri WHERE {w}
            """), params).fetchone()[0]
            params.update({"lim": per_page, "off": (max(page, 1) - 1) * per_page})
            rows = conn.execute(text(f"""
                SELECT a.uri, a.title, a.summary, a.news_source, COALESCE(NULLIF(a.url, ''), CASE WHEN a.uri LIKE 'http%' THEN a.uri END) AS url, a.category, a.sentiment,
                       a.publication_date, a.submission_date, a.topic_alignment_score,
                       e.language, e.source_tier, e.attribution, e.techniques, e.targets, e.narratives,
                       e.fact_check, e.response, e.extracted_at
                FROM articles a LEFT JOIN sd_extractions e ON e.article_uri = a.uri
                WHERE {w}
                ORDER BY a.submission_date DESC LIMIT :lim OFFSET :off
            """), params).fetchall()
            out = []
            for r in rows:
                m = dict(r._mapping)
                m["techniques"] = list(m.get("techniques") or [])
                m["extracted_at"] = m["extracted_at"].isoformat() if m.get("extracted_at") else None
                out.append(m)
            return {"total": int(total), "page": page, "per_page": per_page, "articles": out}
        finally:
            conn.close()

    # ---------------------------------------------------------------- briefs
    async def generate_brief(self, days_back: int = 7, model_name: str = BRIEF_MODEL) -> Dict[str, Any]:
        from app.ai_models import LiteLLMModel
        ov = self.overview(days_back)
        nars = self.narratives(days_back)
        tgs = [t for t in self.targets(days_back) if t["articles"]]
        techs = [t for t in self.techniques(days_back) if t["articles"] and t["technique"] != "none_reported"]
        resp = self.responses(days_back)
        prompt = BRIEF_PROMPT.format(
            days=days_back, today=date.today().isoformat(),
            article_count=ov["approved"], rejected_count=ov["rejected"], source_count=ov["sources_scanned"],
            narratives="\n".join(
                f"- {n['name']} | {n['statement']} | {n['recent_count']} | {','.join(n['languages'])} | "
                f"{n['attribution']} | {', '.join(n['top_outlets'])}" for n in nars[:15]) or "- none",
            targets="\n".join(f"- {t['name']} | {t['type']} | {t['articles']}" for t in tgs[:15]) or "- none",
            techniques="\n".join(f"- {t['technique']} | {t['articles']}" for t in techs) or "- none reported",
            responses="\n".join(
                [f"- fact-check {r['date']}: {r['fact_check']}" for r in resp['fact_checks'][:8]] +
                [f"- response {r['date']}: {r['response']}" for r in resp['responses'][:8]]) or "- none",
            calendar="\n".join(f"- {d.isoformat()}: {l}" for d, l in scope(self.topic)["calendar"]
                               if d >= date.today()) or "- none in this scope",
        )
        model = LiteLLMModel.get_instance(model_name)
        raw = await model.agenerate_response([
            {"role": "system", "content": "You write plain, factual analyst notes. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ])
        data = _parse_json(raw)
        brief_text = data.get("brief_text") or data.get("summary") or ""
        conn = self._conn()
        try:
            bid = conn.execute(text("""
                INSERT INTO sd_briefs (brief_text, topic, sections, narrative_count, article_count,
                                       days_back, model)
                VALUES (:b, :topic, CAST(:sec AS jsonb), :nc, :ac, :d, :m) RETURNING id
            """), {"b": brief_text, "topic": self.topic, "sec": json.dumps(data), "nc": len(nars),
                   "ac": ov["approved"], "d": days_back, "m": model_name}).fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        return {"id": int(bid), "brief_text": brief_text, "sections": data,
                "narrative_count": len(nars), "article_count": ov["approved"],
                "days_back": days_back, "model": model_name, "created_at": datetime.now().isoformat()}

    def latest_brief(self) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            r = conn.execute(text("SELECT * FROM sd_briefs WHERE topic = :topic "
                                  "ORDER BY created_at DESC LIMIT 1"), {"topic": self.topic}).fetchone()
            if not r:
                return None
            m = dict(r._mapping)
            m["created_at"] = m["created_at"].isoformat()
            return m
        finally:
            conn.close()

    # ------------------------------------------------------------ how it works
    def how_it_works(self) -> Dict[str, Any]:
        """The live inventory behind this watch: every source it collects from,
        with what it has actually produced, plus the settings each pipeline
        stage runs on. Read from the database rather than written down, because
        the source list is the part that changes."""
        conn = self._conn()
        try:
            groups = conn.execute(text("""
                SELECT g.id, g.name, g.language, g.providers, g.social_platforms, g.is_active,
                       g.min_relevance_threshold, g.last_checked_at,
                       COALESCE(ARRAY_AGG(k.keyword ORDER BY k.id) FILTER (WHERE k.id IS NOT NULL), '{}') AS keywords
                FROM keyword_groups g
                LEFT JOIN monitored_keywords k ON k.group_id = g.id
                WHERE g.topic = :topic
                GROUP BY g.id ORDER BY g.id
            """), {"topic": self.topic}).fetchall()
            feeds = conn.execute(text("""
                SELECT f.id, f.name, f.url, f.is_active, f.relevance_threshold,
                       f.articles_fetched, f.last_checked_at, f.last_error,
                       s.tier, s.language
                FROM rss_feeds f
                LEFT JOIN sd_sources s
                       ON s.domain = regexp_replace(regexp_replace(f.url, '^https?://(www\\.)?', ''), '/.*$', '')
                WHERE f.topic = :topic ORDER BY f.is_active DESC, f.name
            """), {"topic": self.topic}).fetchall()
            # Grouped by the article's own domain, not by news_source: an RSS
            # article carries the feed's title ("Aktuelle News aus der Schweiz
            # und weltweit - SRF") while the same outlet collected any other way
            # carries "srf.ch", and the list showed both. Social posts have no
            # outlet domain worth grouping on, so they group by platform.
            produced = {r[0]: {"articles": int(r[1]), "approved": int(r[2]), "label": r[3]}
                        for r in conn.execute(text("""
                SELECT key, COUNT(*), COUNT(*) FILTER (WHERE ingest_status = 'approved'),
                       MIN(label) AS label
                FROM (
                    SELECT a.ingest_status,
                           CASE WHEN a.news_source IN ('bluesky','bsky','telegram','reddit')
                                  OR a.news_source LIKE 'xpoz:%'
                                THEN a.news_source
                                ELSE regexp_replace(regexp_replace(
                                       COALESCE(NULLIF(a.url, ''), a.uri),
                                       '^https?://(www\\.)?', ''), '/.*$', '') END AS key,
                           a.news_source AS label
                    FROM articles a WHERE a.topic = :topic
                ) s GROUP BY key
            """), {"topic": self.topic}).fetchall()}
            # A feed's name rarely equals the article's news_source ("Republik"
            # vs "Republik Magazin"), so per-feed yield is counted by the
            # article URL's domain instead. Matching on the name showed 0 kept
            # for feeds that were plainly producing.
            by_domain = {r[0]: {"articles": int(r[1]), "approved": int(r[2])} for r in conn.execute(text("""
                SELECT regexp_replace(regexp_replace(COALESCE(NULLIF(url, ''), uri),
                                                     '^https?://(www\\.)?', ''), '/.*$', '') AS domain,
                       COUNT(*), COUNT(*) FILTER (WHERE ingest_status = 'approved')
                FROM articles WHERE topic = :topic GROUP BY 1
            """), {"topic": self.topic}).fetchall()}
            tiers = {r[0]: r[1] for r in conn.execute(text(
                "SELECT domain, tier FROM sd_sources")).fetchall()}
            tiers_named = {r[0]: r[1] for r in conn.execute(text(
                "SELECT domain, name FROM sd_sources WHERE name IS NOT NULL")).fetchall()}
            schedules = conn.execute(text("""
                SELECT name, schedule_enabled, schedule_type, schedule_interval, schedule_unit,
                       model, batch_size, last_run_at, next_run_at, last_run_status, run_count
                FROM sd_schedules WHERE topic = :topic ORDER BY id
            """), {"topic": self.topic}).fetchall()
            tenant = conn.execute(text(
                "SELECT min_relevance_threshold, search_fields, default_llm_model, language "
                "FROM keyword_monitor_settings LIMIT 1")).fetchone()
            counts = conn.execute(text("""
                SELECT COUNT(*) AS collected,
                       COUNT(*) FILTER (WHERE ingest_status = 'approved') AS approved,
                       COUNT(*) FILTER (WHERE ingest_status = 'filtered_relevance') AS rejected,
                       COUNT(*) FILTER (WHERE ingest_status = 'social_evaluated') AS social,
                       COUNT(*) FILTER (WHERE ingest_status = 'social_evaluated'
                                        AND topic_alignment_score >= :sm) AS social_kept,
                       COUNT(*) FILTER (WHERE ingest_status IS NULL) AS unscored,
                       MAX(submission_date) AS last_collected
                FROM articles WHERE topic = :topic
            """), {"topic": self.topic, "sm": SOCIAL_MIN_ALIGNMENT}).fetchone()
            ext = conn.execute(text("""
                SELECT COUNT(*) AS analysed, COUNT(*) FILTER (WHERE error IS NOT NULL) AS failed,
                       MAX(extracted_at) AS last_analysed
                FROM sd_extractions WHERE topic = :topic
            """), {"topic": self.topic}).fetchone()
            nar = conn.execute(text("""
                SELECT COUNT(*) AS narratives, COALESCE(SUM(article_count), 0) AS narrative_articles
                FROM sd_narratives WHERE topic = :topic
            """), {"topic": self.topic}).fetchone()
        finally:
            conn.close()

        def _kind(providers: Optional[str], social: Optional[str]) -> str:
            provs = []
            try:
                provs = json.loads(providers) if isinstance(providers, str) else (providers or [])
            except (json.JSONDecodeError, TypeError):
                provs = []
            if any(p in ("bluesky", "reddit", "xpoz", "telegram") for p in provs):
                return "social"
            return "news"

        # The social collectors store their platform in news_source, so they
        # group as "xpoz:twitter" unless they are given a readable name.
        platform_names = {"bluesky": "Bluesky", "bsky": "Bluesky", "telegram": "Telegram",
                          "reddit": "Reddit", "xpoz:twitter": "X (via xpoz)",
                          "xpoz:reddit": "Reddit (via xpoz)", "xpoz:bluesky": "Bluesky (via xpoz)"}
        sc = scope(self.topic)
        # TELEGRAM_CHANNELS is tenant-wide, so only list it where this watch
        # actually runs a telegram group — otherwise the Swiss channels show
        # up under every scope.
        uses_telegram = any("telegram" in (g.providers or "") for g in groups)
        telegram_channels = [c.strip().lstrip("@") for c in
                             os.getenv("TELEGRAM_CHANNELS", "").split(",")
                             if c.strip()] if uses_telegram else []

        # Every name in litellm_config.yaml is an alias, and most of them read
        # like an OpenAI model while calling something else entirely. Showing
        # only the alias here told the reader we run on OpenAI, which we do not,
        # so each stage carries the concrete provider and model it invokes.
        from app.ai_models import resolve_model_identity
        from app.vector_store_pgvector import DEBERTA_ENCODER_URL
        extraction_alias = next((r.model for r in schedules if r.model), DEFAULT_MODEL)
        def _m(stage: str, alias: str, note: str = "") -> Dict[str, str]:
            return {"stage": stage, "alias": alias,
                    "runs": resolve_model_identity(alias) or alias, "note": note}
        models = [
            _m("Relevance gate", os.getenv("RELEVANCE_MODEL", "bedrock-kimi-k2-5"),
               "scores every article against this watch's description"),
            _m("Social relevance", os.getenv("SOCIAL_EVAL_MODEL", "").strip('"') or "bedrock-claude-haiku",
               "scores Bluesky and Telegram posts, which never reach the news gate"),
            _m("Article analysis", (tenant[2] if tenant else "") or DEFAULT_MODEL,
               "category, sentiment and tags, shared with the rest of the platform"),
            _m("Extraction", extraction_alias,
               "the storylines, stance, targets, technique and attribution on this board"),
            {"stage": "Storyline matching", "alias": "DeBERTa encoder (local)",
             "runs": f"{DEBERTA_ENCODER_URL} · 768 dimensions",
             "note": "shortlists candidates by meaning; the extraction model decides the merge"},
            _m("Weekly brief", BRIEF_MODEL, "writes the brief from this board's data only"),
        ]
        return {
            "topic": self.topic,
            "label": sc["label"],
            "blurb": sc["blurb"],
            "keyword_groups": [{
                "id": g.id, "name": g.name, "language": g.language,
                "providers": g.providers, "kind": _kind(g.providers, g.social_platforms),
                "is_active": g.is_active, "keywords": list(g.keywords or []),
                "threshold": g.min_relevance_threshold,
                "last_checked": g.last_checked_at.isoformat() if g.last_checked_at else None,
            } for g in groups],
            "feeds": [{
                "id": f.id, "name": f.name, "url": f.url, "is_active": f.is_active,
                "tier": f.tier, "language": f.language,
                "threshold": f.relevance_threshold, "fetched": f.articles_fetched,
                "last_checked": f.last_checked_at.isoformat() if f.last_checked_at else None,
                "error": f.last_error,
                "produced": by_domain.get(_feed_domain(f.url)) or {"articles": 0, "approved": 0},
            } for f in feeds],
            "telegram_channels": [{"channel": c, "url": f"https://t.me/s/{c}",
                                   "tier": tiers.get(f"t.me/{c}", "unknown")}
                                  for c in telegram_channels],
            "produced_by_source": [
                {"source": k, "name": (platform_names.get(k) or tiers_named.get(k)
                                       or v.get("label") or k),
                 "articles": v["articles"], "approved": v["approved"]}
                for k, v in sorted(produced.items(), key=lambda kv: -kv[1]["articles"])[:40]],
            "schedules": [{
                "name": r.name, "enabled": r.schedule_enabled,
                "every": f"{r.schedule_interval} {r.schedule_unit}" if r.schedule_type == "interval" else r.schedule_type,
                "model": r.model, "batch_size": r.batch_size, "runs": r.run_count,
                "last_run": r.last_run_at.isoformat() if r.last_run_at else None,
                "next_run": r.next_run_at.isoformat() if r.next_run_at else None,
                "status": r.last_run_status,
            } for r in schedules],
            "collection": {
                "collected": int(counts.collected or 0),
                "approved": int(counts.approved or 0),
                "rejected": int(counts.rejected or 0),
                "social": int(counts.social or 0),
                "social_kept": int(counts.social_kept or 0),
                "unscored": int(counts.unscored or 0),
                "analysed": int(ext.analysed or 0),
                "analysis_failed": int(ext.failed or 0),
                "narratives": int(nar.narratives or 0),
                "narrative_articles": int(nar.narrative_articles or 0),
                "last_collected": counts.last_collected,
                "last_analysed": ext.last_analysed.isoformat() if ext.last_analysed else None,
            },
            "models": models,
            "settings": {
                "relevance_threshold": tenant[0] if tenant else None,
                "search_fields": tenant[1] if tenant else None,
                "extraction_model": extraction_alias,
                "brief_model": BRIEF_MODEL,
                "social_min_alignment": SOCIAL_MIN_ALIGNMENT,
                "narrative_shortlist_floor": NARRATIVE_MATCH_THRESHOLD,
                "stances": list(STANCES), "tiers": list(TIERS),
                "techniques": list(TECHNIQUES), "attributions": list(ATTRIBUTIONS),
            },
        }

    # ------------------------------------------------------- target registry
    _TARGET_CACHE: Dict[str, Tuple[float, Dict[str, Tuple[str, str]]]] = {}
    _TARGET_TTL = 120.0

    def _target_aliases(self) -> Dict[str, Tuple[str, str]]:
        """lower(name or alias) -> (type, canonical name), from sd_targets.

        The model writes a target's name freely, so the same ballot item arrived
        as "Neutrality initiative", "Neutrality Initiative", "Neutrality
        initiative referendum" and "Sauvegarder la neutralite suisse initiative",
        and the Targets list showed four rows. Resolution is by name alone, which
        also settles the type: the same initiative came back as a vote in most
        articles and a policy in six.
        """
        import time
        hit = self._TARGET_CACHE.get(self.topic)
        if hit and time.time() - hit[0] < self._TARGET_TTL:
            return hit[1]
        conn = self._conn()
        try:
            rows = conn.execute(text("SELECT type, name, aliases FROM sd_targets")).fetchall()
        finally:
            conn.close()
        out: Dict[str, Tuple[str, str]] = {}
        for ttype, name, aliases in rows:
            out[name.strip().lower()] = (ttype, name)
            for a in (aliases or []):
                key = str(a).strip().lower()
                if key and key not in out:
                    out[key] = (ttype, name)
        self._TARGET_CACHE[self.topic] = (time.time(), out)
        return out

    def canonical_targets(self, targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fold each target onto its registered name, dropping what that makes
        into a duplicate within the same article."""
        amap = self._target_aliases()
        out: List[Dict[str, Any]] = []
        seen = set()
        for t in targets or []:
            name = str(t.get("name") or "").strip()
            ttype = str(t.get("type") or "").strip().lower()
            if not name:
                continue
            resolved = amap.get(name.lower())
            if resolved:
                ttype, name = resolved
            key = (ttype, name.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"type": ttype, "name": name})
        return out

    def known_target_names(self, limit: int = 60) -> List[str]:
        """The registry's canonical names, for the extraction prompt."""
        conn = self._conn()
        try:
            rows = conn.execute(text(
                "SELECT type, name FROM sd_targets ORDER BY seeded DESC, type, name LIMIT :l"
            ), {"l": limit}).fetchall()
        finally:
            conn.close()
        return [f"{name} ({ttype})" for ttype, name in rows]

    # ---------------------------------------------------------------- legend
    @staticmethod
    def glossary() -> Dict[str, Any]:
        """What each label means and when the model is told to apply it. The
        same text goes into the extraction prompt, so the legend on screen is
        the instruction that produced the labels, not a description of it."""
        return {
            "techniques": TECHNIQUE_GLOSSARY, "targets": TARGET_GLOSSARY,
            "attributions": ATTRIBUTION_GLOSSARY, "tiers": TIER_GLOSSARY,
            "stances": STANCE_GLOSSARY,
        }

    # ------------------------------------------------------------- flow graph
    def flow(self, days_back: int = 30) -> Dict[str, Any]:
        """How collection relates to what comes out.

        Every article of this watch is placed on four axes: the channel that
        found it, the language it is written in, the tier of the outlet that
        published it, and what the analysis made of it. Returned as nodes and
        links so the tab can draw it as a flow. Each article is counted once
        per stage, so all four stages sum to the same total.
        """
        conn = self._conn()
        try:
            rows = conn.execute(text("""
                WITH arts AS (
                    SELECT a.uri, a.ingest_status, a.topic_alignment_score,
                           regexp_replace(regexp_replace(COALESCE(NULLIF(a.url, ''), a.uri),
                                          '^https?://(www\\.)?', ''), '/.*$', '') AS domain
                    FROM articles a
                    WHERE a.topic = :topic AND a.submission_date >= :s
                ), chan AS (
                    SELECT DISTINCT ON (m.article_uri)
                           m.article_uri, g.name AS gname, g.language AS glang, g.providers
                    FROM keyword_article_matches m JOIN keyword_groups g ON g.id = m.group_id
                    WHERE g.topic = :topic
                    ORDER BY m.article_uri, g.id
                )
                SELECT a.uri, a.ingest_status, a.topic_alignment_score,
                       c.gname, c.glang, c.providers,
                       e.language AS elang, e.source_tier,
                       s.tier AS stier, s.language AS slang,
                       EXISTS (SELECT 1 FROM sd_narrative_articles na
                               WHERE na.article_uri = a.uri AND na.topic = :topic) AS in_narrative,
                       (e.article_uri IS NOT NULL) AS analysed
                FROM arts a
                LEFT JOIN chan c ON c.article_uri = a.uri
                LEFT JOIN sd_extractions e ON e.article_uri = a.uri AND e.topic = :topic
                LEFT JOIN sd_sources s ON s.domain = a.domain
            """), {"topic": self.topic, "s": self._since(days_back)}).fetchall()
        finally:
            conn.close()

        links: Dict[Tuple[str, str], int] = {}
        totals: Dict[str, int] = {}
        for r in rows:
            provs = (r.providers or "").lower()
            if r.gname is None:
                channel = "RSS feeds"
            elif "telegram" in provs:
                channel = "Telegram"
            elif any(p in provs for p in ("bluesky", "bsky", "reddit", "xpoz")):
                channel = "Bluesky"
            else:
                channel = "Keywords %s" % (r.glang or "en").upper()
            lang = (r.elang or r.glang or r.slang or "").lower()
            lang = lang.upper() if lang in LANGUAGES else "Language unknown"
            tier = (r.source_tier or r.stier or "unknown").replace("_", " ")
            if r.in_narrative:
                outcome = "In a storyline"
            elif r.analysed:
                outcome = "Analysed, no storyline"
            elif r.ingest_status == "approved" or (
                    r.ingest_status == "social_evaluated"
                    and (r.topic_alignment_score or 0) >= SOCIAL_MIN_ALIGNMENT):
                outcome = "Waiting to be analysed"
            elif r.ingest_status is None:
                # Collected but the relevance gate never ran on it. Folding these
                # into "below the line" would hide a collection fault as a
                # judgement, so they get their own bucket.
                outcome = "Never scored"
            elif r.ingest_status == "enrichment_failed":
                outcome = "Analysis failed"
            else:
                outcome = "Below the relevance line"
            path = ["0:" + channel, "1:" + lang, "2:" + tier, "3:" + outcome]
            for key in path:
                totals[key] = totals.get(key, 0) + 1
            for a, b in zip(path, path[1:]):
                links[(a, b)] = links.get((a, b), 0) + 1

        nodes = [{"key": k, "stage": int(k.split(":", 1)[0]), "name": k.split(":", 1)[1], "value": v}
                 for k, v in totals.items()]
        nodes.sort(key=lambda n: (n["stage"], -n["value"], n["name"]))
        return {
            "stages": ["Channel", "Language", "Outlet type", "Outcome"],
            "total": len(rows), "days_back": days_back, "nodes": nodes,
            "links": [{"source": a, "target": b, "value": v}
                      for (a, b), v in sorted(links.items(), key=lambda kv: -kv[1])],
        }

    # ---------------------------------------------------- calendar and alerts
    def ensure_calendar(self) -> int:
        """Seed the vote dates as topic mementos (idempotent)."""
        from app.services.timeline_events import upsert_event
        conn = self._conn()
        created = 0
        try:
            for d, label in scope(self.topic)["calendar"]:
                res = upsert_event(conn, "topic", self.topic, {
                    "event_type": "calendar", "event_subtype": "federal_vote",
                    "title": label, "description": "Swiss federal vote date",
                    "significance": "high", "article_count": 0, "granularity": "daily",
                }, d, dated_hash=True)
                created += int(res == "created")
            conn.commit()
            return created
        finally:
            conn.close()

    def evaluate_alerts(self) -> List[Dict[str, Any]]:
        """Four rules, each becomes a topic memento plus a bell notification."""
        from app.services.timeline_events import upsert_event
        db = get_database_instance()
        conn = db._temp_get_connection()
        alerts: List[Dict[str, Any]] = []
        today = date.today()
        try:
            # 1. New narrative with two or more outlets within 48 hours of first sight.
            for r in conn.execute(text("""
                SELECT n.id, n.name, COUNT(DISTINCT na.source_domain) AS outlets
                FROM sd_narratives n JOIN sd_narrative_articles na ON na.narrative_id = n.id
                WHERE n.first_seen >= CURRENT_DATE - 2 AND n.topic = :topic
                GROUP BY n.id HAVING COUNT(DISTINCT na.source_domain) >= 2
            """), {"topic": self.topic}).fetchall():
                alerts.append({"event_type": "alert", "event_subtype": "new_narrative_multi_outlet",
                               "title": f"New narrative carried by {r.outlets} outlets: {r.name}",
                               "significance": "high", "narrative_id": r.id})
            # 2. 7-day volume more than three times the previous 7 days, minimum five.
            for r in conn.execute(text("""
                SELECT n.id, n.name,
                       COUNT(*) FILTER (WHERE na.article_date >= CURRENT_DATE - 7) AS cur,
                       COUNT(*) FILTER (WHERE na.article_date >= CURRENT_DATE - 14 AND na.article_date < CURRENT_DATE - 7) AS prev
                FROM sd_narratives n JOIN sd_narrative_articles na ON na.narrative_id = n.id
                WHERE n.topic = :topic
                GROUP BY n.id
                HAVING COUNT(*) FILTER (WHERE na.article_date >= CURRENT_DATE - 7) >= 5
                   AND COUNT(*) FILTER (WHERE na.article_date >= CURRENT_DATE - 7)
                       > 3 * GREATEST(1, COUNT(*) FILTER (WHERE na.article_date >= CURRENT_DATE - 14 AND na.article_date < CURRENT_DATE - 7))
            """), {"topic": self.topic}).fetchall():
                alerts.append({"event_type": "alert", "event_subtype": "volume_spike",
                               "title": f"Narrative volume spike ({r.cur} vs {r.prev}): {r.name}",
                               "significance": "high", "narrative_id": r.id})
            # 3. Crossed into a second language: the new language's first sighting is
            #    today or yesterday AND strictly later than the narrative's earliest
            #    sighting in another language. A backfill that lands DE and FR on the
            #    same day is not a crossing.
            for r in conn.execute(text("""
                WITH firsts AS (
                    SELECT narrative_id, language, MIN(article_date) AS first_day
                    FROM sd_narrative_articles WHERE language IS NOT NULL AND topic = :topic
                    GROUP BY narrative_id, language
                )
                SELECT n.id, n.name, f.language
                FROM firsts f JOIN sd_narratives n ON n.id = f.narrative_id
                WHERE f.first_day >= CURRENT_DATE - 1
                  AND f.first_day > (SELECT MIN(first_day) FROM firsts f2
                                     WHERE f2.narrative_id = f.narrative_id AND f2.language <> f.language)
            """), {"topic": self.topic}).fetchall():
                alerts.append({"event_type": "alert", "event_subtype": "language_crossing",
                               "title": f"Narrative crossed into {r.language.upper()}: {r.name}",
                               "significance": "medium", "narrative_id": r.id})
            # 4. Deepfake or synthetic text aimed at a named person.
            for r in conn.execute(text("""
                SELECT e.article_uri, a.title FROM sd_extractions e JOIN articles a ON a.uri = e.article_uri
                WHERE e.article_date >= CURRENT_DATE - 1 AND e.topic = :topic
                  AND (e.techniques && ARRAY['deepfake','synthetic_text']::varchar[])
                  AND EXISTS (SELECT 1 FROM jsonb_array_elements(e.targets) t WHERE t->>'type' = 'person')
            """), {"topic": self.topic}).fetchall():
                alerts.append({"event_type": "alert", "event_subtype": "synthetic_media_person",
                               "title": f"Synthetic media aimed at a person: {r.title[:120]}",
                               "significance": "high", "article_uris": [r.article_uri]})
            created = []
            for a in alerts:
                res = upsert_event(conn, "topic", self.topic, {
                    "event_type": a["event_type"], "event_subtype": a["event_subtype"],
                    "title": a["title"], "description": "",
                    "significance": a["significance"],
                    "event_data": {"narrative_id": a.get("narrative_id")},
                    "article_uris": a.get("article_uris") or [], "article_count": 1,
                }, today, dated_hash=False)
                if res == "created":
                    created.append(a)
            conn.commit()
            for a in created:
                try:
                    db.facade.create_notification(username=None, type="swiss_disinfo",
                                                  title=scope(self.topic)["label"], message=a["title"],
                                                  link="/explore?tab=swiss_disinfo")
                except Exception as e:
                    logger.warning("Swiss disinfo notification failed: %s", e)
            return created
        finally:
            conn.close()


_services: Dict[str, SwissDisinfoService] = {}


def get_swiss_disinfo_service(topic: str = DEFAULT_TOPIC) -> SwissDisinfoService:
    """One service per scope. An unknown topic falls back to the Swiss scope
    rather than silently creating an empty watch."""
    if topic not in SCOPES:
        topic = DEFAULT_TOPIC
    if topic not in _services:
        _services[topic] = SwissDisinfoService(topic)
    return _services[topic]


def list_scopes() -> List[Dict[str, str]]:
    return [{"topic": t, "label": v["label"], "blurb": v["blurb"]} for t, v in SCOPES.items()]
