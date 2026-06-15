from providers.base_provider import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, cfg: dict):
        import google.generativeai as genai
        self._model_name = cfg.get("model", "models/gemini-2.0-flash-exp")
        genai.configure(api_key=cfg["api_key"])
        self._model = genai.GenerativeModel(self._model_name)

    @property
    def provider_name(self) -> str:
        return "gemini"

    def call(self, prompt: str) -> tuple[str, int, int, str]:
        response   = self._model.generate_content(prompt)
        raw        = response.text
        usage      = getattr(response, "usage_metadata", None)
        tokens_in  = getattr(usage, "prompt_token_count",      0) if usage else 0
        tokens_out = getattr(usage, "candidates_token_count",  0) if usage else 0
        return raw, tokens_in, tokens_out, self._model_name
