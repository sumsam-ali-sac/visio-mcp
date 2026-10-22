"""AI layer: pick a model provider, explore local repos, return a DiagramSpec.

    from visio_mcp.ai import load_config, make_llm, DiagramAgent
    llm = make_llm(load_config().provider)
    spec = DiagramAgent(llm, repos, "architecture", on_event=print).run()
"""

from __future__ import annotations

from visio_mcp.ai.agent import AgentCancelled, AgentError, AgentEvent, DiagramAgent
from visio_mcp.ai.config import (
    CONFIG_PATH,
    DEFAULT_MODELS,
    AppConfig,
    ProviderConfig,
    ProviderName,
    detect_providers,
    load_config,
    resolve_key,
    save_config,
    suggested_models,
)
from visio_mcp.ai.providers import LLM, LLMError, Reply, Session, ToolCall, ToolDef, make_llm

__all__ = [
    "AgentCancelled", "AgentError", "AgentEvent", "DiagramAgent",
    "CONFIG_PATH", "DEFAULT_MODELS", "AppConfig", "ProviderConfig", "ProviderName",
    "detect_providers", "load_config", "resolve_key", "save_config", "suggested_models",
    "LLM", "LLMError", "Reply", "Session", "ToolCall", "ToolDef", "make_llm",
]
