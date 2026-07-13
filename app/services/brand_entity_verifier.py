"""Verify LLM-suggested brand executives and firms against Wikidata.

Used by the Brand Watcher /suggest-keywords endpoint. Given the parsed LLM
suggestion payload, this module:

1. Resolves the brand name to a Wikidata QID (or uses a user-confirmed QID).
2. Pulls authoritative people (P169 CEO / P112 founder / P488 chair — current
   only, ex-officeholders filtered via the P582 end-time qualifier) and
   related orgs (P749 parent / P127 owner / P1830 owned).
3. Cross-checks each LLM-suggested person/competitor against Wikidata,
   attaching per-item provenance (verified flag + QID + source).

Verification is best-effort: any failure or timeout degrades to
``{"available": False}`` — callers must still return the LLM suggestions.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import date
from typing import Optional

from app.services.wikidata_client import WikidataClient, WikidataEntity

logger = logging.getLogger(__name__)

# person-role properties on the brand entity
_PEOPLE_PROPS = {"P169": "CEO", "P112": "founder", "P488": "chairperson"}
# org-relation properties on the brand entity
_ORG_PROPS = {"P749": "parent", "P127": "owner", "P1830": "subsidiary"}

_ORG_DESCRIPTION_HINTS = (
    "company", "corporation", "business", "enterprise", "conglomerate",
    "manufacturer", "publisher", "publishing", "brand", "bank", "retailer",
    "organization", "organisation", "firm", "airline", "automaker", "chain",
    "producer", "provider", "developer", "operator", "group", "holding",
    "software", "technology", "media", "label", "studio", "platform",
)

_PERSONISH_DESCRIPTION_HINTS = (
    "singer", "rapper", "musician", "actor", "actress", "footballer",
    "politician", "writer", "author", "artist", "player", "born",
)


def _norm(name: str) -> str:
    """Normalize a name for matching: casefold, strip diacritics and
    punctuation ("McGraw-Hill" == "McGraw Hill"), collapse whitespace."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    depunct = "".join(c if c.isalnum() else " " for c in stripped)
    return " ".join(depunct.casefold().split())


def _looks_like_org(description: Optional[str]) -> bool:
    if not description:
        return False
    d = description.casefold()
    return any(h in d for h in _ORG_DESCRIPTION_HINTS)


def _looks_like_person(description: Optional[str]) -> bool:
    if not description:
        return False
    d = description.casefold()
    return any(h in d for h in _PERSONISH_DESCRIPTION_HINTS)


async def verify_suggestions(
    brand_name: str,
    llm_result: dict,
    qid: Optional[str] = None,
    max_competitor_lookups: int = 12,
    budget_seconds: float = 15.0,
) -> dict:
    """Cross-check LLM brand suggestions against Wikidata.

    Returns the ``verification`` block for the suggest-keywords response.
    Never raises — degrades to ``{"available": False}``.
    """
    try:
        return await asyncio.wait_for(
            _verify(brand_name, llm_result, qid, max_competitor_lookups),
            timeout=budget_seconds,
        )
    except Exception as e:
        logger.warning("Brand entity verification unavailable for %r: %s", brand_name, e)
        return {"available": False}


async def _verify(
    brand_name: str,
    llm_result: dict,
    qid: Optional[str],
    max_competitor_lookups: int,
) -> dict:
    async with WikidataClient() as wd:
        # ── 1. Brand resolution ─────────────────────────────────────────────
        candidates: list[dict] = []
        brand_qid = qid
        matched = bool(qid)

        if not brand_qid:
            hits = await wd.search(brand_name, limit=8)
            candidates = [
                {"qid": h["qid"], "label": h["label"], "description": h.get("description")}
                for h in hits
            ]
            target = _norm(brand_name)
            for h in hits:
                names = [h.get("label", "")] + list(h.get("aliases") or [])
                if any(_norm(n) == target for n in names) and not _looks_like_person(h.get("description")):
                    brand_qid = h["qid"]
                    matched = True
                    break

        brand_entity: Optional[WikidataEntity] = None
        if brand_qid:
            brand_entity = await wd.get_entity(brand_qid)

        brand_block = {
            "qid": brand_qid,
            "label": brand_entity.label if brand_entity else None,
            "description": brand_entity.description if brand_entity else None,
            "matched": matched and brand_entity is not None,
            "candidates": candidates,
        }

        people: list[dict] = []
        competitors: list[dict] = []

        if brand_entity:
            # ── 2. Collect person/org QIDs from claims ──────────────────────
            person_refs: list[tuple[str, str]] = []  # (qid, role)
            org_refs: list[tuple[str, str]] = []     # (qid, relation)
            for pid, role in _PEOPLE_PROPS.items():
                for claim in brand_entity.claims.get(pid, []):
                    # P582 end-time qualifier ⇒ former officeholder
                    if pid == "P169" and claim.qualifiers.get("P582"):
                        continue
                    if isinstance(claim.value, str) and claim.value.startswith("Q"):
                        person_refs.append((claim.value, role))
            for pid, relation in _ORG_PROPS.items():
                for claim in brand_entity.claims.get(pid, [])[:5]:
                    if isinstance(claim.value, str) and claim.value.startswith("Q"):
                        org_refs.append((claim.value, relation))

            # ── 3. Resolve QIDs → labels in one batch ───────────────────────
            ref_qids = list(dict.fromkeys([q for q, _ in person_refs] + [q for q, _ in org_refs]))
            entities = await wd.get_entities_batch(ref_qids) if ref_qids else {}

            # ── 4. People merge ─────────────────────────────────────────────
            wd_people: dict[str, dict] = {}  # normalized name -> entry
            for pqid, role in person_refs:
                ent = entities.get(pqid)
                if not ent:
                    continue
                key = _norm(ent.label)
                if key in wd_people:
                    if role not in wd_people[key]["role"].split("/"):
                        wd_people[key]["role"] += f"/{role}"
                    continue
                wd_people[key] = {
                    "name": ent.label,
                    "role": role,
                    "qid": pqid,
                    "verified": True,
                    "source": "wikidata",
                    "_aliases": {_norm(a) for a in ent.aliases},
                }

            llm_people = [p for p in (llm_result.get("people_keywords") or []) if isinstance(p, str)]
            matched_wd_keys: set[str] = set()
            for name in llm_people:
                key = _norm(name)
                hit = wd_people.get(key)
                if hit is None:
                    hit = next((v for v in wd_people.values() if key in v["_aliases"]), None)
                if hit is not None:
                    matched_wd_keys.add(_norm(hit["name"]))
                    people.append({
                        "name": name,
                        "role": hit["role"],
                        "qid": hit["qid"],
                        "verified": True,
                        "source": "both",
                    })
                else:
                    people.append({"name": name, "verified": False, "source": "llm"})
            for key, entry in wd_people.items():
                if key not in matched_wd_keys:
                    people.append({k: v for k, v in entry.items() if not k.startswith("_")})

            # ── 5. Firms: related orgs from claims ──────────────────────────
            for oqid, relation in org_refs:
                ent = entities.get(oqid)
                if not ent:
                    continue
                competitors.append({
                    "name": ent.label,
                    "qid": oqid,
                    "description": ent.description,
                    "verified": True,
                    "source": "wikidata",
                    "relation": relation,
                })

        # ── 5b. Competitor existence checks (works even without brand match) ─
        llm_competitors = [c for c in (llm_result.get("competitor_keywords") or []) if isinstance(c, str)]
        seen_comp = {_norm(c["name"]) for c in competitors}
        for name in llm_competitors:
            if _norm(name) in seen_comp:
                continue
            entry: dict = {"name": name, "verified": False, "source": "llm"}
            if max_competitor_lookups > 0:
                max_competitor_lookups -= 1
                hits = await wd.search(name, limit=3)
                target = _norm(name)
                for h in hits:
                    names = [h.get("label", "")] + list(h.get("aliases") or [])
                    if any(_norm(n) == target for n in names) and _looks_like_org(h.get("description")):
                        entry.update({
                            "qid": h["qid"],
                            "description": h.get("description"),
                            "verified": True,
                            "source": "both",
                        })
                        break
            competitors.append(entry)

        return {
            "available": True,
            "retrieved_at": date.today().isoformat(),
            "brand": brand_block,
            "people": people,
            "competitors": competitors,
        }
