"""Conversations: "new chat" starts a thread instead of deleting history."""
from pages.friday import agent, messages


class TitleClient:
    """LLM stub: first call is the reply, second is the auto-generated title."""
    def __init__(self, title="Grocery Run Planning"):
        self.replies = [{"role": "assistant", "content": "Sure."},
                        {"role": "assistant", "content": f'"{title}"'}]

    def complete(self, messages, tools=None):
        return self.replies.pop(0)


def test_new_thread_keeps_previous_conversation(ctx):
    messages.add("user", "first chat")
    messages.add("assistant", "hi")
    messages.new_thread()
    messages.add("user", "second chat")

    assert [m["content"] for m in messages.history()] == ["second chat"]
    assert [t["title"] for t in messages.threads()] == ["second chat", "first chat"]

    messages.set_thread(1)
    assert [m["content"] for m in messages.history()] == ["first chat", "hi"]


def test_clear_only_drops_the_open_thread(ctx):
    messages.add("user", "keep me")
    messages.new_thread()
    messages.add("user", "drop me")
    messages.clear()

    assert messages.history() == []
    assert [t["title"] for t in messages.threads()] == ["keep me"]


def test_history_endpoint_reads_a_past_thread(client):
    client.post("/api/friday/thread")  # ensure a pointer exists
    with client.application.app_context():
        messages.add("user", "old turn")
        messages.new_thread()
        messages.add("user", "new turn")

    threads = client.get("/api/friday/threads").get_json()
    old = min(t["id"] for t in threads["threads"])
    rows = client.get(f"/api/friday/history?thread={old}").get_json()
    assert [r["content"] for r in rows] == ["old turn"]


def test_chat_page_ships_the_row_action_buttons(client):
    html = client.get("/friday").get_data(as_text=True)
    assert 'id="thread-actions"' in html          # friday.js clones this per row
    assert "data-rename" in html and "data-delete" in html


def test_autotitle_names_a_new_thread_once(ctx):
    list(agent.run_turn("what should I buy", TitleClient()))
    thread = messages.current_thread()
    assert messages.title(thread) == "Grocery Run Planning"
    assert [t["title"] for t in messages.threads()] == ["Grocery Run Planning"]

    # Second turn: the thread already has a name, so no title call is made — a
    # TitleClient with only one scripted reply left would blow up otherwise.
    only_reply = TitleClient()
    only_reply.replies = [{"role": "assistant", "content": "Milk."}]
    list(agent.run_turn("and then", only_reply))
    assert messages.title(thread) == "Grocery Run Planning"


def test_rename_endpoint_overrides_the_generated_title(client):
    with client.application.app_context():
        messages.add("user", "first message")

    res = client.patch("/api/friday/thread/1", json={"title": "  My Chat  "})
    assert res.get_json() == {"title": "My Chat"}
    assert client.patch("/api/friday/thread/1", json={"title": " "}).status_code == 400

    threads = client.get("/api/friday/threads").get_json()["threads"]
    assert threads[0]["title"] == "My Chat"


def test_delete_endpoint_drops_the_thread_and_reopens_the_newest(client):
    client.post("/api/friday/thread")
    with client.application.app_context():
        messages.add("user", "keep me")
        messages.new_thread()
        messages.add("user", "drop me")
        open_thread = messages.current_thread()
    client.patch(f"/api/friday/thread/{open_thread}", json={"title": "Doomed"})

    assert client.delete(f"/api/friday/thread/{open_thread}").get_json()["current"] != open_thread

    threads = client.get("/api/friday/threads").get_json()
    assert [t["title"] for t in threads["threads"]] == ["keep me"]
    with client.application.app_context():
        assert messages.title(open_thread) is None  # the name goes with the thread
