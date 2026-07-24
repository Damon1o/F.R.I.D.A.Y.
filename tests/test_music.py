"""Spotify token persistence: tokens obtained in the OAuth callback survive across
provider instances (each request builds a fresh SpotifyProvider). requests always faked."""
from pages.music import SpotifyProvider


class FakeResp:
    def __init__(self, ok=True, data=None):
        self.ok = ok
        self._data = data or {}

    def json(self):
        return self._data


def test_exchange_code_persists_tokens_across_instances(ctx, monkeypatch):
    import pages.music as music
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        music.requests, "post",
        lambda *a, **k: FakeResp(True, {"access_token": "AT", "refresh_token": "RT"}),
    )

    assert SpotifyProvider().exchange_code("code123") is True

    # A fresh instance (as every subsequent request gets) reads the stored tokens.
    fresh = SpotifyProvider()
    assert fresh._access_token == "AT"
    assert fresh._refresh_token == "RT"
    assert fresh.is_connected() is True
