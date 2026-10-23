"""The provider wizard: choose the AI that explores the code, test it, and save it."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from visio_mcp.ai import config
from visio_mcp.cli import prompts, ui
from visio_mcp.cli.studio.session import provider_label

PROVIDERS = [("anthropic", "Claude (Anthropic)"), ("gemini", "Google Gemini"), ("azure", "Azure OpenAI"),
             ("openai", "OpenAI"), ("ollama", "Ollama (local)")]


def setup_wizard(cfg: Any) -> Any:
    """Walk through provider, credentials and model; returns the (possibly updated) config."""
    ui.console.print(ui.panel(Text("Pick the model that explores your code. Keys stay on this machine "
                                   f"({config.CONFIG_PATH}).", style="muted"), title="AI provider"))
    detected = {p.provider: p for p in config.detect_providers()}
    choices = [prompts.choice(label, key, "detected in your environment" if key in detected else "")
               for key, label in PROVIDERS]
    provider = prompts.select("Provider", choices)
    pc = detected.get(provider) or config.ProviderConfig(provider=provider,
                                                          model=config.DEFAULT_MODELS.get(provider, ""))

    if provider == "azure":
        typed = prompts.text("Azure OpenAI endpoint", default=pc.endpoint or "https://<resource>.openai.azure.com",
                             instruction="(the portal's …/openai/v1 URL works too)")
        pc.endpoint = config.azure_endpoint_root(typed)
        if pc.endpoint and pc.endpoint != typed.strip().rstrip("/"):
            ui.info(f"Using the resource endpoint [bold]{pc.endpoint}[/]")
        pc.deployment = prompts.text("Deployment name", default=pc.deployment or "")
        pc.api_version = prompts.text("API version", default=pc.api_version or config.DEFAULT_AZURE_API_VERSION,
                                      instruction="(the Azure OpenAI API version, not the model version)")
        pc.model = pc.deployment or pc.model
    if provider != "ollama" and not (pc.api_key or config.resolve_key(pc)):
        hint = "(leave empty to use your Azure sign-in: az login)" if provider == "azure" else None
        pc.api_key = prompts.password("API key", instruction=hint) or None
        if provider == "azure" and not pc.api_key:
            ui.info(f"Using your {config.AZURE_SIGN_IN}: run [bold]az login[/] first if you haven't")
    if provider != "azure":
        models = config.suggested_models(provider) or [pc.model]
        pick = prompts.select("Model", [prompts.choice(m, m, "default" if m == pc.model else "") for m in models]
                              + [prompts.choice("Other…", "")], default=pc.model if pc.model in models else None)
        pc.model = pick or prompts.text("Model id", default=pc.model)

    if prompts.confirm("Test the connection now?", default=True) and not _connects(pc):
        if not prompts.confirm("Save it anyway?", default=False):
            return cfg
    cfg.provider = pc
    config.save_config(cfg)
    ui.ok(f"Saved to {config.CONFIG_PATH}")
    return cfg


def _connects(pc: Any) -> bool:
    from visio_mcp.ai import providers

    try:
        with ui.spinner("Saying hello…"):
            providers.make_llm(pc).start("Reply with the single word: ready", []).send_user("ping")
    except Exception as e:
        ui.fail(str(getattr(e, "message", e)), getattr(e, "hint", ""))
        return False
    ui.ok(f"Connected to {provider_label(pc)}")
    return True
