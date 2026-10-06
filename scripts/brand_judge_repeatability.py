#!/usr/bin/env python3
"""Repeatability of the brand judge on fixed evidence (docs/BRAND_RELEVANCE_SPEC.md,
"Relationship labels and model contract").

Runs the configured judge route N times on the captured cases that reach a
judge (a verified mention, no rule settles them), with the profile, rubric,
evidence and model fixed and decision reuse bypassed, and reports per case the
labels returned, whether they changed, and failures. Agreement is not accuracy.

    cd <site tree> && .venv/bin/python scripts/brand_judge_repeatability.py [--runs 3]
"""
import argparse
import collections
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--fixture", default="tests/fixtures/brand_relevance/captured_2026-10-06.json")
    a = ap.parse_args()
    from dotenv import load_dotenv; load_dotenv(".env")
    import logging; logging.disable(logging.WARNING)
    from app.services import brand_decision as bd, brand_profile as bp
    spec = importlib.util.spec_from_file_location("bpa", "scripts/brand_profile_apply.py")
    bpa = importlib.util.module_from_spec(spec); spec.loader.exec_module(bpa)
    cap = json.load(open(a.fixture))
    judges = bd.configured_judges()
    print(f"route: {bd.route_signature(judges)}; runs: {a.runs}")
    tally = collections.Counter()
    for case, block in cap["cases"].items():
        site = block["site"]
        rows = {r["display_name"]: dict(r) for r in cap["brands"][site]}
        add = json.load(open(f"eval/brand_relevance/profiles/{site}.json"))
        for name, sp in add["brands"].items():
            if name in rows:
                for col, (new, _) in bpa.plan_for(rows[name], sp).items():
                    rows[name][col] = new
        for r in block["rows"]:
            res = bp.resolve(list(rows.values()), r["topic"])
            if res.profile is None or bp.exclusion(res.profile, r):
                continue
            m = bp.detect_mention(res.profile, r)
            if not m.verified:
                continue
            q = bp.evidence_quality(r)
            labels = []
            for _ in range(a.runs):
                try:
                    lab, _reason, _model = judges[0](res.profile, r, m, q)
                except (bd.InvalidJudgment, bd.JudgeUnavailable) as e:
                    lab = f"FAILED({type(e).__name__})"
                labels.append(lab)
            changed = len(set(labels)) > 1
            tally["cases"] += 1; tally["changed"] += changed
            tally["failures"] += sum(1 for l in labels if l.startswith("FAILED"))
            print(f"{'CHANGED' if changed else 'stable '} {m.status:5} {labels}  {(r.get('original_title') or r['title'])[:70]}")
    print(f"\n{tally['cases']} cases x {a.runs} runs: {tally['changed']} changed label between runs, {tally['failures']} failed calls")


if __name__ == "__main__":
    main()
