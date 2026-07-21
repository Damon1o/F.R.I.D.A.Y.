from flask import Blueprint, current_app, jsonify, request

from core.context_loader import build_context
from core.providers.anthropic_provider import AnthropicProvider
from core.router import TIER_MODELS, classify

chat_bp = Blueprint("chat", __name__)

TOOL_DISPATCH: dict[str, callable] = {}

MAX_TOOL_ITERATIONS = 5


@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    payload = request.get_json()
    user_message = payload["message"]
    active_page = payload.get("active_page", "")

    provider = AnthropicProvider(api_key=current_app.config["ANTHROPIC_API_KEY"])

    decision = classify(provider, user_message, active_page)
    context = build_context(decision.skills)

    total_input_tokens = decision.input_tokens
    total_output_tokens = decision.output_tokens

    messages = [{"role": "user", "content": user_message}]
    model = TIER_MODELS[decision.tier]

    reply_text = ""
    for _ in range(MAX_TOOL_ITERATIONS):
        response = provider.complete(
            system=context["system_prompt"],
            messages=messages,
            tools=context["tools"] or None,
            model=model,
        )
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens

        if not response.tool_calls:
            reply_text = response.text
            break

        messages.append({"role": "assistant", "content": response.text or ""})
        tool_results = []
        for call in response.tool_calls:
            handler = TOOL_DISPATCH.get(call["name"])
            result = handler(**call["input"]) if handler else {"error": "unknown tool"}
            tool_results.append(
                {"tool_use_id": call["id"], "content": str(result)}
            )
        messages.append({"role": "user", "content": str(tool_results)})
    else:
        reply_text = "Sorry, I couldn't finish that request."

    total_tokens = total_input_tokens + total_output_tokens
    budget_warning = total_tokens > current_app.config["TOKEN_BUDGET_WARNING"]

    return jsonify(
        {
            "reply": reply_text,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "budget_warning": budget_warning,
        }
    )