import anthropic

from core.providers.base import Provider, ProviderResponse

# Claude Fable 5 has always-on thinking and no sampling params; it also
# supports a server-side fallback to Opus 4.8 on a policy refusal, which we
# opt into by default per Anthropic's guidance.
FABLE_MODEL = "claude-fable-5"
FABLE_FALLBACK_MODEL = "claude-opus-4-8"
FABLE_FALLBACK_BETA = "server-side-fallback-2026-06-01"


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

        if model == FABLE_MODEL:
            message = self.client.beta.messages.create(
                betas=[FABLE_FALLBACK_BETA],
                fallbacks=[{"model": FABLE_FALLBACK_MODEL}],
                **kwargs,
            )
        else:
            message = self.client.messages.create(**kwargs)

        if message.stop_reason == "refusal":
            return ProviderResponse(
                text="I can't help with that request.",
                tool_calls=[],
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                stop_reason="refusal",
            )

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
