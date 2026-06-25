#!/usr/bin/env python3
"""
Process articles for threat intelligence extraction.

Runs as a subprocess launched by the threat intelligence routes.
Writes progress to /tmp/threat_processing_status.json for polling.

Usage:
    python scripts/process_threat_articles.py --batch-size 100 --model gpt-4o-mini
    python scripts/process_threat_articles.py --topic "Threat Intelligence" --process-all
"""

import sys
import os
import json
import asyncio
import argparse
import logging
from pathlib import Path

# Set up path before importing app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
from dotenv import load_dotenv
load_dotenv()

from app.database import get_database_instance
from app.services.threat_intelligence_service import (
    get_threat_intelligence_service,
    extract_threat_with_llm,
    extract_iocs_from_text,
    is_placeholder_domain,
    is_placeholder_ip,
    is_valid_cve,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

STATUS_FILE = Path("/tmp/threat_processing_status.json")


def write_status(status: dict):
    """Write current processing status to file for the main app to read."""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logger.warning(f"Failed to write status file: {e}")


async def process_articles(batch_size: int, model: str, topic: str | None, process_all: bool):
    service = get_threat_intelligence_service()

    articles = service.get_unprocessed_articles(
        limit=batch_size,
        topic=topic,
        process_all=process_all,
    )

    if not articles:
        write_status({"running": False, "completed": True, "processed": 0, "total": 0,
                       "created": 0, "updated": 0, "message": "No articles to process"})
        logger.info("No articles to process")
        return

    status = {
        "running": True,
        "completed": False,
        "total": len(articles),
        "processed": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "last_error": None,
        "current_article": None,
        "actors_identified": 0,
        "iocs_extracted": 0,
        "message": f"Processing {len(articles)} articles...",
    }
    write_status(status)

    try:
        for i, article in enumerate(articles):
            try:
                status["current_article"] = (article.get('title') or '')[:100]
                write_status(status)

                await asyncio.sleep(0.3)

                result = await extract_threat_with_llm(
                    article['title'] or "",
                    article['summary'] or "",
                    article['category'] or "",
                    model,
                )

                if result.get('no_threat'):
                    status["skipped"] += 1
                    continue

                if not result.get('threat_name') or not result.get('threat_type'):
                    status["skipped"] += 1
                    continue

                threat_name = result.get('threat_name', '')
                if threat_name.upper().startswith('CVE-') and not is_valid_cve(threat_name):
                    logger.info(f"Skipping invalid CVE threat name: {threat_name}")
                    status["skipped"] += 1
                    continue

                # Extract IOCs from article text
                article_text = f"{article.get('title', '')} {article.get('summary', '')}"
                extracted_iocs = extract_iocs_from_text(article_text)

                # Filter LLM IOCs through blocklist
                llm_iocs = result.get('iocs', [])
                filtered_llm_iocs = []
                for ioc in llm_iocs:
                    ioc_type = ioc.get('type', '')
                    ioc_value = ioc.get('value', '')
                    if ioc_type == 'domain' and is_placeholder_domain(ioc_value):
                        continue
                    if ioc_type == 'ip' and is_placeholder_ip(ioc_value):
                        continue
                    if ioc_type == 'url':
                        try:
                            from urllib.parse import urlparse
                            parsed = urlparse(ioc_value)
                            if parsed.netloc and is_placeholder_domain(parsed.netloc):
                                continue
                        except Exception:
                            pass
                    if ioc_type == 'email' and '@' in ioc_value:
                        email_domain = ioc_value.split('@')[1]
                        if is_placeholder_domain(email_domain):
                            continue
                    filtered_llm_iocs.append(ioc)

                # Merge extracted IOCs
                existing_values = {(ioc.get('type'), ioc.get('value')) for ioc in filtered_llm_iocs}
                for ioc in extracted_iocs:
                    if (ioc['type'], ioc['value']) not in existing_values:
                        filtered_llm_iocs.append(ioc)

                result['iocs'] = filtered_llm_iocs
                if filtered_llm_iocs:
                    status["iocs_extracted"] += len(filtered_llm_iocs)

                # NER extraction (optional)
                try:
                    from app.utils.ner_extractor import extract_entities
                    ner_entities = extract_entities(article_text)
                    if ner_entities.get('organizations'):
                        result['ner_organizations'] = ner_entities['organizations']
                    if ner_entities.get('locations'):
                        result['ner_locations'] = ner_entities['locations']
                    if ner_entities.get('persons'):
                        result['ner_persons'] = ner_entities['persons']
                    if ner_entities.get('products'):
                        result['ner_products'] = ner_entities['products']
                except Exception:
                    pass

                # Check if threat already exists
                conn = get_database_instance().get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM threat_intel_threats WHERE threat_name = ?",
                    [result['threat_name']],
                )
                existing = cursor.fetchone()
                cursor.close()
                conn.close()

                is_new = existing is None

                threat_id = service.create_or_update_threat(result, topic=topic)
                service.link_article_to_threat(
                    threat_id,
                    article['uri'],
                    relevance_score=1.0,
                    mention_type='primary',
                )

                if is_new:
                    status["created"] += 1
                else:
                    status["updated"] += 1

                actor_name = result.get('threat_actor_name')
                invalid_actors = {'unknown', 'unidentified', 'unnamed', 'n/a', 'na', 'none', 'null', ''}
                if actor_name and actor_name.lower().strip() not in invalid_actors:
                    status["actors_identified"] += 1

                status["processed"] += 1
                logger.info(
                    f"Processed ({i+1}/{len(articles)}): "
                    f"{article['title'][:40]}... -> {result['threat_name']}"
                )

            except Exception as e:
                status["errors"] += 1
                status["last_error"] = str(e)
                logger.warning(f"Error processing article {article['uri']}: {e}")

        status["completed"] = True
        status["current_article"] = None
        status["message"] = (
            f"Completed: {status['processed']} processed, "
            f"{status['created']} created, {status['updated']} updated"
        )
        logger.info(f"Processing completed: {status}")

    except Exception as e:
        status["last_error"] = str(e)
        status["current_article"] = None
        status["message"] = f"Error: {str(e)}"
        logger.error(f"Processing error: {e}")

    finally:
        status["running"] = False
        write_status(status)


def main():
    parser = argparse.ArgumentParser(description="Process articles for threat intelligence")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--model", type=str, default="gpt-4o-mini")
    parser.add_argument("--topic", type=str, default=None)
    parser.add_argument("--process-all", action="store_true")
    args = parser.parse_args()

    asyncio.run(process_articles(
        batch_size=args.batch_size,
        model=args.model,
        topic=args.topic,
        process_all=args.process_all,
    ))


if __name__ == "__main__":
    main()
