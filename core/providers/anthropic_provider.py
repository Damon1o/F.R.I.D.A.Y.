import anthropic

from core.providers.base import Provider, ProviderResponse


class AnthropicProvider(Provider):
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
    ) -> ProviderResponse:
        kwargs = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        message = self.client.messages.create(**kwargs)

        text = ""
        tool_calls = []
        for block in message.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason,
        )
