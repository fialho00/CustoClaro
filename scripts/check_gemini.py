"""Check locally configured Gemini models without exposing the API key.

Run: python scripts/check_gemini.py [--live]
The optional live check sends one tiny prompt and may consume API quota.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher import load_key_from_documents  # noqa: E402
from api.index import PREFERRED_MODEL  # noqa: E402
from products import SEARCH_MODEL  # noqa: E402
from product_catalog import SEARCH_MODEL as CATALOG_MODEL  # noqa: E402


def main() -> int:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or load_key_from_documents()
    if not key:
        print("Gemini key: missing (set GEMINI_API_KEY on the server).")
        return 2
    print("Gemini key: present (value hidden).")
    try:
        from google import genai
        from google.genai import types
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=15000)) as client:
            available = {m.name.removeprefix("models/") for m in client.models.list() if m.name}
            configured = {"chat/photo": PREFERRED_MODEL, "explore": SEARCH_MODEL, "catalog": CATALOG_MODEL}
            for label, model in configured.items():
                print(f"{label}: {model} - {'available' if model in available else 'NOT LISTED'}")
            if "--live" in sys.argv:
                model = PREFERRED_MODEL
                if model not in available:
                    print("Live check: skipped; configured chat model not listed.")
                    return 3
                try:
                    response = client.models.generate_content(model=model, contents="Responda apenas OK.")
                    print("Live check:", "OK" if (response.text or "").strip() else "empty response")
                except Exception as exc:
                    print("Live check failed:", type(exc).__name__, "status", getattr(exc, "code", "unknown"))
                    return 4
    except Exception as exc:
        print("API metadata check failed:", type(exc).__name__, "status", getattr(exc, "code", "unknown"))
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
