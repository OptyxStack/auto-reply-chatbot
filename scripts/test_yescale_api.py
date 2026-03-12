#!/usr/bin/env python3
"""Quick test for YesScale (OpenAI-compatible) API.

Usage:
  YESCALE_API_KEY=sk-xxx python scripts/test_yescale_api.py
  Or set API_KEY, BASE_URL, MODEL below for quick test.
"""

import os
import httpx

BASE_URL = os.getenv("YESCALE_BASE_URL", "https://api.yescale.io/v1")
API_KEY = os.getenv("YESCALE_API_KEY", "sk-AQshr1c0QRrk0h4n2cmd2lcZ01dbAzzyGHYSrgMCctgIyySd")
MODEL = os.getenv("YESCALE_MODEL", "gpt-4o-mini")

def main():
    print("1. Testing models list (fast)...")
    with httpx.Client(timeout=15.0) as client:
        r = client.get(
            f"{BASE_URL}/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        models = r.json().get("data", [])
        ids = [m.get("id") for m in models]
        print(f"   Models (sample): {ids[:8]}...")
        gpt = [m for m in ids if "gpt" in (m or "").lower()]
        if gpt:
            print(f"   GPT models: {gpt}")
    else:
        print(f"   Error: {r.text[:200]}")

    print("\n2. Testing chat completions...")
    r = None
    for try_model in [MODEL, "gpt-4o", "gpt-3.5-turbo"]:
        print(f"   Trying model: {try_model}")
        with httpx.Client(timeout=60.0) as client:
            try:
                r = client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {API_KEY}",
                    },
                    json={
                        "model": try_model,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 20,
                    },
                )
                break
            except httpx.ReadTimeout:
                print(f"   Timeout on {try_model}")
                r = None
    if r is None:
        print("   All models timed out. Chat completions may be slow from your network.")
        return
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        print(f"Response: {content}")
        print("OK - API works!")
    else:
        print(f"Error: {r.text}")

if __name__ == "__main__":
    main()
