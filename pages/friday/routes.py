"""F.R.I.D.A.Y. assistant: streaming chat endpoint + history/clear."""
import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core import undo
from pages.friday import agent, messages

friday_bp = Blueprint("friday", __name__)


@friday_bp.route("/api/undo", methods=["POST"])
def undo_last():
    """Spec S — reverse the last data mutation."""
    return jsonify(undo.undo())


def _sse(frames):
    for event, payload in frames:
        yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@friday_bp.route("/api/friday/message", methods=["POST"])
def message():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "empty message"}), 400
    stream = stream_with_context(_sse(agent.run_turn(text)))
    return Response(stream, mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@friday_bp.route("/api/quickadd", methods=["POST"])
def quickadd():
    """Spec K — natural-language quick-add: run the text through the agent loop."""
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "empty message"}), 400
    return jsonify(agent.run_text(text))


@friday_bp.route("/api/friday/history", methods=["GET"])
def history():
    shown = [{"role": m["role"], "content": m["content"]}
             for m in messages.history()
             if m["content"] and m["role"] in ("user", "assistant")]
    return jsonify(shown)


@friday_bp.route("/api/friday/clear", methods=["POST"])
def clear():
    messages.clear()
    return "", 204
