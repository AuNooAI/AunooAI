"""Deciding which public account belongs to which company.

This is the part of the system most likely to be confidently wrong, so it is
built to refuse rather than to guess.

A handle is not an identity. Handles are reused, abandoned, squatted and
impersonated, and two companies with similar names routinely hold accounts that
look like each other's. So an exact name or handle match may *propose* a
mapping and can never confirm one. Confirmation needs either a stable id from
the platform, a link from a domain we have already verified belongs to the
company, or a person saying so.

The stable id is also what survives a rename. An account that changes its
handle keeps its platform id, so it stays one identity with the old handle
recorded in history, instead of quietly becoming a second unmapped account
while the first goes silent.

Reddit gets an explicit exception. A subreddit named after a company is not the
company's account — it is frequently where its unhappiest customers gather —
so community names are recorded as communities and never as ownership.

Two companies claiming the same account as their own is never resolved
automatically. It becomes a high-severity review task, because whichever way it
is settled, someone's brand monitoring has been reading the wrong feed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services import entity_review

logger = logging.getLogger(__name__)

# Platforms whose provider records carry an id that outlives a rename.
STABLE_ID_PLATFORMS = frozenset({'bluesky', 'twitter', 'instagram', 'tiktok',
                                 'reddit', 'linkedin'})

# What a proposal is worth, before anyone confirms it.
CONFIDENCE = {
    'linked_from_domain': 0.9,
    'provider': 0.8,
    'manual': 1.0,
    'content_inference': 0.4,
}

# Methods allowed to mark a mapping verified without a person.
AUTO_VERIFIABLE = frozenset({'linked_from_domain', 'provider'})


def canonical_handle(handle: str) -> str:
    return (handle or '').strip().lstrip('@').lower()


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def upsert_account(conn, *, platform: str, handle: str,
                   platform_user_id: Optional[str] = None,
                   display_name: Optional[str] = None,
                   profile_url: Optional[str] = None,
                   seen_at: Optional[str] = None) -> Dict[str, Any]:
    """Find or create the account, following the stable id when there is one.

    Returns the account id and whether a rename was observed. A rename updates
    the existing row and keeps the previous handle in ``metadata`` rather than
    creating a second account for the same people.
    """
    canonical = canonical_handle(handle)
    result = {'account_id': None, 'created': False, 'renamed': False}

    existing = None
    if platform_user_id:
        existing = conn.execute(text("""
            SELECT id, handle, handle_canonical, metadata FROM social_accounts
             WHERE platform = :p AND platform_user_id = :uid
        """), {'p': platform, 'uid': str(platform_user_id)}).mappings().first()

    if existing is None:
        existing = conn.execute(text("""
            SELECT id, handle, handle_canonical, metadata FROM social_accounts
             WHERE platform = :p AND handle_canonical = :h
        """), {'p': platform, 'h': canonical}).mappings().first()

    if existing is None:
        row = conn.execute(text("""
            INSERT INTO social_accounts
                (platform, handle, handle_canonical, platform_user_id,
                 display_name, profile_url, identity_status, first_seen_at,
                 last_seen_at, metadata)
            VALUES (:p, :handle, :h, :uid, :dn, :url, 'provisional',
                    COALESCE(CAST(:seen AS TIMESTAMPTZ), NOW()),
                    COALESCE(CAST(:seen AS TIMESTAMPTZ), NOW()),
                    '{}'::jsonb)
            RETURNING id
        """), {'p': platform, 'handle': handle.strip(), 'h': canonical,
               'uid': str(platform_user_id) if platform_user_id else None,
               'dn': display_name, 'url': profile_url,
               'seen': seen_at}).fetchone()
        result.update(account_id=int(row[0]), created=True)
        return result

    account_id = int(existing['id'])
    result['account_id'] = account_id

    if canonical and existing['handle_canonical'] != canonical:
        # Same platform id, different handle: one account that renamed itself.
        metadata = existing['metadata'] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        history = list(metadata.get('handle_history') or [])
        history.append({'handle': existing['handle'],
                        'canonical': existing['handle_canonical']})
        metadata['handle_history'] = history
        conn.execute(text("""
            UPDATE social_accounts
               SET handle = :handle, handle_canonical = :h,
                   metadata = CAST(:meta AS JSONB), last_seen_at = NOW()
             WHERE id = :id
        """), {'handle': handle.strip(), 'h': canonical,
               'meta': json.dumps(metadata), 'id': account_id})
        result['renamed'] = True
    else:
        conn.execute(text("""
            UPDATE social_accounts SET last_seen_at = NOW(),
                   platform_user_id = COALESCE(platform_user_id, :uid),
                   first_seen_at = COALESCE(first_seen_at, NOW())
             WHERE id = :id
        """), {'id': account_id,
               'uid': str(platform_user_id) if platform_user_id else None})
    return result


# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------

def propose_identity(conn, *, brand_id: int, social_account_id: int,
                     relationship: str, verification_method: str,
                     provenance: Optional[Dict[str, Any]] = None,
                     confidence: Optional[float] = None,
                     actor: Optional[str] = None) -> Dict[str, Any]:
    """Propose, and where the evidence allows it, verify a mapping.

    Refuses in three cases: the same mapping was rejected before and nothing
    has changed, the relationship needs a person and none is named, or another
    company already claims the account as its own.
    """
    outcome = {'identity_id': None, 'status': None, 'reason': ''}

    rejected = conn.execute(text("""
        SELECT id FROM bw_entity_social_identities
         WHERE brand_id = :b AND social_account_id = :a
           AND relationship = :rel AND status = 'rejected'
         ORDER BY id DESC LIMIT 1
    """), {'b': brand_id, 'a': social_account_id,
           'rel': relationship}).fetchone()
    if rejected and verification_method != 'manual':
        outcome['reason'] = ('previously rejected; automatic proposal '
                             'suppressed until the evidence changes')
        return outcome

    # An executive or employee account is a claim about a person, and a name
    # match is not evidence about a person.
    if relationship in ('executive', 'employee') and verification_method != 'manual':
        outcome['reason'] = f'{relationship} mappings require manual confirmation'
        return outcome

    if relationship == 'owned_company':
        conflict = conn.execute(text("""
            SELECT brand_id FROM bw_entity_social_identities
             WHERE social_account_id = :a AND relationship = 'owned_company'
               AND valid_to IS NULL AND status IN ('proposed', 'verified')
               AND brand_id <> :b
        """), {'a': social_account_id, 'b': brand_id}).fetchall()
        if conflict:
            others = ', '.join(str(int(r[0])) for r in conflict)
            entity_review.open_task(
                conn, kind=entity_review.KIND_IDENTITY_CONFLICT,
                message=(f"social account {social_account_id} is claimed as "
                         f"owned by brand {brand_id} and by brand(s) {others}. "
                         f"Ownership cannot be decided automatically."),
                brand_id=brand_id, field='social_account', severity='high',
                source_ref={'social_account_id': social_account_id,
                            'competing_brand_ids': [int(r[0]) for r in conflict]})
            outcome['reason'] = 'ownership disputed; review task filed'
            outcome['status'] = 'disputed'
            return outcome

    auto_verified = verification_method in AUTO_VERIFIABLE
    status = 'verified' if auto_verified or verification_method == 'manual' else 'proposed'
    score = confidence if confidence is not None else CONFIDENCE.get(
        verification_method, 0.5)

    row = conn.execute(text("""
        INSERT INTO bw_entity_social_identities
            (brand_id, social_account_id, relationship, verification_method,
             confidence, status, provenance, verified_by, verified_at)
        VALUES (:b, :a, :rel, :m, :conf, :status, CAST(:prov AS JSONB),
                :actor, CASE WHEN :status = 'verified' THEN NOW() END)
        ON CONFLICT (brand_id, social_account_id, relationship)
        WHERE valid_to IS NULL DO NOTHING
        RETURNING id
    """), {'b': brand_id, 'a': social_account_id, 'rel': relationship,
           'm': verification_method, 'conf': score, 'status': status,
           'prov': json.dumps(provenance or {}), 'actor': actor}).fetchone()

    if row is None:
        outcome['reason'] = 'mapping already exists'
        return outcome
    outcome.update(identity_id=int(row[0]), status=status,
                   reason=f'{status} via {verification_method}')
    return outcome


def reject_identity(conn, identity_id: int, *, actor: str,
                    reason: str = '') -> None:
    """Reject a mapping and keep it, so the same guess is not made again."""
    conn.execute(text("""
        UPDATE bw_entity_social_identities
           SET status = 'rejected', valid_to = NOW(), verified_by = :actor,
               verified_at = NOW(), updated_at = NOW(),
               provenance = provenance || jsonb_build_object('rejected_reason', :reason)
         WHERE id = :id
    """), {'id': identity_id, 'actor': actor, 'reason': reason})


def verify_identity(conn, identity_id: int, *, actor: str) -> None:
    conn.execute(text("""
        UPDATE bw_entity_social_identities
           SET status = 'verified', verification_method = 'manual',
               confidence = 1.0, verified_by = :actor, verified_at = NOW(),
               updated_at = NOW()
         WHERE id = :id
    """), {'id': identity_id, 'actor': actor})


def identities_for(conn, brand_id: int) -> list:
    rows = conn.execute(text("""
        SELECT i.id, i.relationship, i.status, i.verification_method,
               i.confidence, a.platform, a.handle, a.platform_user_id,
               a.identity_status
          FROM bw_entity_social_identities i
          JOIN social_accounts a ON a.id = i.social_account_id
         WHERE i.brand_id = :b AND i.valid_to IS NULL
         ORDER BY i.relationship, a.platform
    """), {'b': brand_id}).mappings().all()
    return [dict(r) for r in rows]


def account_owner(conn, social_account_id: int) -> Optional[int]:
    """The entity that owns this account, if exactly one verified claim exists."""
    rows = conn.execute(text("""
        SELECT brand_id FROM bw_entity_social_identities
         WHERE social_account_id = :a AND relationship = 'owned_company'
           AND status = 'verified' AND valid_to IS NULL
    """), {'a': social_account_id}).fetchall()
    return int(rows[0][0]) if len(rows) == 1 else None
