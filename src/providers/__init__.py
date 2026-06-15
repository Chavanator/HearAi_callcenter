from __future__ import annotations
from typing import Optional
from providers.base_provider import LLMProvider

_instance: Optional[LLMProvider] = None


def get_provider(config: Optional[dict] = None) -> LLMProvider:
    global _instance
    if _instance is not None:
        return _instance

    if config is None:
        raise ValueError(
            "[providers] Primera llamada a get_provider() requiere el config dict"
        )

    ai_provider = config.get("ai_provider", "claude").lower()

    if ai_provider == "claude":
        from providers.claude_provider import ClaudeProvider
        _instance = ClaudeProvider(config["claude"])

    elif ai_provider in ("gemini", "google"):
        from providers.gemini_provider import GeminiProvider
        _instance = GeminiProvider(config["Gemini"])

    else:
        raise ValueError(
            f"[providers] ai_provider desconocido: '{ai_provider}'. "
            "Usa 'claude' o 'gemini' en config.json"
        )

    return _instance


def reset_provider() -> None:
    global _instance
    _instance = None


__all__ = ["get_provider", "reset_provider", "LLMProvider"]