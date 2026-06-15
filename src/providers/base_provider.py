from abc import ABC, abstractmethod


class LLMProvider(ABC):

    @abstractmethod
    def call(self, prompt: str) -> tuple[str, int, int, str]:
        """
        Envia el prompt al modelo.
        Returns: (raw_response, tokens_in, tokens_out, model_name)
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identificador corto del proveedor (ej: 'claude', 'gemini')."""
        ...