#!/usr/bin/env python3
"""
Summarization Comparison Test

Compares summarization quality across:
1. GPT-4o-mini (OpenAI LLM)
2. BART (local fine-tuned model)
3. Small LLM (Phi-3-mini or similar via LiteLLM)

Usage:
    python scripts/compare_summarizers.py [--count 10] [--topic "Topic Name"]
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database


def get_test_articles(db: Database, count: int = 10, topic: Optional[str] = None) -> List[Dict]:
    """Fetch articles with scraped content for testing.

    Joins articles table with raw_articles to get full scraped content.
    """
    params = {"count": count}

    if topic:
        query = """
            SELECT a.uri, a.title, a.summary, a.news_source, a.topic, r.raw_markdown
            FROM articles a
            JOIN raw_articles r ON a.uri = r.uri
            WHERE r.raw_markdown IS NOT NULL
              AND LENGTH(r.raw_markdown) > 500
              AND a.topic ILIKE :topic
            ORDER BY a.submission_date DESC LIMIT :count
        """
        params["topic"] = f"%{topic}%"
    else:
        query = """
            SELECT a.uri, a.title, a.summary, a.news_source, a.topic, r.raw_markdown
            FROM articles a
            JOIN raw_articles r ON a.uri = r.uri
            WHERE r.raw_markdown IS NOT NULL
              AND LENGTH(r.raw_markdown) > 500
            ORDER BY a.submission_date DESC LIMIT :count
        """

    results = db.fetch_all(query, params)

    articles = []
    for row in results:
        articles.append({
            "uri": row["uri"],
            "title": row["title"],
            "existing_summary": row["summary"],
            "content": row["raw_markdown"],
            "source": row["news_source"],
            "topic": row["topic"]
        })

    return articles


def summarize_with_gpt4mini(title: str, content: str) -> Dict:
    """Summarize using GPT-4o-mini."""
    try:
        from litellm import completion

        prompt = f"""Summarize the following article in 2-3 concise sentences.

Title: {title}

Content:
{content[:4000]}

Summary:"""

        start = time.time()
        response = completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3
        )
        elapsed = time.time() - start

        summary = response.choices[0].message.content.strip()

        return {
            "summary": summary,
            "model": "gpt-4o-mini",
            "time_seconds": round(elapsed, 2),
            "tokens": response.usage.total_tokens if response.usage else None
        }
    except Exception as e:
        return {"summary": f"ERROR: {e}", "model": "gpt-4o-mini", "time_seconds": 0}


def summarize_with_bart(title: str, content: str) -> Dict:
    """Summarize using local BART model."""
    try:
        from app.services.summarization_service import get_summarization_service

        service = get_summarization_service()
        if not service.is_available():
            return {"summary": "ERROR: BART model not available", "model": "bart-local", "time_seconds": 0}

        start = time.time()
        result = service.summarize(title=title, content=content)
        elapsed = time.time() - start

        return {
            "summary": result.get("summary", ""),
            "model": "bart-local",
            "source": result.get("source", "local"),
            "time_seconds": round(elapsed, 2)
        }
    except Exception as e:
        return {"summary": f"ERROR: {e}", "model": "bart-local", "time_seconds": 0}


def summarize_with_small_llm(title: str, content: str, model: str = "ollama/phi3:mini") -> Dict:
    """Summarize using a small LLM (Phi-3, Mistral, etc.)."""
    try:
        from litellm import completion

        prompt = f"""Summarize the following article in 2-3 concise sentences. Focus only on the main news content, ignore any website navigation, ads, or metadata.

Title: {title}

Content:
{content[:3000]}

Summary:"""

        start = time.time()
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3
        )
        elapsed = time.time() - start

        summary = response.choices[0].message.content.strip()

        return {
            "summary": summary,
            "model": model,
            "time_seconds": round(elapsed, 2)
        }
    except Exception as e:
        return {"summary": f"ERROR: {e}", "model": model, "time_seconds": 0}


def summarize_with_mistral(title: str, content: str) -> Dict:
    """Summarize using Mistral via Ollama."""
    return summarize_with_small_llm(title, content, model="ollama/mistral")


def print_comparison(article: Dict, results: Dict[str, Dict]):
    """Print a formatted comparison of summaries."""
    print("\n" + "=" * 100)
    print(f"ARTICLE: {article['title'][:80]}...")
    print(f"Source: {article['source']} | Topic: {article['topic']}")
    print(f"Content length: {len(article['content'])} chars")
    print("=" * 100)

    if article.get('existing_summary'):
        print(f"\n📄 EXISTING (database):")
        print(f"   {article['existing_summary'][:300]}...")

    for name, result in results.items():
        status = "✅" if not result['summary'].startswith("ERROR") else "❌"
        print(f"\n{status} {name.upper()} ({result.get('time_seconds', 0)}s):")
        summary = result['summary']
        # Word wrap at 90 chars
        words = summary.split()
        lines = []
        current_line = "   "
        for word in words:
            if len(current_line) + len(word) + 1 > 95:
                lines.append(current_line)
                current_line = "   " + word
            else:
                current_line += " " + word if current_line != "   " else word
        if current_line.strip():
            lines.append(current_line)
        print("\n".join(lines))


def run_comparison(
    count: int = 10,
    topic: Optional[str] = None,
    small_llm_model: str = "ollama/phi3:mini",
    output_file: Optional[str] = None
):
    """Run the full comparison."""
    print(f"\n🔬 Summarization Comparison Test")
    print(f"   Articles: {count}")
    print(f"   Topic filter: {topic or 'None'}")
    print(f"   Small LLM: {small_llm_model}")
    print("-" * 50)

    # Get articles
    db = Database()
    articles = get_test_articles(db, count, topic)

    if not articles:
        print("❌ No articles found with content. Try a different topic or check database.")
        return

    print(f"✅ Found {len(articles)} articles with content")

    # Run comparisons
    all_results = []

    for i, article in enumerate(articles, 1):
        print(f"\n[{i}/{len(articles)}] Processing: {article['title'][:50]}...")

        results = {}

        # GPT-4o-mini
        print("   → GPT-4o-mini...", end=" ", flush=True)
        results["gpt-4o-mini"] = summarize_with_gpt4mini(article['title'], article['content'])
        print(f"done ({results['gpt-4o-mini']['time_seconds']}s)")

        # BART
        print("   → BART...", end=" ", flush=True)
        results["bart"] = summarize_with_bart(article['title'], article['content'])
        print(f"done ({results['bart']['time_seconds']}s)")

        # Phi3
        print(f"   → {small_llm_model}...", end=" ", flush=True)
        results["phi3"] = summarize_with_small_llm(article['title'], article['content'], small_llm_model)
        print(f"done ({results['phi3']['time_seconds']}s)")

        # Mistral
        print("   → ollama/mistral...", end=" ", flush=True)
        results["mistral"] = summarize_with_mistral(article['title'], article['content'])
        print(f"done ({results['mistral']['time_seconds']}s)")

        # Print comparison
        print_comparison(article, results)

        # Store for output
        all_results.append({
            "article": {
                "uri": article['uri'],
                "title": article['title'],
                "source": article['source'],
                "topic": article['topic'],
                "content_length": len(article['content']),
                "existing_summary": article.get('existing_summary')
            },
            "summaries": results
        })

    # Summary statistics
    print("\n" + "=" * 100)
    print("📊 SUMMARY STATISTICS")
    print("=" * 100)

    for model in ["gpt-4o-mini", "bart", "phi3", "mistral"]:
        times = [r["summaries"][model]["time_seconds"] for r in all_results
                 if not r["summaries"][model]["summary"].startswith("ERROR")]
        errors = sum(1 for r in all_results if r["summaries"][model]["summary"].startswith("ERROR"))

        if times:
            avg_time = sum(times) / len(times)
            print(f"\n{model}:")
            print(f"   Success: {len(times)}/{len(all_results)}")
            print(f"   Avg time: {avg_time:.2f}s")
            print(f"   Total time: {sum(times):.2f}s")
        else:
            print(f"\n{model}: All {errors} attempts failed")

    # Save results to file
    if output_file:
        output_path = Path(output_file)
        with open(output_path, 'w') as f:
            json.dump(all_results, f, indent=2)
        print(f"\n💾 Results saved to: {output_path}")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Compare summarization methods")
    parser.add_argument("--count", "-n", type=int, default=10, help="Number of articles to test")
    parser.add_argument("--topic", "-t", type=str, help="Filter by topic name")
    parser.add_argument("--small-llm", type=str, default="ollama/phi3:mini",
                        help="Small LLM model to use (default: ollama/phi3:mini)")
    parser.add_argument("--output", "-o", type=str, help="Save results to JSON file")

    args = parser.parse_args()

    run_comparison(
        count=args.count,
        topic=args.topic,
        small_llm_model=args.small_llm,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
