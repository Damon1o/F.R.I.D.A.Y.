"""Music provider abstraction and Spotify implementation."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import os
import requests

@dataclass
class TrackInfo:
    title: str
    artist: str
    album_art: Optional[str]
    progress_ms: int
    duration_ms: int
    is_playing: bool
    device_id: Optional[str] = None

class MusicProvider(ABC):
    @abstractmethod
    def get_now_playing(self) -> Optional[TrackInfo]:
        pass

    @abstractmethod
    def control(self, action: str, position_ms: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def play_track(self, query: str) -> bool:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

class SpotifyProvider(MusicProvider):
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5000/api/music/spotify/callback")
        self._access_token = None
        self._refresh_token = None
        self._load_tokens()

    def _load_tokens(self):
        # Env vars seed a fresh deploy; the settings table holds tokens the OAuth
        # callback obtained, and wins (env is only a bootstrap fallback). DB read
        # is best-effort: no app context / DB down falls back to env, never 500s.
        self._access_token = os.getenv("SPOTIFY_ACCESS_TOKEN")
        self._refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        try:
            from core.db import query
            stored = {r["key"]: r["value"] for r in query(
                "SELECT key, value FROM settings "
                "WHERE key IN ('spotify_access_token', 'spotify_refresh_token')")}
            self._access_token = stored.get("spotify_access_token") or self._access_token
            self._refresh_token = stored.get("spotify_refresh_token") or self._refresh_token
        except Exception:
            pass

    def _save_tokens(self, access_token: str, refresh_token: str):
        try:
            from core.db import execute
            for key, val in (("spotify_access_token", access_token),
                             ("spotify_refresh_token", refresh_token)):
                if val:
                    execute(
                        "INSERT INTO settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                        "updated_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
                        (key, val),
                    )
        except Exception:
            pass

    def _refresh_access_token(self) -> bool:
        if not self._refresh_token or not self.client_id or not self.client_secret:
            return False
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            self._access_token = data["access_token"]
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]
            self._save_tokens(self._access_token, self._refresh_token)
            return True
        return False

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        if not self._access_token:
            return None
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        resp = requests.request(method, f"https://api.spotify.com/v1{endpoint}", headers=headers, timeout=10, **kwargs)
        if resp.status_code == 401 and self._refresh_access_token():
            headers["Authorization"] = f"Bearer {self._access_token}"
            resp = requests.request(method, f"https://api.spotify.com/v1{endpoint}", headers=headers, timeout=10, **kwargs)
        return resp if resp.ok else None

    def get_now_playing(self) -> Optional[TrackInfo]:
        resp = self._request("GET", "/me/player/currently-playing")
        if not resp:
            return None
        if resp.status_code == 204 or not resp.content:
            return None
        data = resp.json()
        if not data.get("is_playing") and not data.get("item"):
            return None
        item = data.get("item")
        if not item:
            return None
        album_art = None
        if item.get("album", {}).get("images"):
            album_art = item["album"]["images"][0]["url"]
        return TrackInfo(
            title=item.get("name", "Unknown"),
            artist=", ".join(a["name"] for a in item.get("artists", [])),
            album_art=album_art,
            progress_ms=data.get("progress_ms", 0),
            duration_ms=item.get("duration_ms", 0),
            is_playing=data.get("is_playing", False),
            device_id=data.get("device", {}).get("id"),
        )

    def control(self, action: str, position_ms: Optional[int] = None) -> bool:
        endpoints = {
            "play": ("PUT", "/me/player/play"),
            "pause": ("PUT", "/me/player/pause"),
            "next": ("POST", "/me/player/next"),
            "prev": ("POST", "/me/player/previous"),
        }
        if action == "seek" and position_ms is not None:
            resp = self._request("PUT", f"/me/player/seek?position_ms={position_ms}")
            return resp is not None
        if action not in endpoints:
            return False
        method, endpoint = endpoints[action]
        resp = self._request(method, endpoint)
        return resp is not None

    def play_track(self, query: str) -> bool:
        resp = self._request("GET", "/search", params={"q": query, "type": "track", "limit": 1})
        if not resp:
            return False
        items = resp.json().get("tracks", {}).get("items", [])
        if not items:
            return False
        resp = self._request("PUT", "/me/player/play", json={"uris": [items[0]["uri"]]})
        return resp is not None

    def is_connected(self) -> bool:
        return bool(self._access_token or self._refresh_token)

    def get_auth_url(self, state: str = "") -> str:
        scopes = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
        from urllib.parse import urlencode
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": scopes,
            "show_dialog": "true",
        }
        if state:
            params["state"] = state
        return f"https://accounts.spotify.com/authorize?{urlencode(params)}"

    def exchange_code(self, code: str) -> bool:
        if not self.client_id or not self.client_secret:
            return False
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            self._save_tokens(self._access_token, self._refresh_token)
            return True
        return False


class LocalProvider(MusicProvider):
    """Fallback for local HTML5 audio (not fully implemented)."""
    def get_now_playing(self) -> Optional[TrackInfo]:
        return None

    def control(self, action: str, position_ms: Optional[int] = None) -> bool:
        return False

    def play_track(self, query: str) -> bool:
        return False

    def is_connected(self) -> bool:
        return False


def get_provider(service: str = "spotify") -> MusicProvider:
    if service == "spotify":
        return SpotifyProvider()
    return LocalProvider()