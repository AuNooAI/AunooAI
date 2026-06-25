#!/usr/bin/env python3
"""
Test SLM (Phi-3) for generating article analysis explanations.

Tests whether Phi-3 can generate quality explanations for:
- sentiment_explanation
- time_to_impact_explanation
- driver_type_explanation
- future_signal_explanation

Usage:
    python scripts/test_slm_explanations.py
"""

import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# vLLM Configuration
VLLM_BASE_URL = "http://localhost:8765/v1"
VLLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"  # Can also use: Qwen/Qwen2.5-7B-Instruct, microsoft/Phi-3-mini-4k-instruct

# Test articles with known classifications
TEST_ARTICLES = [
    {
        "title": "OpenAI Announces GPT-5 with Revolutionary Reasoning Capabilities",
        "summary": "OpenAI has unveiled GPT-5, featuring breakthrough reasoning abilities that surpass human performance on complex problem-solving tasks. The model demonstrates unprecedented accuracy in scientific research, coding, and mathematical proofs.",
        "sentiment": "Positive",
        "time_to_impact": "0-6 months",
        "driver_type": "Technology",
        "future_signal": "Emerging Trend",
    },
    {
        "title": "Major Tech Layoffs Continue as AI Automation Replaces Jobs",
        "summary": "Several major technology companies announced another round of layoffs this week, citing AI automation as the primary driver. Industry analysts warn that white-collar jobs are increasingly at risk as AI capabilities expand.",
        "sentiment": "Negative",
        "time_to_impact": "0-6 months",
        "driver_type": "Economic",
        "future_signal": "Accelerating Trend",
    },
    {
        "title": "EU Passes Comprehensive AI Regulation Framework",
        "summary": "The European Union has finalized its AI Act, establishing strict requirements for high-risk AI systems. Companies will have 24 months to comply with the new regulations, which include mandatory transparency and safety assessments.",
        "sentiment": "Neutral",
        "time_to_impact": "1-2 years",
        "driver_type": "Regulatory",
        "future_signal": "Established Trend",
    },
    {
        "title": "Climate Scientists Warn of Accelerating Arctic Ice Melt",
        "summary": "New satellite data reveals Arctic ice is melting 40% faster than previous models predicted. Scientists warn this could trigger cascading effects on global weather patterns and sea levels within the decade.",
        "sentiment": "Negative",
        "time_to_impact": "2-5 years",
        "driver_type": "Environmental",
        "future_signal": "Accelerating Trend",
    },
]


def check_vllm_available():
    """Check if vLLM server is running."""
    try:
        import requests
        response = requests.get(f"{VLLM_BASE_URL}/models", timeout=5)
        if response.status_code == 200:
            models = response.json().get("data", [])
            for model in models:
                if VLLM_MODEL in model.get("id", ""):
                    return True
        return False
    except Exception as e:
        print(f"vLLM check failed: {e}")
        return False


def generate_explanations_slm(article: dict) -> dict:
    """Generate all explanations using Phi-3 via vLLM.

    The classifier gives labels but no reasoning, so the explanation service
    must review the article and justify WHY the classification makes sense.
    """
    from litellm import completion

    title = article["title"]
    summary = article["summary"]

    prompt = f"""Analyze this article and explain what indicates each classification. Write brief explanations (1-2 sentences) that help a reader understand the analysis.

Article Title: {title}

Article Summary: {summary}

Classifications:
- Sentiment: {article['sentiment']}
- Time to Impact: {article['time_to_impact']}
- Driver Type: {article['driver_type']}
- Future Signal: {article['future_signal']}

For each, explain what in the article indicates this. Be specific - reference key phrases or facts.

Respond in JSON format only:
{{
  "sentiment_explanation": "What language or implications indicate {article['sentiment']} sentiment",
  "time_to_impact_explanation": "What suggests the {article['time_to_impact']} timeframe",
  "driver_type_explanation": "What makes {article['driver_type']} the primary driver",
  "future_signal_explanation": "What indicates this is an {article['future_signal']}"
}}"""

    start_time = time.time()

    response = completion(
        model=f"openai/{VLLM_MODEL}",
        api_base=VLLM_BASE_URL,
        messages=[
            {"role": "system", "content": "You are a news analyst. Provide concise, insightful explanations for article classifications. Output valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400,
        temperature=0.3,
    )

    latency_ms = int((time.time() - start_time) * 1000)
    response_text = response.choices[0].message.content.strip()

    # Parse JSON response
    result = parse_json_response(response_text)
    result["latency_ms"] = latency_ms
    result["raw_response"] = response_text

    return result


def generate_explanations_llm(article: dict) -> dict:
    """Generate explanations using external LLM (gpt-4o-mini) for comparison."""
    from litellm import completion

    title = article["title"]
    summary = article["summary"]

    prompt = f"""Analyze this article and explain what indicates each classification. Write brief explanations (1-2 sentences) that help a reader understand the analysis.

Article Title: {title}

Article Summary: {summary}

Classifications:
- Sentiment: {article['sentiment']}
- Time to Impact: {article['time_to_impact']}
- Driver Type: {article['driver_type']}
- Future Signal: {article['future_signal']}

For each, explain what in the article indicates this. Be specific - reference key phrases or facts.

Respond in JSON format only:
{{
  "sentiment_explanation": "What language or implications indicate {article['sentiment']} sentiment",
  "time_to_impact_explanation": "What suggests the {article['time_to_impact']} timeframe",
  "driver_type_explanation": "What makes {article['driver_type']} the primary driver",
  "future_signal_explanation": "What indicates this is an {article['future_signal']}"
}}"""

    start_time = time.time()

    response = completion(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a news analyst. Provide concise, insightful explanations for article classifications. Output valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400,
        temperature=0.3,
    )

    latency_ms = int((time.time() - start_time) * 1000)
    response_text = response.choices[0].message.content.strip()

    # Parse JSON response
    result = parse_json_response(response_text)
    result["latency_ms"] = latency_ms
    result["raw_response"] = response_text

    return result


def parse_json_response(response_text: str) -> dict:
    """Parse JSON response, handling common formatting issues."""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code block
    if "```" in response_text:
        try:
            json_str = response_text.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            pass

    # Try to find JSON object in response
    try:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response_text[start:end])
    except json.JSONDecodeError:
        pass

    return {"error": "Failed to parse JSON", "raw": response_text[:200]}


def evaluate_explanation_quality(explanation: str) -> dict:
    """Basic quality metrics for an explanation."""
    if not explanation or not isinstance(explanation, str):
        return {"valid": False, "word_count": 0, "has_reasoning": False}

    word_count = len(explanation.split())
    # Check for reasoning indicators
    reasoning_words = ["because", "since", "due to", "as", "given", "indicates", "suggests", "reflects", "demonstrates"]
    has_reasoning = any(word in explanation.lower() for word in reasoning_words)

    return {
        "valid": True,
        "word_count": word_count,
        "has_reasoning": has_reasoning,
        "appropriate_length": 10 <= word_count <= 50,
    }


def main():
    print("=" * 70)
    print("SLM Explanation Generation Test")
    print("=" * 70)

    # Check vLLM availability
    if not check_vllm_available():
        print("\n❌ vLLM server not available at", VLLM_BASE_URL)
        print("Start vLLM with: python -m vllm.entrypoints.openai.api_server \\")
        print(f"    --model {VLLM_MODEL} --port 8765")
        return

    print(f"\n✅ vLLM available: {VLLM_MODEL}")
    print("\nTesting explanation generation...\n")

    results = []

    for i, article in enumerate(TEST_ARTICLES, 1):
        print(f"\n{'='*70}")
        print(f"Article {i}: {article['title'][:60]}...")
        print(f"{'='*70}")

        # Test SLM (Phi-3)
        print("\n📝 SLM (Phi-3) Explanations:")
        try:
            slm_result = generate_explanations_slm(article)
            slm_latency = slm_result.get("latency_ms", 0)

            for field in ["sentiment_explanation", "time_to_impact_explanation",
                         "driver_type_explanation", "future_signal_explanation"]:
                explanation = slm_result.get(field, "N/A")
                quality = evaluate_explanation_quality(explanation)
                print(f"  {field}:")
                print(f"    → {explanation}")
                print(f"    Quality: {quality['word_count']} words, reasoning: {quality['has_reasoning']}")

            print(f"  ⏱️ Latency: {slm_latency}ms")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            slm_result = {"error": str(e)}
            slm_latency = 0

        # Test LLM (gpt-4o-mini) for comparison
        print("\n🤖 LLM (gpt-4o-mini) Explanations:")
        try:
            llm_result = generate_explanations_llm(article)
            llm_latency = llm_result.get("latency_ms", 0)

            for field in ["sentiment_explanation", "time_to_impact_explanation",
                         "driver_type_explanation", "future_signal_explanation"]:
                explanation = llm_result.get(field, "N/A")
                quality = evaluate_explanation_quality(explanation)
                print(f"  {field}:")
                print(f"    → {explanation}")
                print(f"    Quality: {quality['word_count']} words, reasoning: {quality['has_reasoning']}")

            print(f"  ⏱️ Latency: {llm_latency}ms")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            llm_result = {"error": str(e)}
            llm_latency = 0

        results.append({
            "article": article["title"],
            "slm": slm_result,
            "slm_latency_ms": slm_latency,
            "llm": llm_result,
            "llm_latency_ms": llm_latency,
        })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    slm_latencies = [r["slm_latency_ms"] for r in results if r["slm_latency_ms"] > 0]
    llm_latencies = [r["llm_latency_ms"] for r in results if r["llm_latency_ms"] > 0]

    if slm_latencies:
        print(f"\nSLM (Phi-3) avg latency: {sum(slm_latencies)/len(slm_latencies):.0f}ms")
    if llm_latencies:
        print(f"LLM (gpt-4o-mini) avg latency: {sum(llm_latencies)/len(llm_latencies):.0f}ms")

    if slm_latencies and llm_latencies:
        speedup = sum(llm_latencies) / sum(slm_latencies)
        print(f"\nSLM is {speedup:.1f}x faster than LLM")

    # Save results
    output_file = "data/explanation_comparison.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
