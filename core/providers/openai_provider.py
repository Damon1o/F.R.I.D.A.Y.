from core.providers.base import Provider, ProviderResponse


class OpenAIProvider(Provider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
    ) -> ProviderResponse:
        raise NotImplementedError("OpenAI provider not implemented yet")
