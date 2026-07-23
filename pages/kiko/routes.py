"""Kiko assistant: streaming chat endpoint + history/clear."""
import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from pages.kiko import agent, messages

kiko_bp = Blueprint("kiko", __name__)


def _sse(frames):
    for event, payload in frames:
        yield f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@kiko_bp.route("/api/kiko/message", methods=["POST"])
def message():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "empty message"}), 400
    stream = stream_with_context(_sse(agent.run_turn(text)))
    return Response(stream, mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@kiko_bp.route("/api/kiko/history", methods=["GET"])
def history():
    shown = [{"role": m["role"], "content": m["content"]}
             for m in messages.history()
             if m["content"] and m["role"] in ("user", "assistant")]
    return jsonify(shown)


@kiko_bp.route("/api/kiko/clear", methods=["POST"])
def clear():
    messages.clear()
    return "", 204
