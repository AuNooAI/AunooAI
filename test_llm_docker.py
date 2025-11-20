#!/usr/bin/env python3
"""
Test script to diagnose LLM message passing issue in Docker.
Run this inside the Docker container to test if messages are being passed correctly.
"""
import os
import sys
from litellm import completion

# Test messages
test_messages = [
    {"role": "system", "content": "You are a helpful assistant. You must respond with JSON only."},
    {"role": "user", "content": 'Please respond with this exact JSON: {"test": "success", "value": 42}'}
]

print("=" * 70)
print("LiteLLM Docker Diagnostic Test")
print("=" * 70)
print()

# Check environment
print("Environment Check:")
print(f"  Python version: {sys.version}")
print(f"  OPENAI_API_KEY set: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")
print(f"  Key value: {os.getenv('OPENAI_API_KEY', '')[:10]}..." if os.getenv('OPENAI_API_KEY') else "  Key value: Not set")
print()

# Test 1: Direct litellm.completion call (no router)
print("Test 1: Direct litellm.completion() call")
print("-" * 70)
print(f"Messages being sent:")
for i, msg in enumerate(test_messages):
    print(f"  [{i}] role={msg['role']}, content_length={len(msg['content'])}")
    print(f"      content: {msg['content'][:80]}...")
print()

try:
    response = completion(
        model="gpt-4o-mini",
        messages=test_messages,
        max_tokens=100,
        temperature=0.0
    )

    content = response.choices[0].message.content
    print(f"✅ SUCCESS - Response received:")
    print(f"   Length: {len(content)} characters")
    print(f"   Content: {content}")
    print()

    # Check if response matches expected
    if "Hello! How can I assist you today?" in content:
        print("❌ ERROR: Received default greeting - messages were NOT passed correctly!")
    elif "success" in content.lower() or "42" in content:
        print("✅ PASS: Messages were passed correctly!")
    else:
        print("⚠️  WARNING: Unexpected response - messages may have been modified")

except Exception as e:
    print(f"❌ FAILED - Error: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)

# Test 2: Using Router (like the app does)
print("Test 2: Using LiteLLM Router")
print("-" * 70)

try:
    from litellm import Router

    router_config = {
        "model_list": [{
            "model_name": "gpt-4o-mini",
            "litellm_params": {
                "model": "openai/gpt-4o-mini",
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        }]
    }

    router = Router(
        model_list=router_config["model_list"],
        cache_responses=False,
        set_verbose=True
    )

    print(f"Messages being sent:")
    for i, msg in enumerate(test_messages):
        print(f"  [{i}] role={msg['role']}, content_length={len(msg['content'])}")
    print()

    response = router.completion(
        model="gpt-4o-mini",
        messages=test_messages,
        caching=False
    )

    content = response.choices[0].message.content
    print(f"✅ SUCCESS - Response received:")
    print(f"   Length: {len(content)} characters")
    print(f"   Content: {content}")
    print()

    # Check if response matches expected
    if "Hello! How can I assist you today?" in content:
        print("❌ ERROR: Received default greeting - Router dropped messages!")
        print("   This explains why the app is failing in Docker!")
    elif "success" in content.lower() or "42" in content:
        print("✅ PASS: Router passed messages correctly!")
    else:
        print("⚠️  WARNING: Unexpected response")

except Exception as e:
    print(f"❌ FAILED - Error: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
print("Diagnostic complete")
print("=" * 70)
