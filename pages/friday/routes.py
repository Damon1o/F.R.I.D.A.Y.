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
    # The first frame carries 2 KB of comment padding: anything between here and the
    # browser that buffers small writes (Windows AV shims, proxies) otherwise holds the
    # early frames until more data arrives, which reads as "the reply never came" until
    # a later turn pushes it out. Padding rides along with the first real frame rather
    # than being its own chunk, so nothing waits on an extra read to start the turn.
    pad = ": " + " " * 2048 + "\n\n"
    for event, payload in frames:
        yield f"{pad}event: {event}\ndata: {json.dumps(payload)}\n\n"
        pad = ""


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
        text, total = extract(f.filename, f.read())
    except UnsupportedFile as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"name": f.filename, "chars": len(text), "total_chars": total,
                    "text": text, "truncated": total > len(text)})


@friday_bp.route("/api/friday/history", methods=["GET"])
def history():
    """Newest `limit` turns; `before` pages backwards for older history."""
    limit = request.args.get("limit", type=int)
    before = request.args.get("before", type=int)
    rows = messages.history(limit=limit, before_id=before,
                            thread_id=request.args.get("thread", type=int))
    # Spec AE — a reply's tool notes are rebuilt from the stored tool_calls, so they
    # survive a reload without a new column. Tool *results* are never projected:
    # they are untrusted third-party text and belong nowhere near the UI.
    tools: list[dict] = []
    shown = []
    for m in rows:
        if m["role"] == "assistant" and m["tool_calls"]:
            tools.extend(agent.tool_notes(json.loads(m["tool_calls"])))
        if m["content"] and m["role"] in ("user", "assistant"):
            shown.append({"id": m["id"], "role": m["role"], "content": m["content"],
                          "tools": tools if m["role"] == "assistant" else []})
            tools = []
    return jsonify(shown)


@friday_bp.route("/api/friday/history/<int:message_id>", methods=["DELETE"])
def truncate(message_id):
    """Spec AD — drop this message and every later one in the open thread. This is
    the rewind behind retry (drop the reply) and edit (drop the question too)."""
    return jsonify({"last": messages.truncate_from(message_id)})


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


@friday_bp.route("/api/friday/thread/<int:thread_id>", methods=["PATCH", "DELETE"])
def edit_thread(thread_id):
    """PATCH `{"title": "..."}` renames a conversation; DELETE removes it entirely."""
    if request.method == "DELETE":
        return jsonify({"current": messages.delete(thread_id)})
    title = ((request.get_json(silent=True) or {}).get("title") or "").strip()
    if not title:
        return jsonify({"error": "empty title"}), 400
    return jsonify({"title": messages.set_title(thread_id, title[:60])})


@friday_bp.route("/api/friday/clear", methods=["POST"])
def clear():
    messages.clear()
    return "", 204
