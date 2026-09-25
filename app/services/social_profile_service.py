"""Social account profiles — lean, xpoz-powered per-account brand intelligence.

Given a social handle (X / Reddit / Instagram / TikTok), build a lean profile:
identity + reach (followers/engagement), recent post history, brand-relative
sentiment (via SocialEvalService), and an LLM summary + topics + brand-context.
Persisted to `social_accounts`. Built ON-DEMAND only (never bulk/auto) for cost.

No threat/dimensional/AI-tell/MBFC machinery — that was deliberately dropped for
the brand use-case (see Phase 2 plan). Reddit degrades to profile-stats only
(xpoz exposes no reddit post-history/connections API).
"""
import os
import re
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)

_PLATFORMS = ("twitter", "reddit", "instagram", "tiktok", "bluesky")
#: A profile that sells marketing services, whatever the model called it.
_MARKETER = re.compile(r"\bseo\b|growth\s+hack|digital\s+marketing|"
                       r"marketing\s+(consultant|expert|agency)", re.I)
# The part an account plays in a market, when profiled for one. Stored in
# social_accounts.metadata as market_role / market_org / market.
MARKET_ROLES = ("vendor", "vendor_staff", "practitioner", "analyst_or_press",
                "reseller", "promoter_or_bot", "unrelated")
_HAS_POST_HISTORY = {"twitter", "instagram", "tiktok", "bluesky"}  # reddit: none via xpoz
_BSKY_API = "https://public.api.bsky.app/xrpc"  # bluesky is NOT xpoz — use its public API

# Explicit get_user field sets (xpoz returns a minimal default projection otherwise).
_USER_FIELDS = {
    "twitter": ["id", "username", "name", "description", "followers_count",
                "following_count", "tweet_count", "media_count", "profile_image_url",
                "verified", "is_verified", "created_at"],
    "reddit": ["id", "username", "profile_description", "profile_title", "link_karma",
               "comment_karma", "total_karma", "profile_pic_url", "verified",
               "created_at_date"],
    "instagram": ["id", "username", "full_name", "biography", "follower_count",
                  "following_count", "media_count", "profile_pic_url", "is_verified",
                  "external_url"],
    "tiktok": ["id", "username", "nickname", "signature", "follower_count",
               "following_count", "post_count", "avatar", "is_verified", "region",
               "created_at"],
}
_POST_FIELDS = {
    # NB: do NOT request `created_at` — xpoz's pydantic model rejects posts whose
    # created_at is an int epoch (old posts), failing the whole fetch. Use created_at_date.
    "twitter": ["id", "text", "like_count", "retweet_count", "reply_count",
                "media_urls", "created_at_date"],
    "instagram": ["id", "caption", "code_url", "image_url", "like_count",
                  "comment_count", "created_at_date"],
    "tiktok": ["id", "description", "video_url", "video_thumbnail", "like_count",
               "comment_count", "play_count", "created_at_date"],
}


def _api_key() -> Optional[str]:
    return os.getenv("XPOZ_API_KEY") or os.getenv("PROVIDER_XPOZ_API_KEY")


def norm_handle(platform: str, handle: str) -> str:
    h = (handle or "").strip()
    h = re.sub(r"^https?://(www\.)?[^/]+/", "", h)      # strip profile URL prefix
    h = h.lstrip("@").rstrip("/")
    if platform == "reddit":
        h = re.sub(r"^u/", "", h, flags=re.IGNORECASE)
    return h.split("/")[0].lower()


def _pub_iso(p) -> str:
    ca = getattr(p, "created_at", None)
    if isinstance(ca, (int, float)) and ca:
        try:
            return datetime.fromtimestamp(ca, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(ca, str) and ca.strip():
        return ca
    return str(getattr(p, "created_at_date", "") or "")


def _clean(t: Optional[str], n: int = 600) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()[:n]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()



_DEFAULT_AUDIENCE_FIELD = (
    '"audience": "<exactly one of: patient (uses, is prescribed or referred to a '
    "vendor's health service), caregiver (speaks for a patient), clinician (doctor, "
    "GP, nurse, dietitian, pharmacist, therapist speaking as such), dental_professional "
    "(dentist, hygienist, orthodontist, dental clinic or dental student), customer (end "
    "user or buyer of a non-health product), academic, professional (works in the "
    "field but not for a vendor: analyst, commissioner, partner organisation), "
    "employee (of a vendor), journalist, investor, retailer (a shop, pharmacy, online "
    "seller or distributor selling vendors' products), brand (a vendor's own or affiliate "
    'account), unknown>"'
)


def _audience_field() -> str:
    """The "audience" line of the profile prompt, listing this site's roles.

    The standard text names the health and consumer roles; a site with its own
    persona set (voices_personas, e.g. a publisher) lists that set instead.
    """
    from app.services import voices_personas
    alt = voices_personas.active_set()
    if alt is None:
        return _DEFAULT_AUDIENCE_FIELD
    roles = ", ".join(f"{k} ({v[0].lower() + v[1:]})" for k, v in alt.reasons.items())
    return '"audience": "<exactly one of: ' + roles + '>"'

class ProfileLookupUnavailable(RuntimeError):
    """The provider could not serve the lookup right now (quota, rate limit,
    outage). Distinct from "no such account" so callers do not tell the user
    an account does not exist when the truth is that we could not ask. The
    message is user-facing and deliberately says nothing about credits or
    quotas."""

    USER_MESSAGE = ("Account lookup is temporarily unavailable. "
                    "Please try again in a few minutes.")

    def __init__(self, reason: str = ""):
        super().__init__(self.USER_MESSAGE)
        self.reason = reason


class SocialProfileService:
    def __init__(self):
        self.api_key = _api_key()

    # ---- xpoz fetch (sync, runs in a worker thread) -----------------------

    def _fetch_sync(self, platform: str, handle: str, max_posts: int) -> Optional[Dict]:
        from xpoz import XpozClient
        client = XpozClient(self.api_key, check_update=False)
        try:
            ns = getattr(client, platform, None)
            if ns is None:
                return None
            try:
                user = ns.get_user(handle, fields=_USER_FIELDS.get(platform))
            except Exception as e:  # noqa: BLE001
                # Only a malformed handle means "no such account" here. Every
                # other failure (usage limit, 429, outage) is the provider not
                # answering, and used to fall through to "No X account found"
                # in the UI (oviva, 2026-09-08, during an xpoz quota outage).
                msg = str(e)
                if "Validation failed" in msg or "Invalid" in msg:
                    logger.info("xpoz get_user(%s/%s): rejected handle: %s", platform, handle, msg[:160])
                    return None
                logger.warning("xpoz get_user(%s/%s) unavailable: %s", platform, handle, msg[:200])
                raise ProfileLookupUnavailable(msg) from e
            if user is None:
                return None
            ident = self._map_identity(platform, user)
            posts: List[Dict] = []
            if platform in _HAS_POST_HISTORY:
                try:
                    fetch = ns.get_posts_by_author if platform == "twitter" else ns.get_posts_by_user
                    res = fetch(handle, fields=_POST_FIELDS.get(platform), limit=max_posts)
                    posts = [self._map_post(platform, p) for p in (getattr(res, "data", None) or [])]
                    posts = [p for p in posts if p]
                except Exception as e:  # noqa: BLE001
                    logger.warning("xpoz post history (%s/%s) failed: %s", platform, handle, e)
            ident["posts"] = posts
            return ident
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    def _map_identity(self, platform: str, u) -> Dict:
        g = lambda *names: next((getattr(u, n) for n in names if getattr(u, n, None) not in (None, "")), None)  # noqa: E731
        username = g("username") or ""
        if platform == "twitter":
            base = {"display_name": g("name"), "bio": g("description"),
                    "followers_count": g("followers_count"), "following_count": g("following_count"),
                    "posts_count": g("tweet_count"), "avatar_url": g("profile_image_url"),
                    "verified": bool(g("verified") or g("is_verified")),
                    "account_created_at": g("created_at"),
                    "profile_url": f"https://x.com/{username}"}
        elif platform == "reddit":
            base = {"display_name": g("profile_title") or username, "bio": g("profile_description"),
                    "followers_count": None, "following_count": None,
                    "posts_count": g("link_karma"),  # reddit has no post count; surface link karma
                    "avatar_url": g("profile_pic_url"), "verified": bool(g("verified")),
                    "account_created_at": g("created_at_date"),
                    "profile_url": f"https://www.reddit.com/user/{username}"}
        elif platform == "instagram":
            base = {"display_name": g("full_name"), "bio": g("biography"),
                    "followers_count": g("follower_count"), "following_count": g("following_count"),
                    "posts_count": g("media_count"), "avatar_url": g("profile_pic_url"),
                    "verified": bool(g("is_verified")), "account_created_at": None,
                    "profile_url": f"https://www.instagram.com/{username}/"}
        else:  # tiktok
            base = {"display_name": g("nickname"), "bio": g("signature"),
                    "followers_count": g("follower_count"), "following_count": g("following_count"),
                    "posts_count": g("post_count"), "avatar_url": g("avatar"),
                    "verified": bool(g("is_verified")), "account_created_at": g("created_at"),
                    "profile_url": f"https://www.tiktok.com/@{username}"}
        base["handle"] = username or handle_of(u)
        base["platform"] = platform
        return base

    def _map_post(self, platform: str, p) -> Optional[Dict]:
        pid = getattr(p, "id", None)
        if not pid:
            return None
        if platform == "twitter":
            text_ = _clean(getattr(p, "text", None), 4000)
            media = getattr(p, "media_urls", None)
            return {"id": str(pid), "text": text_, "created_at": _pub_iso(p),
                    "likes": getattr(p, "like_count", None), "reposts": getattr(p, "retweet_count", None),
                    "comments": getattr(p, "reply_count", None),
                    "thumbnail": media[0] if isinstance(media, (list, tuple)) and media else None,
                    "url": f"https://x.com/i/status/{pid}"}
        if platform == "instagram":
            return {"id": str(pid), "text": _clean(getattr(p, "caption", None), 4000), "created_at": _pub_iso(p),
                    "likes": getattr(p, "like_count", None), "comments": getattr(p, "comment_count", None),
                    "thumbnail": getattr(p, "image_url", None), "url": getattr(p, "code_url", None)}
        # tiktok
        return {"id": str(pid), "text": _clean(getattr(p, "description", None), 4000), "created_at": _pub_iso(p),
                "likes": getattr(p, "like_count", None), "comments": getattr(p, "comment_count", None),
                "plays": getattr(p, "play_count", None), "thumbnail": getattr(p, "video_thumbnail", None),
                "url": getattr(p, "video_url", None)}

    # ---- bluesky fetch (public AT-proto API; not xpoz) --------------------

    async def _bluesky_fetch(self, handle: str, cap: int, with_conns: bool = False) -> Optional[Dict]:
        import aiohttp
        prof, feed, follows = None, [], []
        timeout = aiohttp.ClientTimeout(total=25)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(f"{_BSKY_API}/app.bsky.actor.getProfile", params={"actor": handle}) as r:
                    if r.status != 200:
                        return None
                    prof = await r.json()
                async with s.get(f"{_BSKY_API}/app.bsky.feed.getAuthorFeed",
                                 params={"actor": handle, "limit": str(min(cap, 100))}) as r:
                    if r.status == 200:
                        feed = (await r.json()).get("feed", []) or []
                if with_conns:
                    async with s.get(f"{_BSKY_API}/app.bsky.graph.getFollows",
                                     params={"actor": handle, "limit": "24"}) as r:
                        if r.status == 200:
                            follows = (await r.json()).get("follows", []) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("bluesky fetch failed for %s: %s", handle, e)
            if prof is None:
                return None
        if not prof:
            return None
        h = prof.get("handle") or handle
        posts: List[Dict] = []
        for item in feed:
            post = (item or {}).get("post") or {}
            if not post.get("uri"):
                continue
            rec = post.get("record") or {}
            emb = post.get("embed") or {}
            imgs = emb.get("images") or (emb.get("media") or {}).get("images") or []
            thumb = imgs[0].get("thumb") if isinstance(imgs, list) and imgs else None
            rkey = str(post["uri"]).split("/")[-1]
            posts.append({
                "id": post["uri"], "text": _clean(rec.get("text"), 4000),
                "created_at": rec.get("createdAt") or post.get("indexedAt"),
                "likes": post.get("likeCount"), "reposts": post.get("repostCount"),
                "comments": post.get("replyCount"), "thumbnail": thumb,
                "url": f"https://bsky.app/profile/{h}/post/{rkey}",
            })
        return {
            "platform": "bluesky", "handle": h,
            "display_name": prof.get("displayName"), "bio": prof.get("description"),
            "avatar_url": prof.get("avatar"), "verified": False,
            "followers_count": prof.get("followersCount"), "following_count": prof.get("followsCount"),
            "posts_count": prof.get("postsCount"), "account_created_at": prof.get("createdAt"),
            "profile_url": f"https://bsky.app/profile/{h}",
            "posts": posts,
            "connections": [{"handle": f.get("handle"), "name": f.get("displayName"), "followers": None} for f in follows],
        }

    # ---- enrichment (LLM summary + topics + brand context) ----------------

    @staticmethod
    def _market_posts(db, platform: str, handle: str, limit: int = 8) -> List[str]:
        """This account's posts that the site collected about the market's vendors.

        The platform fetch returns the account's latest posts, which for a
        patient logging their weight or a GP in a prescribing thread rarely
        mention the vendor at all, so the model read 24 of 40 Oviva authors as
        "no clear connection". The posts that brought the account here are
        the evidence of its part in the market; they go in first.
        """
        try:
            conn = db._temp_get_connection()
            try:
                rows = conn.execute(sql_text("""
                    SELECT COALESCE(a.summary, a.title) AS body,
                           COALESCE(a.author_role, '') AS role
                      FROM articles a
                     WHERE LOWER(a.social_meta->>'author') = LOWER(:h)
                       AND LOWER(COALESCE(a.social_meta->>'platform',
                                          SPLIT_PART(a.news_source, ':', 2))) = LOWER(:p)
                       AND (a.author_role IS NOT NULL OR a.topic LIKE 'Brand Monitoring %'
                            OR a.topic LIKE 'Market Monitoring %')
                     ORDER BY a.publication_date DESC NULLS LAST
                     LIMIT :lim
                """), {"h": handle, "p": platform, "lim": limit}).fetchall()
            finally:
                conn.close()
            return [str(r[0]).strip()[:300] for r in rows if r[0] and str(r[0]).strip()]
        except Exception as e:  # noqa: BLE001 - evidence is an enhancement, never a blocker
            logger.debug("profile market posts lookup failed for %s/%s: %s", platform, handle, e)
            return []

    async def _summarize(self, ident: Dict, posts: List[Dict], brand: Optional[str],
                         context: Optional[str] = None,
                         market_posts: Optional[List[str]] = None) -> Dict:
        try:
            from app.ai_models import LiteLLMModel
            model = LiteLLMModel.get_instance(os.getenv("SOCIAL_EVAL_MODEL", "claude-haiku-4-5"))
        except Exception:
            model = None
        if not model:
            return {}
        sample = "\n".join(f"- {p['text'][:200]}" for p in posts[:12] if p.get("text")) or "(no post text available)"
        market_block = ""
        if context and not brand and market_posts:
            market_block = ("\n\nPOSTS BY THIS ACCOUNT ABOUT THE MARKET'S VENDORS (judge their part "
                            "in the market from these first; the recent posts only show who "
                            "they are in general):\n"
                            + "\n".join(f"- {t}" for t in market_posts[:8]))
        # A market frames the account differently from a brand: the question
        # is what part it plays in the market (vendor staff, customer, analyst,
        # reseller, promoter, bot), not whether it likes one company.
        role_fields = ""
        if context and not brand:
            brand_line = (f'The account is being profiled for the market "{context}". ')
            relation = ("<1-2 sentences on this account's part in that market: vendor "
                        "staff, customer or practitioner in the market's own field, analyst or press, reseller, "
                        "promoter or bot, or 'No clear connection.' A person using, prescribed, "
                        "referred to or treated with a vendor's product or service has a part in the "
                        "market; 'unrelated' is only for accounts whose posts never engage with it.>")
            # A fixed label beside the prose, so the reading can be tagged
            # and grouped without parsing a sentence.
            role_fields = (
                ', "role": "<exactly one of: vendor (the company\'s own account), '
                'vendor_staff (a person employed by or founding a vendor), practitioner '
                "(works in the market's field or uses its products: a clinician or patient "
                "for a health market, a security team member for a security market, a "
                "librarian or researcher for a publishing market), analyst_or_press, reseller, "
                'promoter_or_bot, unrelated>", '
                '"organisation": "<the company the account is or works for, or null>", '
                # Which side of the market the account speaks from. "practitioner"
                # covers both the GP who prescribes and the patient on the
                # programme; the Voices view needs them apart.
                + _audience_field())
        else:
            brand_line = f'The account is being profiled in the context of the brand "{brand}". ' if brand else ""
            relation = "<1-2 sentences on this account's relationship to the brand, or 'No clear connection.' >"
        sys = (
            "You are a brand-monitoring analyst. Given a social account's bio and recent posts, "
            "produce a compact, factual profile. Respond with ONLY a JSON object: "
            '{"summary": "<2-3 sentence plain description of who this account is and what they post about>", '
            '"topics": ["<3-6 short topic tags>"], '
            f'"brand_context": "{relation}"{role_fields}}}'
            " No prose outside the JSON."
        )
        usr = (f"{brand_line}ACCOUNT: @{ident.get('handle')} ({ident.get('platform')})\n"
               f"NAME: {ident.get('display_name') or ''}\nBIO: {ident.get('bio') or ''}"
               f"{market_block}\n\nRECENT POSTS:\n{sample}")
        try:
            from fastapi.concurrency import run_in_threadpool
            content = await run_in_threadpool(model.generate_response,
                                              [{"role": "system", "content": sys}, {"role": "user", "content": usr}])
            m = re.search(r"\{[\s\S]*\}", content or "")
            obj = json.loads(m.group()) if m else {}
            topics = obj.get("topics") or []
            if isinstance(topics, str):
                topics = [topics]
            out = {"summary": obj.get("summary"), "topics": topics[:8],
                   "brand_context": obj.get("brand_context")}
            if role_fields:
                role = str(obj.get("role") or "").strip().lower().replace(" ", "_")
                out["role"] = role if role in MARKET_ROLES else None
                org = obj.get("organisation")
                out["organisation"] = (str(org).strip()[:120]
                                       if org and str(org).strip().lower() not in ("null", "none", "") else None)
                try:
                    from app.services.social_eval_service import author_roles
                    site_roles = author_roles()
                except ImportError:
                    site_roles = ()
                aud = str(obj.get("audience") or "").strip().lower().replace(" ", "_")
                if out["role"] in ("vendor", "reseller", "promoter_or_bot"):
                    aud = "brand"   # the company's own voice, whatever it posts about
                out["audience"] = aud if aud in site_roles else None
            return out
        except Exception as e:  # noqa: BLE001
            logger.debug("profile summarize failed: %s", e)
            return {}

    async def _sentiment(self, posts: List[Dict], brand: Optional[str]) -> Dict:
        """Returns {agg: {pos,neu,neg,scored,net}, by_id: {post_id: 'positive'|...}}."""
        if not posts or not brand:
            return {"agg": None, "by_id": {}}
        try:
            from app.services.social_eval_service import SocialEvalService
            svc = SocialEvalService()
            eval_posts = [{"uri": p["id"], "title": "", "summary": p.get("text", "")} for p in posts]
            scored = await svc.evaluate_posts(eval_posts, brand)
        except Exception as e:  # noqa: BLE001
            logger.debug("profile sentiment failed: %s", e)
            return {"agg": None, "by_id": {}}
        pos = neu = neg = 0
        by_id: Dict = {}
        for s in scored:
            v = (s.get("sentiment") or "").lower()
            norm = "positive" if "pos" in v else "negative" if "neg" in v else "neutral" if "neu" in v else None
            if norm:
                by_id[s.get("uri")] = norm
            if norm == "positive": pos += 1
            elif norm == "negative": neg += 1
            elif norm == "neutral": neu += 1
        scored_n = pos + neu + neg
        net = round(((pos - neg) / scored_n) * 100) if scored_n else None
        return {"agg": {"pos": pos, "neu": neu, "neg": neg, "scored": scored_n, "net": net} if scored_n else None,
                "by_id": by_id}

    # ---- public API -------------------------------------------------------

    async def build_profile(self, db, platform: str, handle: str, brand: Optional[str] = None,
                            max_posts: Optional[int] = None,
                            context: Optional[str] = None) -> Optional[Dict]:
        """``brand`` frames the summary and scores post sentiment against it.
        ``context`` frames the summary only (a market name, say) and costs no
        per-post sentiment calls."""
        platform = (platform or "").lower()
        if platform not in _PLATFORMS:
            raise ValueError(f"Unsupported platform '{platform}'")
        if platform != "bluesky" and not self.api_key:
            raise RuntimeError("Xpoz API key not configured")
        canon = norm_handle(platform, handle)
        if not canon:
            raise ValueError("Empty handle")
        cap = int(max_posts or os.getenv("XPOZ_PROFILE_MAX", "50"))
        if platform == "bluesky":
            ident = await self._bluesky_fetch(canon, cap)
        else:
            ident = await asyncio.to_thread(self._fetch_sync, platform, canon, cap)
        if not ident:
            return None
        ident.pop("connections", None)
        posts = ident.pop("posts", [])
        market_posts = self._market_posts(db, platform, canon) if (context and not brand) else None
        summary, sentiment = await asyncio.gather(
            self._summarize(ident, posts, brand, context, market_posts=market_posts),
            self._sentiment(posts, brand))
        by_id = sentiment.get("by_id", {})
        for p in posts:
            p["sentiment"] = by_id.get(p["id"])
        top = sorted(posts, key=lambda p: (p.get("likes") or 0), reverse=True)
        row = {
            **ident,
            "handle_canonical": canon,
            "topics": summary.get("topics") or [],
            "post_sentiment": sentiment.get("agg"),
            "summary": summary.get("summary"),
            "brand_context": summary.get("brand_context"),
            "sample_posts": top[:12],
            "last_profiled_at": _now(),
            "metadata": self._market_meta(summary, context, ident),
        }
        return self._upsert(db, row)

    @staticmethod
    def _market_meta(summary: Dict, context: Optional[str],
                     ident: Optional[Dict] = None) -> Dict:
        if not context:
            return {}
        role = summary.get("role")
        # A marketer who writes about the market is not press: "Apoorv Sharma
        # | LLM + SaaS SEO Expert" was listed on aisocnews as Analyst / press.
        who = f"{(ident or {}).get('display_name') or ''} {(ident or {}).get('bio') or ''}"
        if role == "analyst_or_press" and _MARKETER.search(who):
            role = "promoter_or_bot"
        return {"market_role": role,
                "market_org": summary.get("organisation"),
                "audience_role": summary.get("audience"),
                "market": context, "market_read_at": _now()}

    async def reread(self, db, platform: str, handle: str, context: str) -> Optional[Dict]:
        """Run the model step again over the stored bio and sample posts.

        No platform call: for adding the market role to profiles built before
        it existed, at the cost of one short model call each."""
        stored = self.get_stored(db, platform, handle)
        if not stored:
            return None
        ident = {"handle": stored.get("handle"), "platform": platform,
                 "display_name": stored.get("display_name"), "bio": stored.get("bio")}
        posts = [p for p in (stored.get("sample_posts") or []) if isinstance(p, dict)]
        market_posts = self._market_posts(db, platform, stored.get("handle_canonical") or handle)
        summary = await self._summarize(ident, posts, None, context, market_posts=market_posts)
        if not summary:
            return None
        conn = db._temp_get_connection()
        conn.execute(sql_text("""
            UPDATE social_accounts
               SET summary = :summary, topics = CAST(:topics AS jsonb),
                   brand_context = :brand_context,
                   metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb)
             WHERE id = :id
        """), {"summary": summary.get("summary"), "topics": json.dumps(summary.get("topics") or []),
               "brand_context": summary.get("brand_context"),
               "metadata": json.dumps(self._market_meta(summary, context, ident)), "id": stored["id"]})
        try:
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        return self.get_stored(db, platform, handle)

    def _upsert(self, db, row: Dict) -> Dict:
        conn = db._temp_get_connection()
        params = dict(row)
        for k in ("topics", "post_sentiment", "sample_posts"):
            params[k] = json.dumps(params.get(k)) if params.get(k) is not None else None
        params["metadata"] = json.dumps(params.get("metadata") or {})
        params.setdefault("created_at", _now())
        conn.execute(sql_text("""
            INSERT INTO social_accounts
              (platform, handle, handle_canonical, display_name, avatar_url, bio, profile_url,
               verified, followers_count, following_count, posts_count, account_created_at,
               topics, post_sentiment, summary, brand_context, sample_posts, last_profiled_at, created_at,
               metadata)
            VALUES
              (:platform, :handle, :handle_canonical, :display_name, :avatar_url, :bio, :profile_url,
               :verified, :followers_count, :following_count, :posts_count, :account_created_at,
               CAST(:topics AS jsonb), CAST(:post_sentiment AS jsonb), :summary, :brand_context,
               CAST(:sample_posts AS jsonb), :last_profiled_at, :created_at,
               CAST(:metadata AS jsonb))
            ON CONFLICT (platform, handle_canonical) DO UPDATE SET
               handle=EXCLUDED.handle, display_name=EXCLUDED.display_name, avatar_url=EXCLUDED.avatar_url,
               bio=EXCLUDED.bio, profile_url=EXCLUDED.profile_url, verified=EXCLUDED.verified,
               followers_count=EXCLUDED.followers_count, following_count=EXCLUDED.following_count,
               posts_count=EXCLUDED.posts_count, account_created_at=EXCLUDED.account_created_at,
               topics=EXCLUDED.topics, post_sentiment=EXCLUDED.post_sentiment, summary=EXCLUDED.summary,
               brand_context=EXCLUDED.brand_context, sample_posts=EXCLUDED.sample_posts,
               last_profiled_at=EXCLUDED.last_profiled_at,
               -- merged, not replaced: the entity layer keeps its own keys here
               metadata=COALESCE(social_accounts.metadata, '{}'::jsonb) || EXCLUDED.metadata
        """), params)
        try:
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        return self.get_stored(db, row["platform"], row["handle_canonical"])

    _SELECT = ("id, platform, handle, handle_canonical, display_name, avatar_url, bio, profile_url, "
               "verified, followers_count, following_count, posts_count, account_created_at, topics, "
               "post_sentiment, summary, brand_context, sample_posts, tags, annotation, last_profiled_at, "
               "watchlisted, metadata")

    def _row_to_dict(self, r) -> Dict:
        keys = [c.strip() for c in self._SELECT.split(",")]
        return dict(zip(keys, r))

    def get_stored(self, db, platform: str, handle: str) -> Optional[Dict]:
        conn = db._temp_get_connection()
        canon = norm_handle(platform, handle)
        r = conn.execute(sql_text(f"SELECT {self._SELECT} FROM social_accounts "
                                  "WHERE platform=:p AND handle_canonical=:h"),
                         {"p": platform.lower(), "h": canon}).fetchone()
        return self._row_to_dict(r) if r else None

    def list_profiles(self, db, limit: int = 200) -> List[Dict]:
        conn = db._temp_get_connection()
        # Profiled or watched only. social_accounts also holds bare rows: every
        # post author on entity tenants, and accounts registered as a
        # company's own, which have no profile to show.
        rows = conn.execute(sql_text(f"SELECT {self._SELECT} FROM social_accounts "
                                     "WHERE last_profiled_at IS NOT NULL OR watchlisted "
                                     "ORDER BY watchlisted DESC, last_profiled_at DESC NULLS LAST "
                                     "LIMIT :lim"),
                            {"lim": limit}).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def set_watchlist(self, db, account_id: int, watchlisted: bool) -> Optional[Dict]:
        conn = db._temp_get_connection()
        conn.execute(sql_text("UPDATE social_accounts SET watchlisted=:w WHERE id=:id"),
                     {"w": bool(watchlisted), "id": account_id})
        try: conn.commit()
        except Exception: pass
        return self._by_id(db, account_id)

    def set_tags(self, db, account_id: int, tags: List[str]) -> Optional[Dict]:
        conn = db._temp_get_connection()
        conn.execute(sql_text("UPDATE social_accounts SET tags=CAST(:t AS jsonb) WHERE id=:id"),
                     {"t": json.dumps(tags or []), "id": account_id})
        try: conn.commit()
        except Exception: pass
        return self._by_id(db, account_id)

    def set_annotation(self, db, account_id: int, note_text: str, by: Optional[str]) -> Optional[Dict]:
        conn = db._temp_get_connection()
        ann = {"text": note_text, "by": by, "at": _now()} if note_text else None
        conn.execute(sql_text("UPDATE social_accounts SET annotation=CAST(:a AS jsonb) WHERE id=:id"),
                     {"a": json.dumps(ann) if ann else None, "id": account_id})
        try: conn.commit()
        except Exception: pass
        return self._by_id(db, account_id)

    def _by_id(self, db, account_id: int) -> Optional[Dict]:
        conn = db._temp_get_connection()
        r = conn.execute(sql_text(f"SELECT {self._SELECT} FROM social_accounts WHERE id=:id"),
                         {"id": account_id}).fetchone()
        return self._row_to_dict(r) if r else None

    def delete_profile(self, db, account_id: int) -> bool:
        conn = db._temp_get_connection()
        conn.execute(sql_text("DELETE FROM social_accounts WHERE id=:id"), {"id": account_id})
        try:
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        return True

    # ---- deep dive (on-demand deeper pull; no tracking cron) ---------------

    _CONN_FIELDS = {
        "twitter": ["username", "name", "followers_count"],
        "instagram": ["username", "full_name", "follower_count"],
    }

    def _deep_sync(self, platform: str, handle: str, cap: int) -> Optional[Dict]:
        from xpoz import XpozClient
        client = XpozClient(self.api_key, check_update=False)
        try:
            ns = getattr(client, platform, None)
            if ns is None:
                return None
            posts: List[Dict] = []
            if platform in _HAS_POST_HISTORY:
                try:
                    fetch = ns.get_posts_by_author if platform == "twitter" else ns.get_posts_by_user
                    res = fetch(handle, fields=_POST_FIELDS.get(platform), limit=cap)
                    posts = [self._map_post(platform, p) for p in (getattr(res, "data", None) or [])]
                    posts = [p for p in posts if p]
                except Exception as e:  # noqa: BLE001
                    logger.warning("deep post history (%s/%s) failed: %s", platform, handle, e)
            connections: List[Dict] = []
            if platform in self._CONN_FIELDS:
                try:
                    cres = ns.get_user_connections(handle, "following", fields=self._CONN_FIELDS[platform])
                    for u in (getattr(cres, "data", None) or [])[:24]:
                        connections.append({
                            "handle": getattr(u, "username", None),
                            "name": getattr(u, "name", None) or getattr(u, "full_name", None),
                            "followers": getattr(u, "followers_count", None) or getattr(u, "follower_count", None),
                        })
                except Exception as e:  # noqa: BLE001
                    logger.warning("connections (%s/%s) failed: %s", platform, handle, e)
            return {"posts": posts, "connections": connections}
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    async def deep_dive(self, db, platform: str, handle: str, brand: Optional[str] = None) -> Optional[Dict]:
        from collections import defaultdict
        platform = (platform or "").lower()
        if platform not in _PLATFORMS:
            raise ValueError(f"Unsupported platform '{platform}'")
        if not self.api_key:
            raise RuntimeError("Xpoz API key not configured")
        canon = norm_handle(platform, handle)
        cap = int(os.getenv("XPOZ_DEEP_MAX_RESULTS", "200"))
        if platform == "bluesky":
            fetched = await self._bluesky_fetch(canon, cap, with_conns=True)
            data = {"posts": fetched.get("posts", []), "connections": fetched.get("connections", [])} if fetched else None
        else:
            data = await asyncio.to_thread(self._deep_sync, platform, canon, cap)
        if not data:
            return None
        posts = data["posts"]
        byday = defaultdict(lambda: {"count": 0, "likes": 0})
        for p in posts:
            d = (p.get("created_at") or "")[:10]
            if not d:
                continue
            byday[d]["count"] += 1
            byday[d]["likes"] += (p.get("likes") or 0)
        timeline = [{"date": k, "count": v["count"], "likes": v["likes"]} for k, v in sorted(byday.items())]
        likes = [p.get("likes") or 0 for p in posts]
        comments = [p.get("comments") or 0 for p in posts]
        top = sorted(posts, key=lambda p: (p.get("likes") or 0), reverse=True)[:10]
        engagement = {
            "posts": len(posts),
            "total_likes": sum(likes), "total_comments": sum(comments),
            "avg_likes": round(sum(likes) / len(likes)) if likes else 0,
            "max_likes": max(likes) if likes else 0,
        }
        return {
            "platform": platform, "handle": canon, "brand": brand,
            "posts_analyzed": len(posts), "timeline": timeline,
            "engagement": engagement, "connections": data["connections"], "top_posts": top,
        }


def handle_of(u) -> str:
    return getattr(u, "username", None) or ""
