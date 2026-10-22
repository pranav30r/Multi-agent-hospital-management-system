"""
Hospital Intelligence LLM Package.

Exports the unified LLMService supporting OpenAI-compatible chat completions
(OpenAI, Groq) with robust deterministic fallback for clinical intake NLP,
SBAR handoff brief drafting, and discharge summary drafting.
"""

from app.llm.llm_service import (
    LLMService,
    LLMServiceError,
    PROVIDER_OPENAI,
    PROVIDER_GROQ,
    PROVIDER_FALLBACK,
    DISCLAIMER_TEXT,
)

__all__ = [
    "LLMService",
    "LLMServiceError",
    "PROVIDER_OPENAI",
    "PROVIDER_GROQ",
    "PROVIDER_FALLBACK",
    "DISCLAIMER_TEXT",
]
