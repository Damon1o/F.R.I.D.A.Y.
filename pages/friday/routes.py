"""F.R.I.D.A.Y. assistant: streaming chat endpoint + history/clear."""
import json

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context, g

from core import undo
from core.files import UnsupportedFile, extract
from pages.friday import agent, messages

friday_bp = Blueprint("friday", __name__)


@friday_bp.route("/friday")
def friday_page():
    """Full-window conversation. The shell's side panel is suppressed here."""
    return render_template("friday.html")


@friday_bp.route("/api/undo", methods=["POST"])
def undo_last():
    """Spec S — reverse the last data mutation."""
    return jsonify(undo.undo(g.session_id))


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


@friday_bp.route("/api/friday/upload", methods=["POST"])
def upload():
    """Extract an attachment's text and hand it back. Nothing is stored on disk —
    the client sends the text as the next message, so the normal stream applies."""
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "no file"}), 400
    try:
        text = extract(f.filename, f.read())
    except UnsupportedFile as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": f.filename, "chars": len(text), "text": text})


@friday_bp.route("/api/friday/history", methods=["GET"])
def history():
    """Newest `limit` turns; `before` pages backwards for older history."""
    limit = request.args.get("limit", type=int)
    before = request.args.get("before", type=int)
    rows = messages.history(limit=limit, before_id=before,
                            thread_id=request.args.get("thread", type=int))
    shown = [{"id": m["id"], "role": m["role"], "content": m["content"]}
             for m in rows
             if m["content"] and m["role"] in ("user", "assistant")]
    return jsonify(shown)


@friday_bp.route("/api/friday/threads", methods=["GET"])
def thread_list():
    """Past conversations, newest first, plus which one is open."""
    return jsonify({"current": messages.current_thread(), "threads": messages.threads()})


@friday_bp.route("/api/friday/thread", methods=["POST"])
def open_thread():
    """`{"id": N}` reopens a past conversation; no id starts a fresh one."""
    thread_id = (request.get_json(silent=True) or {}).get("id")
    new = messages.set_thread(int(thread_id)) if thread_id else messages.new_thread()
    return jsonify({"id": new})


@friday_bp.route("/api/friday/clear", methods=["POST"])
def clear():
    messages.clear()
    return "", 204
