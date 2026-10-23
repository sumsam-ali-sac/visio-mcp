"""Build the LLM for a saved provider configuration."""

from __future__ import annotations

import os

from ..config import ProviderConfig, resolve_key
from .anthropic import AnthropicLLM
from .base import LLM
from .errors import LLMError
from .gemini import GeminiLLM
from .openai import OpenAILLM


def make_llm(cfg: ProviderConfig) -> LLM:
    """Build the LLM for a provider config. Raises LLMError when settings are missing."""
    key = resolve_key(cfg)
    if cfg.provider == "anthropic":
        if not key:
            raise LLMError("No Anthropic API key found.", "run visio-ai setup or set ANTHROPIC_API_KEY", "auth")
        return AnthropicLLM(cfg.model or "claude-opus-5-5", key, effort=cfg.effort or "high")
    if cfg.provider == "openai":
        if not key:
            raise LLMError("No OpenAI API key found.", "run visio-ai setup or set OPENAI_API_KEY", "auth")
        return OpenAILLM.openai(cfg.model, key, effort=cfg.effort)
    if cfg.provider == "azure":
        endpoint = cfg.endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        deployment = cfg.deployment or cfg.model or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        version = cfg.api_version or os.environ.get("AZURE_OPENAI_API_VERSION")
        if not endpoint or not deployment:  # no key is fine: Azure sign-in (Entra ID) is used instead
            raise LLMError("Azure OpenAI needs an endpoint and a deployment name.",
                           "run visio-ai setup or set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT", "error")
        return OpenAILLM.azure(deployment, endpoint, key, version, effort=cfg.effort)
    if cfg.provider == "gemini":
        if not key:
            raise LLMError("No Gemini API key found.", "run visio-ai setup or set GEMINI_API_KEY", "auth")
        return GeminiLLM(cfg.model, key)
    if cfg.provider == "ollama":
        return OpenAILLM.ollama(cfg.model, cfg.endpoint)
    raise LLMError(f"Unknown provider '{cfg.provider}'.", "choose anthropic, openai, azure, gemini or ollama")
