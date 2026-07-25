# F.R.I.D.A.Y. — Music Control Extensions Design (Spec O)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A, existing music module (`pages/music/`, `SpotifyProvider`,
`control_music`/`play_track` tools).

## 1. Context

Current music tools cover play/pause/next/prev/seek and play-a-track. Round it out
with the everyday controls a voice assistant needs: know what's playing, queue
songs, adjust volume, and play a named playlist. Extends the existing
`MusicProvider` interface and the two existing tools.

## 2. Goals / Non-goals

**Goals**
- `get_now_playing()` — current track/artist/progress.
- `queue_track(query)` — search + add to queue (don't interrupt current).
- `set_volume(percent)`.
- `play_playlist(name)` — find a user playlist by name and start it.

**Non-goals**
- Multi-provider parity beyond the existing `LocalProvider` stub (implement for
  Spotify; stub the rest to satisfy the interface, as done for `play_track`).
- Library management (save/like/create playlist).
- Lyrics, audio analysis, crossfade settings.

## 3. Design

**Interface** (`MusicProvider`): add abstract `now_playing`, `queue`, `set_volume`,
`play_playlist`. `SpotifyProvider` implements via Web API
(`/me/player/currently-playing`, `/me/player/queue`, `/me/player/volume`,
playlist search + `/me/player/play` with `context_uri`). `LocalProvider` stubs
each (mirrors the existing `play_track` stub pattern).

**Tools** (add to `TOOLS` + `dispatch`):
- `get_now_playing` {} , `queue_track` {`query`}, `set_volume` {`percent`},
  `play_playlist` {`name`}.

Token persistence + refresh already handled by the existing provider (Spec-A-era
settings persistence). No new auth.

## 4. Testing

- Extend `test_music.py`: each new provider method against faked Spotify HTTP;
  each new tool dispatches to the provider (fake provider), asserts shape.
- `now_playing` when nothing is playing → sane empty result, not an error.

## 5. Risks

- **Spotify requires an active device** for queue/volume/play — surface Spotify's
  "no active device" as a clear tool error the agent can relay.
- **Playlist name ambiguity** — return candidates when multiple match.
