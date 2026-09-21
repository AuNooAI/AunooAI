"""Shadow for account-to-company resolution, with the TypeSafe Jev model.

``entity_identity.py`` will only confirm that an account belongs to a company
on hard evidence: a stable platform id, a link from a domain already verified
as the company's, or a person saying so. A name resemblance may propose a
mapping and can never confirm one. That rule is right, and it is why 1,294
accounts on this site sit unmapped: nothing proposes for them at all.

This shadow fills that gap on paper before it fills it in production. Code
picks a shortlist of companies whose names or keywords could plausibly match
the account, and Jev answers, over that shortlist only: which company owns
this account, is it a company account at all rather than a person, a
community or a parody, and is the only thing linking it to the chosen company
a resemblance between names. That last question is the doctrine of the module
above, asked as a typed question.

Rows land in ``entity_identity_shadow``. Nothing reads them.
``bw_entity_social_identities`` is not written to and no mapping is proposed.

Env:
    TYPESAFE_SHADOW_IDENTITY        "1" to enable (needs TYPESAFE_API_KEY)
    TYPESAFE_SHADOW_IDENTITY_MAX    accounts judged per batch (default 100)
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

USE_CASE = "services.entity_identity_shadow:resolve"
MAX_CANDIDATES = 8          # how many companies Jev may choose between
NONE_KEY = "none"

# Measured on the first batch of 61 accounts (2026-09-21), and not used by
# anything yet. A future decide() would queue an account for a curator when
# the action is propose_owned, its confidence clears ACTION_MIN, and the
# account reads as a company at all. The second test is what matters: on its
# own the action confidence queued dropzone-gaming.bsky.social under the
# vendor Dropzone AI at 0.84, and company_account caught it at 0.53.
QUEUE_ACTION_MIN = 0.4
QUEUE_COMPANY_MIN = 0.55


def enabled() -> bool:
    from app.services import typesafe_client
    return (os.getenv("TYPESAFE_SHADOW_IDENTITY", "false").lower() in {"1", "true", "yes"}
            and typesafe_client.is_configured())


# ---------------------------------------------------------------------------
# Shortlist: code decides what Jev is allowed to choose between
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Words that carry no identity on their own, so a match on one of them is noise.
_STOP = frozenset({"ai", "io", "inc", "ltd", "llc", "corp", "co", "the", "app",
                   "security", "secure", "cyber", "labs", "lab", "tech", "hq",
                   "software", "systems", "group", "platform", "cloud", "data",
                   "com", "net", "org", "www", "official", "team", "global"})


def _norm(s: Optional[str]) -> str:
    return _NON_ALNUM.sub("", (s or "").lower())


def _tokens(s: Optional[str]) -> List[str]:
    return [t for t in _NON_ALNUM.sub(" ", (s or "").lower()).split() if t]


def _significant(s: Optional[str]) -> List[str]:
    return [t for t in _tokens(s) if t not in _STOP and len(t) > 2]


def _brand_names(brand: Dict[str, Any]) -> List[str]:
    """Every string that could stand for this company in a handle."""
    out = [brand.get("display_name") or "", brand.get("name") or ""]
    kw = brand.get("brand_keywords")
    if isinstance(kw, list):
        out.extend(str(k) for k in kw[:12])
    return [s for s in out if s]


def shortlist(account: Dict[str, Any], brands: List[Dict[str, Any]],
              limit: int = MAX_CANDIDATES) -> Tuple[List[Dict[str, Any]], Optional[int], bool]:
    """Companies whose name could plausibly be this account, best first.

    Returns ``(candidates, name_match_brand_id, exact)`` where the second value
    is what a plain name-match proposer would have picked: the single company
    whose name matches the handle or display name outright.
    """
    acct_norm = {_norm(account.get("handle")), _norm(account.get("display_name"))}
    acct_norm.discard("")
    acct_tokens = set(_significant(account.get("handle")) + _significant(account.get("display_name")))
    # The bio is weaker evidence than the handle, and it is where the cases
    # that most need judging live: a person naming their employer, a community
    # named after a product, an account that only talks about a company.
    bio_norm = _norm(account.get("bio"))
    scored: List[Tuple[float, bool, Dict[str, Any]]] = []
    for b in brands:
        best, exact = 0.0, False
        for nm in _brand_names(b):
            n = _norm(nm)
            if not n or len(n) < 3:
                continue
            if n in acct_norm:                      # handle *is* the company name
                best, exact = max(best, 1.0), True
            elif any(n in a or a in n for a in acct_norm if len(a) >= 3):
                best = max(best, 0.7)               # contained one way or the other
            sig = set(_significant(nm))
            # A shared word only counts if it is long enough to be a name in
            # its own right; otherwise every ".com" handle matches every
            # ".com" company.
            if sig and sig <= acct_tokens and any(len(t) >= 4 for t in sig):
                best = max(best, 0.6 if not exact else best)
            elif len(n) >= 5 and n in bio_norm:     # named in the bio only
                best = max(best, 0.3)
        if best > 0:
            scored.append((best, exact, b))
    scored.sort(key=lambda t: (-t[0], (t[2].get("display_name") or "")))
    cands = [b for _, _, b in scored[:limit]]
    exacts = [b for sc, ex, b in scored if ex]
    name_match = int(exacts[0]["id"]) if len(exacts) == 1 else None
    return cands, name_match, bool(exacts)


# ---------------------------------------------------------------------------
# The questions
# ---------------------------------------------------------------------------

def _questions(candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    criteria: Dict[str, Optional[str]] = {}
    for b in candidates:
        label = b.get("display_name") or b.get("name") or str(b.get("id"))
        descr = (b.get("description") or "").strip()
        criteria[str(b["id"])] = f"{label}" + (f" — {descr[:160]}" if descr else "")
    criteria[NONE_KEY] = ("No company in the list owns this account: it belongs to someone else, "
                          "to a company not listed, or to no company at all")
    return {
        "owner": {
            "type": "choice",
            "instructions": ("Which company in `candidates` runs `account` as its own official account? "
                             "Judge from the display name, the bio and the linked site together, not from "
                             "the handle alone. Choose none unless the account clearly belongs to that company."),
            "criteria": criteria,
        },
        "company_account": {
            "type": "noul",
            "instructions": "Is `account` an organisation's own account, posting as the organisation?",
            "criteria": {"true": "The account speaks as a company, product or team",
                         "false": "It is a person, a community, a news outlet, a job board, a fan or parody account"},
        },
        "person": {
            "type": "noul",
            "instructions": "Does `account` belong to a named individual rather than an organisation?",
            "criteria": {"true": "A person's own account, even when they name their employer in the bio",
                         "false": "Not an individual's account"},
        },
        "community": {
            "type": "noul",
            "instructions": ("Is `account` a community, forum, user group or fan account about a company or "
                             "its products, rather than an account the company runs?"),
            "criteria": {"true": "Readers or users gather here; the company does not speak through it",
                         "false": "Not a community account"},
        },
        "name_only": {
            "type": "noul",
            "instructions": ("Take the company chosen in `owner`. Is a resemblance between the names the only "
                             "thing linking them? Read the bio and the linked site: a matching product name, "
                             "a matching site, or the company describing itself counts as more than a name."),
            "criteria": {"true": "Nothing but the name matches, or no company was chosen",
                         "false": "The bio, the linked site or the described business confirms the company"},
        },
        "impersonation": {
            "type": "noul",
            "instructions": "Does `account` look like a parody, impersonation, squatted handle or fake of a company?",
            "criteria": {"true": "It presents as a company it is probably not, or the handle looks squatted",
                         "false": "No sign of impersonation"},
        },
        "action": {
            "type": "choice",
            "instructions": ("What should a curator do with `account`? This is a softer call than `owner`: "
                             "a queued proposal is read by a person before anything is recorded, so a likely "
                             "match is worth queueing even when it is not certain."),
            "criteria": {
                "propose_owned": "Queue it as probably the chosen company's own account, for a person to confirm",
                "propose_community": "Queue it as a community, forum or fan account about the company",
                "propose_person": "Queue it as an individual's account, possibly someone who works there",
                "leave": "Leave it unmapped: no company in the list is plausibly connected to it",
            },
        },
    }


def has_evidence(account: Dict[str, Any]) -> bool:
    """Does this account carry anything a person could check, beyond its name?"""
    return any(str(account.get(k) or "").strip()
               for k in ("bio", "profile_url", "summary", "brand_context"))


def _state(account: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "account": {
            "platform": str(account.get("platform") or ""),
            "handle": str(account.get("handle") or ""),
            "display_name": str(account.get("display_name") or ""),
            "bio": str(account.get("bio") or "")[:600],
            "linked_site": str(account.get("profile_url") or "")[:200],
            "platform_verified": bool(account.get("verified")),
            "profile_notes": str(account.get("summary") or "")[:500],
            "followers": int(account.get("followers_count") or 0),
            "posts": int(account.get("posts_count") or 0),
        },
        "candidates": [{
            "id": str(b["id"]),
            "name": b.get("display_name") or b.get("name") or "",
            "description": (b.get("description") or "")[:200],
            "known_names": _brand_names(b)[:6],
        } for b in candidates],
    }


def resolve(account: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ask Jev who owns this account. Never raises; returns a row fragment."""
    from app.services import typesafe_client
    started = time.monotonic()
    out = typesafe_client.system_one(_state(account, candidates), _questions(candidates),
                                     use_case=USE_CASE, timeout_s=20.0)
    latency_ms = int((time.monotonic() - started) * 1000)
    if not out:
        return {"jev_error": "no response", "jev_latency_ms": latency_ms}
    try:
        a = out["answers"]
        owner = a["owner"]
        choice = owner.get("choice")
        brand_id = None if choice in (None, NONE_KEY) else int(choice)
        action = a["action"]
        return {
            "jev_owner_brand_id": brand_id,
            "jev_owner_confidence": float(owner.get("confidence") or 0.0),
            "jev_action": action.get("choice"),
            "jev_action_confidence": float(action.get("confidence") or 0.0),
            "jev_company_account": float(a["company_account"]["noul"]),
            "jev_person": float(a["person"]["noul"]),
            "jev_community": float(a["community"]["noul"]),
            "jev_name_only": float(a["name_only"]["noul"]),
            "jev_impersonation": float(a["impersonation"]["noul"]),
            "jev_model": out.get("model"),
            "jev_latency_ms": latency_ms,
            "jev_error": None,
        }
    except (KeyError, TypeError, ValueError) as e:
        return {"jev_error": f"bad answers: {e}", "jev_latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Reading the backlog and writing the rows
# ---------------------------------------------------------------------------

UNMAPPED_SQL = """
    SELECT a.id, a.platform, a.handle, a.display_name, a.bio, a.profile_url,
           a.verified, a.followers_count, a.posts_count, a.summary, a.brand_context
      FROM social_accounts a
      LEFT JOIN bw_entity_social_identities i
             ON i.social_account_id = a.id AND i.valid_to IS NULL
     WHERE i.id IS NULL
     ORDER BY COALESCE(a.followers_count, 0) DESC, a.id
     LIMIT :lim
"""

BRANDS_SQL = "SELECT id, name, display_name, description, brand_keywords FROM bw_brands WHERE enabled"

COLS = ["batch_key", "social_account_id", "platform", "handle", "display_name",
        "candidate_brand_ids", "candidate_count", "name_match_brand_id", "name_match_exact",
        "evidence_beyond_name",
        "jev_owner_brand_id", "jev_owner_confidence", "jev_action", "jev_action_confidence",
        "jev_company_account", "jev_person",
        "jev_community", "jev_name_only", "jev_impersonation",
        "jev_model", "jev_latency_ms", "jev_error"]


def _insert(rows: List[Dict[str, Any]]) -> int:
    from sqlalchemy import text
    from app.database import get_database_instance
    sql = text(f"INSERT INTO entity_identity_shadow ({', '.join(COLS)}) "
               f"VALUES ({', '.join(':' + c for c in COLS)})")
    conn = get_database_instance()._temp_get_connection()
    n = 0
    try:
        for r in rows:
            conn.execute(sql, {c: r.get(c) for c in COLS})
            n += 1
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[identity shadow] insert failed: {e}")
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return n


def run_for_unmapped(limit: Optional[int] = None, *, scan: int = 400) -> Dict[str, Any]:
    """Judge the unmapped accounts that have at least one plausible company.

    ``scan`` accounts are read, the shortlist filter decides which of them are
    worth asking about, and at most ``limit`` are sent. Returns a summary.
    """
    if not enabled():
        return {"skipped": "disabled"}
    from sqlalchemy import text
    from app.database import get_database_instance
    limit = int(limit or os.getenv("TYPESAFE_SHADOW_IDENTITY_MAX", "100"))
    conn = get_database_instance()._temp_get_connection()
    try:
        brands = [dict(r) for r in conn.execute(text(BRANDS_SQL)).mappings().all()]
        accounts = [dict(r) for r in conn.execute(text(UNMAPPED_SQL), {"lim": scan}).mappings().all()]
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    batch_key = uuid.uuid4().hex[:16]
    rows: List[Dict[str, Any]] = []
    for acct in accounts:
        if len(rows) >= limit:
            break
        cands, name_match, exact = shortlist(acct, brands)
        if not cands:
            continue
        row = {
            "batch_key": batch_key,
            "social_account_id": int(acct["id"]),
            "platform": acct.get("platform"),
            "handle": acct.get("handle"),
            "display_name": acct.get("display_name"),
            "candidate_brand_ids": ",".join(str(b["id"]) for b in cands),
            "candidate_count": len(cands),
            "name_match_brand_id": name_match,
            "name_match_exact": exact,
            "evidence_beyond_name": has_evidence(acct),
        }
        row.update(resolve(acct, cands))
        rows.append(row)

    written = _insert(rows) if rows else 0
    ok = [r for r in rows if not r.get("jev_error")]
    agreed = sum(1 for r in ok if r.get("jev_owner_brand_id") == r.get("name_match_brand_id"))
    summary = {
        "batch_key": batch_key, "scanned": len(accounts), "judged": len(rows), "written": written,
        "errors": len(rows) - len(ok),
        "jev_named_a_company": sum(1 for r in ok if r.get("jev_owner_brand_id") is not None),
        "name_match_named_a_company": sum(1 for r in rows if r.get("name_match_brand_id") is not None),
        "agree_with_name_match": agreed,
        "name_only_evidence": sum(1 for r in ok if (r.get("jev_name_only") or 0) >= 0.5
                                  and r.get("jev_owner_brand_id") is not None),
        "with_evidence_beyond_name": sum(1 for r in rows if r.get("evidence_beyond_name")),
        "actions": {k: sum(1 for r in ok if r.get("jev_action") == k)
                    for k in ("propose_owned", "propose_community", "propose_person", "leave")},
        "not_company_accounts": sum(1 for r in ok if (r.get("jev_company_account") or 0) < 0.5),
    }
    logger.info("🪞 [identity shadow] %s", summary)
    return summary
