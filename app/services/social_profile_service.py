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
                logger.warning("xpoz get_user(%s/%s) failed: %s", platform, handle, e)
                return None
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

    async def _summarize(self, ident: Dict, posts: List[Dict], brand: Optional[str]) -> Dict:
        try:
            from app.ai_models import LiteLLMModel
            model = LiteLLMModel.get_instance(os.getenv("SOCIAL_EVAL_MODEL", "bedrock-claude-haiku"))
        except Exception:
            model = None
        if not model:
            return {}
        sample = "\n".join(f"- {p['text'][:200]}" for p in posts[:12] if p.get("text")) or "(no post text available)"
        brand_line = f'The account is being profiled in the context of the brand "{brand}". ' if brand else ""
        sys = (
            "You are a brand-monitoring analyst. Given a social account's bio and recent posts, "
            "produce a compact, factual profile. Respond with ONLY a JSON object: "
            '{"summary": "<2-3 sentence plain description of who this account is and what they post about>", '
            '"topics": ["<3-6 short topic tags>"], '
            '"brand_context": "<1-2 sentences on this account\'s relationship to the brand, or \'No clear connection.\' >"}'
            " No prose outside the JSON."
        )
        usr = (f"{brand_line}ACCOUNT: @{ident.get('handle')} ({ident.get('platform')})\n"
               f"NAME: {ident.get('display_name') or ''}\nBIO: {ident.get('bio') or ''}\n\nRECENT POSTS:\n{sample}")
        try:
            from fastapi.concurrency import run_in_threadpool
            content = await run_in_threadpool(model.generate_response,
                                              [{"role": "system", "content": sys}, {"role": "user", "content": usr}])
            m = re.search(r"\{[\s\S]*\}", content or "")
            obj = json.loads(m.group()) if m else {}
            topics = obj.get("topics") or []
            if isinstance(topics, str):
                topics = [topics]
            return {"summary": obj.get("summary"), "topics": topics[:8],
                    "brand_context": obj.get("brand_context")}
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
                            max_posts: Optional[int] = None) -> Optional[Dict]:
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
        summary, sentiment = await asyncio.gather(
            self._summarize(ident, posts, brand), self._sentiment(posts, brand))
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
        }
        return self._upsert(db, row)

    def _upsert(self, db, row: Dict) -> Dict:
        conn = db._temp_get_connection()
        params = dict(row)
        for k in ("topics", "post_sentiment", "sample_posts"):
            params[k] = json.dumps(params.get(k)) if params.get(k) is not None else None
        params.setdefault("created_at", _now())
        conn.execute(sql_text("""
            INSERT INTO social_accounts
              (platform, handle, handle_canonical, display_name, avatar_url, bio, profile_url,
               verified, followers_count, following_count, posts_count, account_created_at,
               topics, post_sentiment, summary, brand_context, sample_posts, last_profiled_at, created_at)
            VALUES
              (:platform, :handle, :handle_canonical, :display_name, :avatar_url, :bio, :profile_url,
               :verified, :followers_count, :following_count, :posts_count, :account_created_at,
               CAST(:topics AS jsonb), CAST(:post_sentiment AS jsonb), :summary, :brand_context,
               CAST(:sample_posts AS jsonb), :last_profiled_at, :created_at)
            ON CONFLICT (platform, handle_canonical) DO UPDATE SET
               handle=EXCLUDED.handle, display_name=EXCLUDED.display_name, avatar_url=EXCLUDED.avatar_url,
               bio=EXCLUDED.bio, profile_url=EXCLUDED.profile_url, verified=EXCLUDED.verified,
               followers_count=EXCLUDED.followers_count, following_count=EXCLUDED.following_count,
               posts_count=EXCLUDED.posts_count, account_created_at=EXCLUDED.account_created_at,
               topics=EXCLUDED.topics, post_sentiment=EXCLUDED.post_sentiment, summary=EXCLUDED.summary,
               brand_context=EXCLUDED.brand_context, sample_posts=EXCLUDED.sample_posts,
               last_profiled_at=EXCLUDED.last_profiled_at
        """), params)
        try:
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        return self.get_stored(db, row["platform"], row["handle_canonical"])

    _SELECT = ("id, platform, handle, handle_canonical, display_name, avatar_url, bio, profile_url, "
               "verified, followers_count, following_count, posts_count, account_created_at, topics, "
               "post_sentiment, summary, brand_context, sample_posts, tags, annotation, last_profiled_at, "
               "watchlisted")

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
        rows = conn.execute(sql_text(f"SELECT {self._SELECT} FROM social_accounts "
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
