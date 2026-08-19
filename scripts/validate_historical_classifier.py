#!/usr/bin/env python3
"""Decide whether the E5 historical classifier may be trusted to set labels.

This is the authorization gate. It does not tune anything and it does not
deploy anything — it measures the shadow decisions the pipeline has already
recorded against a labelled set, and answers one question: may
``EMERGING_TOPICS_HISTORICAL_MODE`` move from ``shadow`` to ``enforce``?

The gate, all of which must hold, reported per tenant and never pooled:

1. Precision on "ongoing" at or above 95%. This is the direction that matters:
   a topic wrongly called ongoing is dropped from new-topic alerts, and an
   alert that never fires is invisible. Recall is reported but does not gate.
2. Zero adversarial topics classified ongoing. Not a rate — a count. The
   adversarial cases are invented topics that cannot have prior coverage, so a
   single one passing means the classifier is matching on something other than
   the topic.
3. At least 100 shadow decisions, spanning at least 7 days. A hundred decisions
   gathered in an afternoon only samples one day's corpus.
4. One algorithm version and one model revision across the decisions being
   judged. Pooling two versions measures neither.

Usage:
    python scripts/validate_historical_classifier.py --labels eval/historical_labels.json
    python scripts/validate_historical_classifier.py --labels ... --json report.json

Exit code is 0 only when every criterion passes for the tenant it ran on.
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_historical")

MIN_ONGOING_PRECISION = 0.95
MAX_ADVERSARIAL_ONGOING = 0
MIN_DECISIONS = 100
MIN_SPAN_DAYS = 7

# Labels a case may carry.
LABEL_ONGOING = "ongoing"          # known to have prior coverage
LABEL_NEW = "new"                  # genuinely new; must not be called ongoing
LABEL_ADVERSARIAL = "adversarial"  # invented; must never be called ongoing
LABELS = (LABEL_ONGOING, LABEL_NEW, LABEL_ADVERSARIAL)


def load_labels(path):
    """Read the labelled set: {"tenant": ..., "cases": [{topic_label, label}]}."""
    with open(path) as handle:
        data = json.load(handle)

    cases = data.get("cases") or []
    if not cases:
        raise SystemExit(f"{path} contains no cases")

    by_label = Counter(c.get("label") for c in cases)
    unknown = set(by_label) - set(LABELS)
    if unknown:
        raise SystemExit(f"{path} uses unknown labels: {sorted(unknown)}")
    missing = [l for l in LABELS if not by_label.get(l)]
    if missing:
        raise SystemExit(
            f"{path} has no cases labelled {missing}. The set must be stratified: "
            "known-ongoing, genuinely-new, and adversarial are each required, or "
            "the gate measures nothing."
        )

    logger.info("labelled set: %s", dict(by_label))
    return {str(c["topic_label"]).strip().lower(): c["label"] for c in cases}


def fetch_shadow_decisions(conn):
    """Every recorded shadow decision, newest first."""
    return conn.execute(text("""
        SELECT topic_label,
               historical_shadow->>'would_be'          AS would_be,
               historical_shadow->>'algorithm_version' AS algorithm_version,
               historical_shadow->>'model_revision'    AS model_revision,
               historical_shadow->>'decided_at'        AS decided_at,
               topic_filter
        FROM emerging_topics
        WHERE historical_shadow ? 'would_be'
        ORDER BY historical_shadow->>'decided_at' DESC
    """)).mappings().all()


def evaluate(decisions, labels, tenant):
    """Score the decisions we have labels for, and apply the gate."""
    matched = []
    for row in decisions:
        key = (row["topic_label"] or "").strip().lower()
        if key in labels:
            matched.append({**dict(row), "label": labels[key]})

    report = {
        "tenant": tenant,
        "decisions_total": len(decisions),
        "decisions_labelled": len(matched),
        "failures": [],
    }

    versions = {m["algorithm_version"] for m in matched if m["algorithm_version"]}
    revisions = {m["model_revision"] for m in matched if m["model_revision"]}
    report["algorithm_versions"] = sorted(versions)
    report["model_revisions"] = sorted(revisions)

    stamps = sorted(m["decided_at"] for m in matched if m["decided_at"])
    span_days = 0.0
    if len(stamps) >= 2:
        from datetime import datetime
        try:
            span_days = (
                datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])
            ).total_seconds() / 86400.0
        except ValueError:
            span_days = 0.0
    report["span_days"] = round(span_days, 2)

    called_ongoing = [m for m in matched if m["would_be"] == "ongoing"]
    true_ongoing = [m for m in called_ongoing if m["label"] == LABEL_ONGOING]
    adversarial_ongoing = [m for m in called_ongoing if m["label"] == LABEL_ADVERSARIAL]
    new_called_ongoing = [m for m in called_ongoing if m["label"] == LABEL_NEW]

    precision = (len(true_ongoing) / len(called_ongoing)) if called_ongoing else None
    actually_ongoing = [m for m in matched if m["label"] == LABEL_ONGOING]
    recall = (
        len(true_ongoing) / len(actually_ongoing) if actually_ongoing else None
    )

    report["ongoing_calls"] = len(called_ongoing)
    report["ongoing_precision"] = round(precision, 4) if precision is not None else None
    report["ongoing_recall"] = round(recall, 4) if recall is not None else None
    report["adversarial_called_ongoing"] = len(adversarial_ongoing)
    report["new_called_ongoing"] = len(new_called_ongoing)
    report["adversarial_examples"] = [m["topic_label"] for m in adversarial_ongoing[:5]]

    # The gate.
    if len(matched) < MIN_DECISIONS:
        report["failures"].append(
            f"only {len(matched)} labelled shadow decisions, need {MIN_DECISIONS}"
        )
    if span_days < MIN_SPAN_DAYS:
        report["failures"].append(
            f"decisions span {span_days:.1f} days, need {MIN_SPAN_DAYS}"
        )
    if len(versions) > 1:
        report["failures"].append(
            f"decisions mix algorithm versions {sorted(versions)}; rerun on one"
        )
    if len(revisions) > 1:
        report["failures"].append(
            f"decisions mix model revisions {sorted(revisions)}; rerun on one"
        )
    if not versions or not revisions:
        report["failures"].append(
            "decisions are missing an algorithm version or model revision stamp"
        )
    if precision is None:
        report["failures"].append("the classifier never said ongoing; nothing to judge")
    elif precision < MIN_ONGOING_PRECISION:
        report["failures"].append(
            f"ongoing precision {precision:.1%} below {MIN_ONGOING_PRECISION:.0%}"
        )
    if len(adversarial_ongoing) > MAX_ADVERSARIAL_ONGOING:
        report["failures"].append(
            f"{len(adversarial_ongoing)} adversarial topic(s) called ongoing; "
            "the limit is zero"
        )

    report["passed"] = not report["failures"]
    return report


def print_report(report):
    logger.info("")
    logger.info("=== %s ===", report["tenant"])
    logger.info("shadow decisions recorded : %s", report["decisions_total"])
    logger.info("matched against labels    : %s", report["decisions_labelled"])
    logger.info("spanning                  : %s days", report["span_days"])
    logger.info("algorithm version(s)      : %s", report["algorithm_versions"] or "none")
    logger.info("model revision(s)         : %s", report["model_revisions"] or "none")
    logger.info("called ongoing            : %s", report["ongoing_calls"])
    logger.info("ongoing precision         : %s (gate %.0f%%)",
                f"{report['ongoing_precision']:.1%}"
                if report["ongoing_precision"] is not None else "n/a",
                MIN_ONGOING_PRECISION * 100)
    logger.info("ongoing recall            : %s (reported, not gated)",
                f"{report['ongoing_recall']:.1%}"
                if report["ongoing_recall"] is not None else "n/a")
    logger.info("adversarial called ongoing: %s (gate 0)",
                report["adversarial_called_ongoing"])
    if report["adversarial_examples"]:
        logger.info("  e.g. %s", ", ".join(report["adversarial_examples"]))
    logger.info("genuinely-new called ongoing: %s", report["new_called_ongoing"])

    if report["passed"]:
        logger.info("")
        logger.info("PASS — this tenant meets every criterion for enforce mode.")
    else:
        logger.info("")
        logger.info("NOT AUTHORIZED. Blocked by:")
        for failure in report["failures"]:
            logger.info("  - %s", failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, help="path to the labelled set")
    parser.add_argument("--json", help="also write the report as JSON here")
    args = parser.parse_args()

    labels = load_labels(args.labels)
    tenant = os.getenv("DB_NAME", "unknown")

    conn = get_database_instance()._temp_get_connection()
    try:
        decisions = fetch_shadow_decisions(conn)
        conn.commit()
    finally:
        conn.close()

    report = evaluate(decisions, labels, tenant)
    print_report(report)

    if args.json:
        with open(args.json, "w") as handle:
            json.dump(report, handle, indent=2)
        logger.info("report written to %s", args.json)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
