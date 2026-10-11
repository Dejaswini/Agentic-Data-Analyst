"""LLM factory: Gemini free tier by default, Groq as the alternative.

Keys come from .env (see .env.example) - never hardcoded.
"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


def _text(content) -> str:
    """Flatten message content (str or list of parts) into a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content)


class _TextLLM:
    """Thin proxy so `.invoke(...).content` is always a string."""

    def __init__(self, inner: BaseChatModel):
        self._inner = inner

    def invoke(self, *args, **kwargs):
        resp = self._inner.invoke(*args, **kwargs)
        resp.content = _text(resp.content)
        return resp

    def __getattr__(self, name):
        return getattr(self._inner, name)


def build_llm() -> BaseChatModel:
    return _TextLLM(_build_raw_llm())  # type: ignore[return-value]


def _build_raw_llm() -> BaseChatModel:
    provider = settings.llm_provider
    if provider == "gemini":
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is missing. Add it to .env "
                "(free key: https://aistudio.google.com/app/apikey)"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0,
        )
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to .env "
                "(free key: https://console.groq.com/keys)"
            )
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0,
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}' - use 'gemini' or 'groq'.")
