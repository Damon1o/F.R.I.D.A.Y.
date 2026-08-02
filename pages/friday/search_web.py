"""Spec H — web search via SerpAPI (Google results). One provider, one key, no fallback."""
import os

import requests

ENDPOINT = "https://serpapi.com/search.json"


def search(query: str, count: int = 5):
    """Top web results as [{title, url, snippet}]. Returns {"error": ...} on any failure."""
    key = os.environ.get("SERP_API_KEY")
    if not key:
        return {"error": "web search unavailable — SERP_API_KEY is not set"}
    count = max(1, min(int(count), 10))  # cap: tool-result tokens are the cost
    try:
        resp = requests.get(ENDPOINT, timeout=8,
                            params={"q": query, "num": count, "engine": "google",
                                    "api_key": key})
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"search failed: {e}"}
    body = resp.json()
    if body.get("error"):
        return {"error": f"search failed: {body['error']}"}
    results = body.get("organic_results") or []
    return [{"title": r.get("title", ""), "url": r.get("link", ""),
             "snippet": r.get("snippet", "")} for r in results[:count]]
