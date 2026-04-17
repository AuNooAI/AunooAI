#!/usr/bin/env python3
"""
Nightly Data Quality Report

Samples approved articles from the last 24h across all topics,
independently verifies relevance via LLM, and reports per-topic
quality scores. Topics with pass rate below 60% are flagged.

Usage:
    python scripts/nightly_quality_report.py [--hours 24] [--samples 10]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database
from app.services.data_quality_service import DataQualityService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger("quality-report")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default 24)")
    parser.add_argument("--samples", type=int, default=10, help="Articles to sample per topic (default 10)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted report")
    args = parser.parse_args()

    db = Database()
    dqs = DataQualityService(db)
    report = dqs.nightly_report(hours=args.hours, sample_per_topic=args.samples)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("=" * 70)
    print(f"DATA QUALITY REPORT — last {args.hours}h")
    print(f"Run at: {report['run_at']}")
    print(f"Topics audited: {report['topics_audited']}")
    print(f"Total sampled: {report['total_sampled']}")
    print(f"Overall pass rate: {report['overall_pass_rate']:.0%}")
    print("=" * 70)

    if report['alerts']:
        print(f"\n{'!'*3} ALERTS {'!'*3}")
        for alert in report['alerts']:
            print(f"  {alert}")

    print(f"\n{'Topic':<50} {'Pass Rate':>10} {'P/F/E':>10}")
    print("-" * 70)

    for tr in sorted(report['topic_reports'], key=lambda x: x['pass_rate']):
        pfe = f"{tr['passed']}/{tr['failed']}/{tr['error']}"
        rate = f"{tr['pass_rate']:.0%}"
        flag = " !!!" if tr['pass_rate'] < 0.6 and (tr['passed'] + tr['failed']) >= 3 else ""
        print(f"{tr['topic']:<50} {rate:>10} {pfe:>10}{flag}")

        if tr.get('failures'):
            for f in tr['failures']:
                print(f"    FAIL: {f['title'][:60]}")
                print(f"          {f['reason']}")

    print()


if __name__ == "__main__":
    main()
