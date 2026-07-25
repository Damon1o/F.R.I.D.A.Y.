"""Spec P — bounded context window: to_api(limit) trims and snaps to a user turn."""
from pages.friday import messages


def test_to_api_full_by_default(ctx):
    for i in range(6):
        messages.add("user", f"u{i}")
        messages.add("assistant", f"a{i}")
    assert len(messages.to_api()) == 12


def test_to_api_limit_snaps_to_user_turn(ctx):
    messages.add("user", "u0")
    messages.add("assistant", "a0")
    messages.add("user", "u1")
    messages.add("assistant", "a1")
    # last 3 rows would be [a0, u1, a1]; window snaps forward to the u1 user turn.
    win = messages.to_api(limit=3)
    assert win[0] == {"role": "user", "content": "u1"}
    assert [m["content"] for m in win] == ["u1", "a1"]
