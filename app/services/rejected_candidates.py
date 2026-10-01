"""Remember which candidate URLs a keyword group's relevance gate rejected.

The early relevance gate scores every candidate URL on every poll and keeps
no record. In seven days across eight sites it ran 112,332 times on 21,033
distinct URLs; 8,001 URLs were scored five or more times. Each evaluation
embeds the candidate, so this is compute, log volume, and inflated numbers
that hide real throughput.

The ledger is keyed by canonical URL, keyword group and gate version. A hit
under the current version returns the stored outcome without embedding. The
version is derived from the group's terms, the threshold and the gate
implementation, so changing any of them invalidates the entries without a
sweep. Entries older than the retention window (30 days, the longest
provider look-back) are dropped by ``prune``.

The ledger only answers for the keyword route. An RSS feed or a manual
submission that passes its own gate stores the article whatever this says.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 19.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import text

from app.collectors.url_identity import canonical_url

logger = logging.getLogger(__name__)

#: Bump when the gate's scoring changes in a way that should re-score
#: previously rejected candidates.
GATE_IMPLEMENTATION_VERSION = "early_gate_v1"

RETENTION_DAYS = int(os.getenv("REJECTED_CANDIDATE_RETENTION_DAYS", "30") or 30)


def enabled() -> bool:
    return (os.getenv("REJECTED_CANDIDATE_LEDGER", "1") or "1").strip().lower() not in (
        "0", "false", "no", "off")


def gate_version(terms: Iterable[str], threshold: Any, implementation: str = GATE_IMPLEMENTATION_VERSION) -> str:
    """A short stable hash of what decides a rejection: the group's terms,
    the threshold in force and the gate implementation."""
    norm = sorted({(t or "").strip().lower() for t in terms if t and str(t).strip()})
    seed = f"{implementation}|{threshold}|" + "\x1f".join(norm)
    return implementation + ":" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


@dataclass
class LedgerHit:
    canonical_url: str
    score: Optional[float]
    threshold: Optional[float]
    evaluated_at: Optional[datetime]


class RejectedCandidateLedger:
    def __init__(self, db):
        self.db = db

    def _conn(self):
        return self.db._temp_get_connection()

    def lookup(self, urls: Sequence[str], group_id: Optional[int], version: str) -> dict:
        """``{canonical_url: LedgerHit}`` for the URLs already rejected by
        this group under this gate version. Bumps the hit counter."""
        if not enabled() or group_id is None or not urls:
            return {}
        keys = {}
        for u in urls:
            cu = canonical_url(u)
            if cu:
                keys[cu] = u
        if not keys:
            return {}
        conn = None
        try:
            conn = self._conn()
            rows = conn.execute(text("""
                UPDATE rejected_candidates SET hits = hits + 1
                 WHERE group_id = :g AND gate_version = :v AND canonical_url = ANY(:urls)
                RETURNING canonical_url, score, threshold, evaluated_at
            """), {"g": int(group_id), "v": version, "urls": list(keys)}).fetchall()
            conn.commit()
            return {r[0]: LedgerHit(r[0], r[1], r[2], r[3]) for r in rows}
        except Exception as exc:  # noqa: BLE001
            logger.warning("rejected-candidate lookup failed: %s", exc)
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            return {}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def record(self, url: str, group_id: Optional[int], version: str, *, score: Optional[float],
               threshold: Optional[float]) -> None:
        if not enabled() or group_id is None:
            return
        cu = canonical_url(url)
        if not cu:
            return
        conn = None
        try:
            conn = self._conn()
            conn.execute(text("""
                INSERT INTO rejected_candidates (canonical_url, group_id, gate_version, score, threshold, evaluated_at)
                VALUES (:u, :g, :v, :s, :t, :now)
                ON CONFLICT (canonical_url, group_id) DO UPDATE SET
                    gate_version = EXCLUDED.gate_version, score = EXCLUDED.score,
                    threshold = EXCLUDED.threshold, evaluated_at = EXCLUDED.evaluated_at
            """), {"u": cu, "g": int(group_id), "v": version, "s": score, "t": threshold,
                   "now": datetime.now(timezone.utc)})
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("rejected-candidate record failed: %s", exc)
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def forget(self, url: str, group_id: Optional[int] = None) -> int:
        """Drop ledger entries for a URL (all groups unless one is given).
        Called when another route accepts the article, so a later keyword
        poll re-evaluates it rather than trusting a stale rejection."""
        cu = canonical_url(url)
        if not cu:
            return 0
        conn = None
        try:
            conn = self._conn()
            if group_id is None:
                res = conn.execute(text("DELETE FROM rejected_candidates WHERE canonical_url = :u"), {"u": cu})
            else:
                res = conn.execute(text("DELETE FROM rejected_candidates WHERE canonical_url = :u AND group_id = :g"),
                                   {"u": cu, "g": int(group_id)})
            conn.commit()
            return int(res.rowcount or 0)
        except Exception:  # noqa: BLE001
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def prune(self, retention_days: int = RETENTION_DAYS) -> int:
        conn = None
        try:
            conn = self._conn()
            res = conn.execute(text(
                "DELETE FROM rejected_candidates WHERE evaluated_at < NOW() - make_interval(days => :d)"),
                {"d": int(retention_days)})
            conn.commit()
            return int(res.rowcount or 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rejected-candidate prune failed: %s", exc)
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def stats(self) -> dict:
        conn = None
        try:
            conn = self._conn()
            row = conn.execute(text(
                "SELECT COUNT(*), COALESCE(SUM(hits), 0), MIN(evaluated_at), MAX(evaluated_at) FROM rejected_candidates"
            )).fetchone()
            return {"entries": int(row[0]), "hits": int(row[1]),
                    "oldest": row[2].isoformat() if row[2] else None,
                    "newest": row[3].isoformat() if row[3] else None}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
