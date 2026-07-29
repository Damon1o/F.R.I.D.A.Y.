"""Conversations: "new chat" starts a thread instead of deleting history."""
from pages.friday import messages


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
