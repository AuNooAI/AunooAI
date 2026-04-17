"""
Data Quality Audit Service

Spot-checks approved articles against their topic using an independent LLM call.
Two modes:
  A) Post-ingest sample audit — called after each auto-ingest batch
  B) Nightly quality report — samples across all topics from the last 24h
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

RELEVANCE_CHECK_PROMPT = """You are a strict relevance auditor. Given a topic and an article, determine whether the article is GENUINELY relevant to the topic — not just tangentially related.

Topic: {topic}
Article title: {title}
Article summary: {summary}

Rules:
- The article must be DIRECTLY about the topic, not merely mentioning a related word
- Generic news that happens to share a keyword is NOT relevant
- An article about a company launching a product is NOT relevant to a geopolitical topic just because the company operates internationally
- Be strict: when in doubt, say NO

Respond with ONLY a JSON object:
{{"relevant": true/false, "reason": "one sentence explaining why"}}"""


class DataQualityService:
    def __init__(self, db=None):
        self.db = db
        self._ai_model = None

    def _get_ai(self):
        if not self._ai_model:
            from app.ai_models import AIModelFactory
            self._ai_model = AIModelFactory.get_model()
        return self._ai_model

    def _check_single_article(self, topic: str, title: str, summary: str) -> Dict[str, Any]:
        """Ask LLM whether this article is genuinely relevant to the topic."""
        import json
        from app.ai_models import extract_content

        prompt = RELEVANCE_CHECK_PROMPT.format(
            topic=topic,
            title=title,
            summary=summary or "(no summary)"
        )

        try:
            ai = self._get_ai()
            response = ai.generate_sync(prompt, max_tokens=150, temperature=0.0)
            text = extract_content(response).strip()

            if text.startswith("```"):
                text = text.strip("`").strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            result = json.loads(text)
            return {
                "relevant": bool(result.get("relevant", False)),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error(f"Quality check LLM call failed: {e}")
            return {"relevant": None, "reason": f"LLM error: {e}"}

    def audit_batch(self, topic: str, approved_articles: List[Dict[str, Any]],
                    sample_size: int = 5) -> Dict[str, Any]:
        """
        Post-ingest sample audit (Mode A).

        Takes a list of just-approved articles, samples a few, and checks them.
        Returns a quality report. If failure rate exceeds threshold, logs a warning.
        """
        if not approved_articles or len(approved_articles) == 0:
            return {"sampled": 0, "passed": 0, "failed": 0, "error": 0, "pass_rate": 1.0}

        sample = random.sample(approved_articles, min(sample_size, len(approved_articles)))

        passed = 0
        failed = 0
        errors = 0
        failures = []

        for article in sample:
            result = self._check_single_article(
                topic,
                article.get("title", ""),
                article.get("summary", "")
            )
            if result["relevant"] is True:
                passed += 1
            elif result["relevant"] is False:
                failed += 1
                failures.append({
                    "title": article.get("title", "")[:100],
                    "reason": result["reason"],
                })
            else:
                errors += 1

        total_checked = passed + failed
        pass_rate = passed / total_checked if total_checked > 0 else 0.0

        report = {
            "topic": topic,
            "sampled": len(sample),
            "passed": passed,
            "failed": failed,
            "error": errors,
            "pass_rate": round(pass_rate, 2),
            "failures": failures,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if pass_rate < 0.6 and total_checked >= 3:
            logger.warning(
                f"DATA QUALITY ALERT: topic '{topic}' batch pass rate {pass_rate:.0%} "
                f"({failed}/{total_checked} failed). Failures: "
                + "; ".join(f['title'][:60] for f in failures)
            )

        return report

    def nightly_report(self, hours: int = 24, sample_per_topic: int = 10) -> Dict[str, Any]:
        """
        Nightly quality report (Mode B).

        Samples recent approved articles across all topics and produces
        a per-topic quality score.
        """
        if not self.db:
            raise ValueError("Database connection required for nightly report")

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT topic FROM articles
                WHERE ingest_status = 'approved'
                  AND submission_date >= :cutoff
                  AND topic IS NOT NULL AND topic != ''
            """, {"cutoff": cutoff})
            topics = [row[0] for row in cursor.fetchall()]

        topic_reports = []
        overall_passed = 0
        overall_failed = 0
        alerts = []

        for topic in topics:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT title, summary FROM articles
                    WHERE ingest_status = 'approved'
                      AND topic = :topic
                      AND submission_date >= :cutoff
                      AND category IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT :limit
                """, {"topic": topic, "cutoff": cutoff, "limit": sample_per_topic})
                rows = cursor.fetchall()

            if not rows:
                continue

            articles = [{"title": r[0], "summary": r[1]} for r in rows]
            report = self.audit_batch(topic, articles, sample_size=len(articles))
            topic_reports.append(report)

            overall_passed += report["passed"]
            overall_failed += report["failed"]

            if report["pass_rate"] < 0.6 and (report["passed"] + report["failed"]) >= 3:
                alerts.append(f"{topic}: {report['pass_rate']:.0%} pass rate")

        overall_total = overall_passed + overall_failed
        overall_rate = overall_passed / overall_total if overall_total > 0 else 0.0

        summary = {
            "run_at": datetime.utcnow().isoformat(),
            "hours_checked": hours,
            "topics_audited": len(topic_reports),
            "total_sampled": sum(r["sampled"] for r in topic_reports),
            "overall_pass_rate": round(overall_rate, 2),
            "alerts": alerts,
            "topic_reports": topic_reports,
        }

        if alerts:
            logger.warning(
                f"NIGHTLY QUALITY REPORT: {len(alerts)} topic(s) below threshold: "
                + ", ".join(alerts)
            )
        else:
            logger.info(
                f"NIGHTLY QUALITY REPORT: {len(topic_reports)} topics audited, "
                f"overall pass rate {overall_rate:.0%}"
            )

        return summary
