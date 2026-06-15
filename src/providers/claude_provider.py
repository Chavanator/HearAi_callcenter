from providers.base_provider import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, cfg: dict):
        import anthropic
        self._model  = cfg.get("model", "claude-haiku-4-5-20251001")
        self._client = anthropic.Anthropic(api_key=cfg["api_key"])

    @property
    def provider_name(self) -> str:
        return "claude"

    def call(self, prompt: str) -> tuple[str, int, int, str]:
        response = self._client.messages.create(
            model      = self._model,
            max_tokens = 4096,
            messages   = [{"role": "user", "content": prompt}],
        )
        raw        = response.content[0].text
        tokens_in  = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        return raw, tokens_in, tokens_out, self._model
