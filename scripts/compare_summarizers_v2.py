#!/usr/bin/env python3
"""
Summarization Comparison V2 - Tests combinations and more models
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database


def get_test_articles(db, count=5):
    """Fetch articles with scraped content."""
    query = """
        SELECT a.uri, a.title, a.summary, a.news_source, a.topic, r.raw_markdown
        FROM articles a
        JOIN raw_articles r ON a.uri = r.uri
        WHERE r.raw_markdown IS NOT NULL
          AND LENGTH(r.raw_markdown) > 500
        ORDER BY a.submission_date DESC LIMIT :count
    """
    results = db.fetch_all(query, {"count": count})
    return [{"uri": r["uri"], "title": r["title"], "content": r["raw_markdown"],
             "existing": r["summary"], "source": r["news_source"]} for r in results]


def summarize_gpt4mini(title, content):
    from litellm import completion
    start = time.time()
    resp = completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Summarize in 2-3 sentences:\n\nTitle: {title}\n\nContent:\n{content[:4000]}\n\nSummary:"}],
        max_tokens=200, temperature=0.3
    )
    return {"summary": resp.choices[0].message.content.strip(), "time": round(time.time() - start, 2)}


def summarize_bart(title, content):
    from app.services.summarization_service import get_summarization_service
    svc = get_summarization_service()
    if not svc.is_available():
        return {"summary": "BART not available", "time": 0}
    start = time.time()
    result = svc.summarize(title=title, content=content)
    return {"summary": result.get("summary", ""), "time": round(time.time() - start, 2)}


def summarize_ollama(title, content, model):
    from litellm import completion
    start = time.time()
    resp = completion(
        model=f"ollama/{model}",
        messages=[{"role": "user", "content": f"Summarize this article in 2-3 concise sentences. Focus only on the news content.\n\nTitle: {title}\n\nContent:\n{content[:3000]}\n\nSummary:"}],
        max_tokens=200, temperature=0.3
    )
    return {"summary": resp.choices[0].message.content.strip(), "time": round(time.time() - start, 2)}


def summarize_bart_then_llm(title, content, llm_model="phi3"):
    """BART generates draft, LLM refines it."""
    from litellm import completion

    # Step 1: BART draft
    bart_result = summarize_bart(title, content)
    bart_summary = bart_result["summary"]

    # Step 2: LLM polish
    start = time.time()
    resp = completion(
        model=f"ollama/{llm_model}",
        messages=[{"role": "user", "content": f"Improve this summary to be more natural and informative. Keep it to 2-3 sentences:\n\nOriginal summary: {bart_summary}\n\nImproved summary:"}],
        max_tokens=200, temperature=0.3
    )

    return {
        "summary": resp.choices[0].message.content.strip(),
        "time": round(bart_result["time"] + time.time() - start, 2),
        "bart_draft": bart_summary
    }


def main():
    db = Database()
    articles = get_test_articles(db, count=5)
    print(f"\n{'='*90}")
    print(f"SUMMARIZATION COMPARISON V2 - {len(articles)} articles")
    print(f"{'='*90}\n")

    models = {
        "gpt-4o-mini": lambda t, c: summarize_gpt4mini(t, c),
        "bart": lambda t, c: summarize_bart(t, c),
        "phi3": lambda t, c: summarize_ollama(t, c, "phi3"),
        "phi4": lambda t, c: summarize_ollama(t, c, "phi4"),
        "llama3.1:8b": lambda t, c: summarize_ollama(t, c, "llama3.1:8b"),
        "gemma3": lambda t, c: summarize_ollama(t, c, "gemma3"),
        "qwen3": lambda t, c: summarize_ollama(t, c, "qwen3"),
        "bart+phi3": lambda t, c: summarize_bart_then_llm(t, c, "phi3"),
        "bart+llama3.1": lambda t, c: summarize_bart_then_llm(t, c, "llama3.1:8b"),
    }

    all_times = {m: [] for m in models}

    for i, article in enumerate(articles, 1):
        print(f"\n{'='*90}")
        print(f"ARTICLE {i}: {article['title'][:70]}...")
        print(f"Source: {article['source']} | Content: {len(article['content'])} chars")
        print(f"{'='*90}")

        print(f"\n📄 EXISTING: {article['existing'][:150]}..." if article['existing'] else "")

        for name, func in models.items():
            try:
                print(f"\n→ {name}...", end=" ", flush=True)
                result = func(article["title"], article["content"])
                print(f"({result['time']}s)")
                all_times[name].append(result["time"])

                # Truncate for display
                summary = result["summary"][:300]
                if len(result["summary"]) > 300:
                    summary += "..."
                print(f"  {summary}")

                if "bart_draft" in result:
                    print(f"  [BART draft: {result['bart_draft'][:100]}...]")

            except Exception as e:
                print(f"ERROR: {e}")
                all_times[name].append(0)

    print(f"\n{'='*90}")
    print("TIMING SUMMARY")
    print(f"{'='*90}")
    for name, times in all_times.items():
        valid = [t for t in times if t > 0]
        if valid:
            print(f"{name:15} | Avg: {sum(valid)/len(valid):.2f}s | Total: {sum(valid):.2f}s")


if __name__ == "__main__":
    main()
