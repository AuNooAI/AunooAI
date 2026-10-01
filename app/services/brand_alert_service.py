"""Brand Watcher adverse-media alert delivery.

Takes persisted bw_alert_events rows that have not been delivered yet and pushes
them through the configured channels:
  - in_app   -> notifications table (NotificationBell UI picks it up)
  - email    -> EmailService (Resend/SMTP), template modelled on send_signal_alert_email
  - webhook  -> JSON POST (Slack-incoming-webhook compatible: includes "text")

Config lives in bw_alert_config (rules/thresholds are consumed by the evaluator in
app/tasks/brand_watcher_monitor.py; this module only handles delivery).
"""
import json
import re
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡"}

# Mirrors the evaluator's sentiment/engagement SQL (app/tasks/brand_watcher_monitor.py) —
# kept here so both the evaluator and the digest can pull the posts behind an alert
# without a services -> tasks import.
_NEG_SENT_SQL = ("(sentiment ILIKE '%negativ%' OR sentiment ILIKE '%concern%' OR sentiment ILIKE '%pessimis%'"
                 " OR sentiment ILIKE '%critical%' OR sentiment ILIKE '%alarm%')")
_ENGAGEMENT_SQL = ("(COALESCE((social_meta->>'likes')::float,0) + 2*COALESCE((social_meta->>'reposts')::float,0)"
                   " + COALESCE((social_meta->>'comments')::float,0) + COALESCE((social_meta->>'plays')::float,0)/100)")


def not_own_account_sql(conn, alias: str = "articles") -> str:
    """SQL condition that drops posts from the brand's own registered accounts.

    A post counts as the brand's own when its author is a verified account in
    ``bw_entity_social_identities`` registered to the brand the row's topic
    watches (``Brand Monitoring <name>``). The Social tab already leaves these
    out of its feed and sentiment; the alert rules did not, and only skipped
    handles starting with the brand's name, so @ora2_official could count
    towards a negative spike for Sunstar. "TRUE" on a tree without the
    registry, so the rules run unchanged there.
    """
    try:
        if conn.execute(text("SELECT to_regclass('bw_entity_social_identities')")).scalar() is None:
            return "TRUE"
    except Exception as e:  # noqa: BLE001 - alerts stand without the filter
        logger.warning("alerts: own-account registry probe failed: %s", e)
        return "TRUE"
    return (f"NOT EXISTS (SELECT 1 FROM bw_entity_social_identities _oi"
            f" JOIN social_accounts _osa ON _osa.id = _oi.social_account_id"
            f" JOIN bw_brands _ob ON _ob.id = _oi.brand_id"
            f" WHERE _oi.relationship IN ('owned_company', 'product')"
            f" AND _oi.status = 'verified' AND _oi.valid_to IS NULL"
            f" AND {alias}.topic = 'Brand Monitoring ' || _ob.display_name"
            f" AND LOWER(_osa.handle_canonical) = LOWER({alias}.social_meta->>'author')"
            f" AND LOWER(_osa.platform) = LOWER(COALESCE({alias}.social_meta->>'platform',"
            f" SPLIT_PART({alias}.news_source, ':', 2))))")


def fetch_negative_social_posts(conn, topic: str, hours: int, author: Optional[str] = None,
                                min_engagement: Optional[float] = None, limit: int = 6) -> List[Dict[str, Any]]:
    """The negative on-brand social posts behind a social alert, most-engaged first.

    Same predicates as the alert rules themselves (topic lane, alignment >= 0.4,
    negative sentiment, false-positive exclusion), so the posts shown are exactly
    the ones that were counted.
    """
    from app.services.social_sources import social_src_sql
    params: Dict[str, Any] = {"t": topic, "h": str(hours), "lim": limit}
    extra = ""
    if author:
        extra += " AND LOWER(COALESCE(social_meta->>'author','')) = :author"
        params["author"] = author.lower()
    if min_engagement is not None:
        extra += f" AND {_ENGAGEMENT_SQL} >= :min_eng"
        params["min_eng"] = min_engagement
    rows = conn.execute(text(f"""
        SELECT title, uri, news_source, LEFT(COALESCE(NULLIF(summary,''), title, ''), 400),
               COALESCE(social_meta->>'author',''), {_ENGAGEMENT_SQL} AS eng
        FROM articles
        WHERE topic = :t AND {social_src_sql('news_source')}
          AND topic_alignment_score >= 0.4 AND {_NEG_SENT_SQL}
          AND publication_date >= to_char(now() - (:h || ' hours')::interval,'YYYY-MM-DD"T"HH24:MI:SS')
          AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews _fpr
                          WHERE _fpr.article_uri = articles.uri AND _fpr.status = 'false_positive')
          AND {not_own_account_sql(conn)}
          {extra}
        ORDER BY eng DESC NULLS LAST, publication_date DESC NULLS LAST
        LIMIT :lim
    """), params).fetchall()
    return [{"title": r[0] or "", "url": r[1], "source": r[2] or "", "text": r[3] or "",
             "author": r[4] or "", "engagement": round(float(r[5] or 0))} for r in rows]


def _platform_label(source: str) -> str:
    """Reader-facing platform name from the internal news_source ('xpoz:twitter' → 'X/Twitter')."""
    s = (source or "").lower().split(":")[-1]
    return {"twitter": "X/Twitter", "reddit": "Reddit", "instagram": "Instagram",
            "tiktok": "TikTok", "bluesky": "Bluesky", "bsky": "Bluesky",
            "youtube": "YouTube", "reddit.com": "Reddit"}.get(s, source or "")


# A reasoning model (gpt-5.4-mini is kimi-k2.5 on the monolith since 8 Sep)
# sometimes writes its working into the reply: "The user wants me to
# summarize ... I need to: ... Key elements: ...". On wbm (24 Sep) two alert
# emails to Wiley carried that text as "What the posts say". The reply is now
# a JSON object, only its "summary" is used, and a summary that still reads
# like working is dropped; the alert then ships with the post list alone.
_WORKING_TEXT = re.compile(
    r"^\s*(the user|i need to|i'll|i will|let me|okay|ok,|alright|first,|so,|we need to|the task)"
    r"|key elements|from the post:|\bi need to\b|\bthe user wants\b",
    re.IGNORECASE)


def _narration_summary(raw: str) -> Optional[str]:
    """The "summary" of the first JSON object in a model reply, or None."""
    decoder = json.JSONDecoder()
    text_ = raw or ""
    for i, ch in enumerate(text_):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text_[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("summary"), str):
            out = " ".join(obj["summary"].split())
            if out and not _WORKING_TEXT.search(out) and not out.startswith(("-", "*", "#", "⚠")):
                return out[:700]
            return None
    return None


# The model the narrator runs on, named for what it is. It used to ask for
# "gpt-5.4-mini", an alias that the 8 Sep yaml repoint silently moved from
# Haiku to kimi (a reasoning model); nobody checked this free-text,
# customer-facing caller could take that.
NARRATION_MODEL = "bedrock-kimi-k2-5"
NARRATION_CHECK_USE_CASE = "services.brand_alert_service:narration_check"


def _jev_check_narration(summary: str, posts: List[Dict[str, Any]]) -> Optional[bool]:
    """Jev's verdict on a narration before it ships, or None when Jev is not used.

    Three questions in one call: is the text a summary written for a reader
    (not notes on how to write one, instructions or the writer's working),
    do the posts support what it says, and does it state anything no post
    states. Any failure drops the narration; the alert ships with the posts. On for a site with
    TYPESAFE_VALIDATE_NARRATION=1 and a TypeSafe key; sites whose data may not
    go to TypeSafe (the Wiley sites, no DPA) leave it off and rely on the
    JSON-and-filter guard alone.
    """
    if (os.getenv("TYPESAFE_VALIDATE_NARRATION") or "").strip().lower() not in ("1", "true", "on", "yes"):
        return None
    try:
        from app.services import typesafe_client
    except ImportError:
        return None
    if not typesafe_client.is_configured():
        return None
    state = {
        "posts": [{"author": p.get("author") or "", "text": (p.get("text") or p.get("title") or "")[:350]}
                  for p in posts[:8]],
        "summary": summary,
    }
    questions = {
        "is_summary": {
            "type": "noul",
            "instructions": ("Is `summary` a finished summary of `posts` written for a reader, rather than "
                             "notes about how to write one, a restatement of instructions, or the writer's "
                             "own reasoning?"),
            "criteria": {"true": "A finished summary a reader could be sent",
                         "false": "Working notes, instructions, reasoning, or not a summary of these posts"},
        },
        "support": {
            "type": "choice",
            "instructions": "Do `posts` support what `summary` says?",
            "criteria": {"supported": "Everything the summary says is stated in the posts",
                         "partly": "Some of what the summary says is not in the posts",
                         "contradicts": "The summary says something the posts contradict"},
        },
        # Tested on abm posts (25 Sep): real summaries 0.17-0.26, summaries with
        # an invented layoff, contract loss or ban 0.96-0.98.
        "unsupported_claim": {
            "type": "noul",
            "instructions": "Does `summary` state any fact, number, event or claim that none of `posts` states?",
            "criteria": {"true": "At least one claim in the summary is not in any post",
                         "false": "Every claim in the summary comes from the posts"},
        },
    }
    out = typesafe_client.system_one(state, questions, use_case=NARRATION_CHECK_USE_CASE)
    if not out:
        return None  # Jev down or refused: the regex guard has already run
    answers = out.get("answers") or {}
    is_summary = (answers.get("is_summary") or {}).get("noul")
    probs = (answers.get("support") or {}).get("probabilities") or {}
    support = max(probs, key=probs.get) if probs else None
    invented = (answers.get("unsupported_claim") or {}).get("noul")
    ok = ((is_summary is None or is_summary >= 0.5)
          and support in (None, "supported")
          and (invented is None or invented < 0.5))
    if not ok:
        logger.warning("bw narration rejected by Jev: is_summary=%s support=%s unsupported_claim=%s: %r",
                       is_summary, support, invented, summary[:160])
    return ok


def narrate_social_posts(brand: str, posts: List[Dict[str, Any]]) -> Optional[str]:
    """2-3 plain sentences on what the posts actually say. Best-effort: None on failure,
    and the alert ships with the linked post list only."""
    if not posts:
        return None
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance(NARRATION_MODEL)
        block = "\n".join(
            f"- {_platform_label(p['source'])} · @{p['author'] or 'unknown'}: {(p['text'] or p['title'])[:350]}"
            for p in posts[:8]
        )
        prompt = (
            f"Negative social posts about the brand \"{brand}\" (platform · author: post):\n"
            + block[:3500]
            + "\n\nIn 2-3 plain sentences, say what these posts are actually saying — the "
            "concrete complaints, claims or stories, named specifically, and who is saying "
            "them when it matters (one loud account, a single community, many unrelated "
            "users). Observations only, nothing not present in the posts. "
            'Respond with ONLY a JSON object: {"summary": "<the 2-3 sentences>"}. '
            "No other text."
        )
        # LiteLLMModel signals failure by RETURNING error prose ("⚠️ <model> is
        # currently unavailable...") instead of raising; that has no JSON, so
        # it is dropped here rather than landing in a digest or alert email.
        for _attempt in range(2):
            out = _narration_summary(model.generate_response(
                [{"role": "user", "content": prompt}], temperature=0.2) or "")
            if out and _jev_check_narration(out, posts) is not False:
                return out
        logger.info("bw social-post narration for %s: no clean summary; sending posts only", brand)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"bw social-post narration failed for {brand}: {e}")
        return None


def social_posts_md(posts: List[Dict[str, Any]], limit: int = 5, indent: str = "") -> List[str]:
    """Markdown bullets for the posts behind an alert: linked text — @author · platform · engagement."""
    lines = []
    for p in posts[:limit]:
        t = (p.get("title") or p.get("text") or "").replace("\\n", " ").replace("\\t", " ")
        t = " ".join(t.split())[:110].replace("[", "(").replace("]", ")")
        link = f"[{t}]({p['url']})" if str(p.get("url") or "").startswith("http") else t
        bits = [b for b in (f"@{p['author']}" if p.get("author") else "",
                            _platform_label(p.get("source") or ""),
                            f"engagement {p['engagement']}" if p.get("engagement") else "") if b]
        lines.append(f"{indent}- {link}" + (" — " + " · ".join(bits) if bits else ""))
    return lines


def get_alert_config(conn) -> Optional[Dict[str, Any]]:
    """Load the tenant-wide alert config row (brand_id NULL). Returns None if absent."""
    row = conn.execute(text("""
        SELECT id, enabled, rules, channels, email_recipients, webhook_url, cooldown_hours
        FROM bw_alert_config WHERE brand_id IS NULL ORDER BY id LIMIT 1
    """)).fetchone()
    if not row:
        return None
    def _j(v, default):
        if v is None:
            return default
        return v if isinstance(v, (dict, list)) else json.loads(v)
    return {
        "id": row[0], "enabled": row[1],
        "rules": _j(row[2], {}), "channels": _j(row[3], {}),
        "email_recipients": _j(row[4], []), "webhook_url": row[5],
        "cooldown_hours": row[6] or 24,
    }


def _deliver_in_app(db, event: Dict[str, Any]) -> bool:
    try:
        db.facade.create_notification(
            username=None,  # system-wide
            type="brand_watcher_adverse",
            title=event["title"],
            message=(event.get("body") or "")[:500],
            link="/explore",
        )
        return True
    except Exception as e:
        logger.warning(f"bw alert in_app delivery failed: {e}")
        return False


def _deliver_email(event: Dict[str, Any], recipients: List[str]) -> bool:
    if not recipients:
        return False
    try:
        from app.services.email_service import get_email_service, markdown_to_html
        svc = get_email_service()
        if not svc.is_available():
            logger.warning("bw alert email skipped: email service not configured")
            return False
        sev = event.get("severity", "medium")
        domain = os.getenv("DOMAIN", "")
        link = f"https://{domain}/explore" if domain else ""
        body_md = (
            f"**{SEVERITY_EMOJI.get(sev, '')} {event['title']}**\n\n"
            f"{event.get('body') or ''}\n\n"
            + (f"[Open Brand Watcher]({link})\n" if link else "")
        )
        # Release gate (advisory) — logs internal-name leaks and similar
        # defects before the alert reaches a customer inbox.
        try:
            from app.services.report_lint import lint_outbound
            lint_outbound(body_md, kind="html", context="bw_alert_email")
        except Exception:
            pass
        ok = svc.send_email(
            to_addresses=recipients,
            subject=f"[AuNoo AI] Brand alert: {event['title'][:120]}",
            body_html=markdown_to_html(body_md),
            body_text=f"{event['title']}\n\n{event.get('body') or ''}\n{link}",
            ai_generated=True,
        )
        return bool(ok)
    except Exception as e:
        logger.warning(f"bw alert email delivery failed: {e}")
        return False


def _deliver_webhook(event: Dict[str, Any], url: str) -> bool:
    if not url:
        return False
    try:
        sev = event.get("severity", "medium")
        payload = {
            # "text" makes this drop-in compatible with Slack incoming webhooks.
            "text": f"{SEVERITY_EMOJI.get(sev, '')} Brand alert ({sev}): {event['title']}\n{event.get('body') or ''}",
            "rule": event.get("rule"),
            "severity": sev,
            "brand_id": event.get("brand_id"),
            "payload": event.get("payload"),
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        logger.warning(f"bw alert webhook delivery failed: {e}")
        return False


def deliver_pending_events(db, conn) -> int:
    """Deliver all bw_alert_events rows with delivered IS NULL. Returns count delivered."""
    cfg = get_alert_config(conn)
    if not cfg or not cfg["enabled"]:
        return 0
    channels = cfg["channels"] or {}
    rows = conn.execute(text("""
        SELECT id, brand_id, rule, severity, title, body, payload
        FROM bw_alert_events WHERE delivered IS NULL AND rule <> 'digest'
        ORDER BY id LIMIT 50
    """)).fetchall()
    done = 0
    for rid, brand_id, rule, severity, title, body, payload in rows:
        event = {"id": rid, "brand_id": brand_id, "rule": rule, "severity": severity,
                 "title": title, "body": body, "payload": payload}
        delivered: Dict[str, bool] = {}
        if channels.get("in_app", True):
            delivered["in_app"] = _deliver_in_app(db, event)
        if channels.get("email"):
            delivered["email"] = _deliver_email(event, cfg["email_recipients"])
        if channels.get("webhook"):
            delivered["webhook"] = _deliver_webhook(event, cfg["webhook_url"])
        conn.execute(text("UPDATE bw_alert_events SET delivered = :d WHERE id = :i"),
                     {"d": json.dumps(delivered), "i": rid})
        done += 1
        logger.info(f"bw alert delivered #{rid} [{rule}/{severity}] via {[k for k, v in delivered.items() if v]}")
    if done:
        conn.commit()
    return done
