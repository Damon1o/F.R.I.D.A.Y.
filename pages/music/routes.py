"""Music page + API routes: now playing, controls, Spotify OAuth."""
from flask import Blueprint, jsonify, request, redirect, session, current_app, render_template
from pages.music import get_provider

music_bp = Blueprint("music", __name__)


@music_bp.route("/music")
def music_page():
    return render_template("music.html")


@music_bp.route("/api/music/now-playing")
def now_playing():
    service = request.args.get("service", "spotify")
    provider = get_provider(service)
    track = provider.get_now_playing()
    if not track:
        return jsonify({"connected": provider.is_connected(), "playing": False})
    return jsonify({
        "connected": True,
        "playing": True,
        "title": track.title,
        "artist": track.artist,
        "album_art": track.album_art,
        "progress_ms": track.progress_ms,
        "duration_ms": track.duration_ms,
        "is_playing": track.is_playing,
    })

@music_bp.route("/api/music/control", methods=["POST"])
def control():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    position_ms = data.get("position_ms")
    service = data.get("service", "spotify")
    provider = get_provider(service)
    ok = provider.control(action, position_ms)
    return jsonify({"ok": ok})

@music_bp.route("/api/music/spotify/login")
def spotify_login():
    provider = get_provider("spotify")
    auth_url = provider.get_auth_url(state="friday-music")
    return redirect(auth_url)

@music_bp.route("/api/music/spotify/callback")
def spotify_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return redirect("/settings?music_error=spotify_auth_failed")
    provider = get_provider("spotify")
    if provider.exchange_code(code):
        return redirect("/settings?music_connected=spotify")
    return redirect("/settings?music_error=spotify_token_exchange_failed")

@music_bp.route("/api/music/status")
def status():
    service = request.args.get("service", "spotify")
    provider = get_provider(service)
    return jsonify({"connected": provider.is_connected(), "service": service})