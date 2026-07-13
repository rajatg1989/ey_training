"""
Pluggable LLM layer — the model is the only swappable part of the pipeline.

Switch the default provider with the LLM_PROVIDER env var ("anthropic" or
"groq"); the UI can override it per session. Groq is OpenAI-compatible, so it's
reached through the openai SDK with a custom base_url. Everything else in the
app (compute layer, context serializer, prompt) is provider-agnostic.

Env vars:
  LLM_PROVIDER       anthropic | groq        (default: anthropic)
  ANTHROPIC_API_KEY  key for Claude
  ANTHROPIC_MODEL    override model           (default: claude-opus-4-8)
  GROQ_API_KEY       key for Groq
  GROQ_MODEL         override model           (default: llama-3.3-70b-versatile)
"""
from __future__ import annotations

import os
from typing import Optional

DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

PROVIDERS = {
    "anthropic": {
        "label": "Claude (Anthropic)",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
        "base_url": None,                 # native SDK
    },
    "groq": {
        "label": "Groq · Llama 3.3 70B",
        "env_key": "GROQ_API_KEY",
        "default_model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "base_url": "https://api.groq.com/openai/v1",   # OpenAI-compatible
    },
}


class LLMError(Exception):
    """Raised for missing keys / unknown providers (mapped to a clean HTTP 500)."""


def list_providers() -> list[dict]:
    """Public metadata for the UI picker (no secrets)."""
    return [
        {"id": pid, "label": cfg["label"], "default_model": cfg["default_model"],
         "is_default": pid == DEFAULT_PROVIDER}
        for pid, cfg in PROVIDERS.items()
    ]


def complete(system: str, messages: list[dict], *, max_tokens: int = 1200,
             provider: Optional[str] = None, model: Optional[str] = None,
             api_key: Optional[str] = None) -> str:
    """Unified text completion across providers.

    `messages` is a list of {"role": "user"|"assistant", "content": str}.
    Returns the assistant's text. Raises LLMError for config problems.
    """
    provider = (provider or DEFAULT_PROVIDER).lower()
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise LLMError(f"Unknown provider '{provider}'. "
                       f"Options: {', '.join(PROVIDERS)}.")

    key = api_key or os.environ.get(cfg["env_key"])
    if not key:
        raise LLMError(f"No API key for '{provider}'. Set {cfg['env_key']} on the "
                       f"server or enter a key in the app.")
    model = model or cfg["default_model"]

    if provider == "anthropic":
        import anthropic
        resp = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=messages,
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    # OpenAI-compatible providers (Groq, and any other base_url-style endpoint)
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=cfg["base_url"])
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}] + messages,
    )
    return resp.choices[0].message.content or ""
