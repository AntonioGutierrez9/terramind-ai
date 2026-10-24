"""Settings, .env discovery, model construction and prices.

.env lookup order (first value wins): this repo folder, then the folder above it
(where the teaching staff keep theirs), then further parent folders.
Keys accepted: PORTKEY_API_KEY (course key, routed through Portkey) or OPENAI_API_KEY.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
ENV_FILES_FOUND: list[str] = []
for folder in [REPO_DIR, *REPO_DIR.parents]:
    env = folder / ".env"
    if env.exists():
        load_dotenv(env, override=False)
        ENV_FILES_FOUND.append(str(env))

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("TERRAMIND_DB", DATA_DIR / "terramind.db"))
FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-6-luna")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")

# USD per 1M tokens (course pricing sheet, Lecture 11). Cached input billed at the lower rate.
MODEL_PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "output": 0.50},
}
# OpenAI charges web search tool calls separately from tokens (USD per call; planning estimate).
WEB_SEARCH_USD_PER_CALL = float(os.getenv("WEB_SEARCH_USD_PER_CALL", "0.01"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


DEFAULT_LIMITS = {
    "max_specialist_calls": _int("MAX_SPECIALIST_CALLS_PER_TURN", 2),
    "max_tool_calls": _int("MAX_TOOL_CALLS_PER_TURN", 12),
    "max_requests": _int("MAX_MODEL_REQUESTS_PER_TURN", 10),
    "max_tokens": _int("MAX_TOKENS_PER_TURN", 250_000),
    "max_usd": _float("MAX_USD_PER_TURN", 0.05),
}
RESEARCH_CACHE_DAYS = _int("RESEARCH_CACHE_DAYS", 14)


def cost_usd(input_tokens: int, output_tokens: int, cached_tokens: int = 0, model: str = MODEL_NAME, web_searches: int = 0) -> float:
    p = MODEL_PRICES.get(model, MODEL_PRICES["gpt-6-luna"])
    cached = min(cached_tokens, input_tokens)
    return ((input_tokens - cached) * p["input"] + cached * p["cached_input"] + output_tokens * p["output"]) / 1e6 + web_searches * WEB_SEARCH_USD_PER_CALL


def api_key_status() -> dict:
    return {
        "portkey": bool(os.getenv("PORTKEY_API_KEY", "").strip()),
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "env_files": len(ENV_FILES_FOUND),
        "model": MODEL_NAME,
    }


def ai_available() -> bool:
    s = api_key_status()
    return s["portkey"] or s["openai"]


@lru_cache(maxsize=2)
def build_model(model_name: str = MODEL_NAME):
    """gpt-6-luna needs the Responses API for tools; route through Portkey with the course key."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    portkey = os.getenv("PORTKEY_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if portkey:
        client = AsyncOpenAI(api_key=portkey, base_url=PORTKEY_BASE_URL,
                             default_headers={"x-portkey-api-key": portkey, "x-portkey-provider": "openai"})
    elif openai_key:
        client = AsyncOpenAI(api_key=openai_key)
    else:
        raise RuntimeError("No API key found. Put PORTKEY_API_KEY in a .env file in the repo folder or the folder above it.")
    return OpenAIResponsesModel(model_name, provider=OpenAIProvider(openai_client=client))
