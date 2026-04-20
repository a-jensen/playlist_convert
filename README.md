# playlist-convert

A command-line tool to list and convert playlists between streaming music services.

**Supported services:**

| Service | List playlists | List songs | Convert from | Convert to |
|---|---|---|---|---|
| Apple Music | yes | yes | yes | no* |
| Spotify | yes | yes | yes | yes |

\* Writing to Apple Music requires an Apple Developer account (MusicKit API). Reading uses the local macOS Music library — no account needed.

---

## Installation

```bash
git clone <repo>
cd playlist_convert
pip install -e .
```

This registers the `playlist-convert` command in your shell.

---

## Setup

### Apple Music

No setup required. The tool reads your local Music app library on macOS automatically. It looks for the library in these locations (in order):

1. `~/Music/Music/Music Library.musiclibrary/Library.musiclibrary` (macOS Sonoma and later)
2. `~/Music/Music/Music Library.musiclibrary` (older macOS Music app)
3. `~/Music/iTunes/iTunes Music Library.xml` (legacy iTunes)

If your library is in a non-standard location, set `APPLE_LIBRARY_PATH` in your `.env` file.

**Requirement:** iCloud Music Library sync should be enabled so your playlists appear in the local library.

### Spotify

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create an application.
2. In the app settings, add `http://127.0.0.1:8000/callback` to the **Redirect URIs**.
3. Copy your Client ID and Client Secret.
4. Create a `.env` file in the project root:

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

`.env` contents:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/callback
```

On the first run of any Spotify command, your browser will open for authorization. The token is cached at `~/.cache-spotify` and refreshed automatically on subsequent runs.

---

## Commands

### `list-playlists`

List all playlists for a service.

```bash
playlist-convert list-playlists --service <service>
```

**Options:**

| Flag | Description |
|---|---|
| `-s`, `--service` | `spotify` or `apple-music` (required) |
| `-o`, `--output` | `table` (default) or `json` |

**Examples:**

```bash
playlist-convert list-playlists --service apple-music
playlist-convert list-playlists --service spotify --output json
```

**Example output:**

```
               Apple Music Playlists
┌──────────┬──────────────────────┬─────────────┐
│ ID       │ Name                 │ Description │
├──────────┼──────────────────────┼─────────────┤
│ 12345    │ My Favorites         │             │
│ 67890    │ Road Trip            │             │
└──────────┴──────────────────────┴─────────────┘

2 playlist(s)
```

---

### `list-songs`

List all songs in a specific playlist.

```bash
playlist-convert list-songs --service <service> --playlist-id <id>
```

**Options:**

| Flag | Description |
|---|---|
| `-s`, `--service` | `spotify` or `apple-music` (required) |
| `-p`, `--playlist-id` | Provider-native playlist ID (required) |
| `-o`, `--output` | `table` (default) or `json` |

Use `list-playlists` to find playlist IDs.

**Examples:**

```bash
playlist-convert list-songs --service apple-music --playlist-id 12345
playlist-convert list-songs --service spotify --playlist-id 37i9dQZF1DXcBWIGoYBM5M
playlist-convert list-songs --service spotify --playlist-id 37i9dQZF1DXcBWIGoYBM5M --output json
```

---

### `convert`

Convert a playlist from one service to another.

```bash
playlist-convert convert --from <service> --to <service> --playlist-id <id>
```

**Options:**

| Flag | Description |
|---|---|
| `--from` | Source service: `spotify` or `apple-music` (required) |
| `--to` | Destination service: `spotify` or `apple-music` (required) |
| `-p`, `--playlist-id` | Playlist ID on the source service (required) |
| `-n`, `--name` | Name for the new playlist (defaults to original name) |
| `--dry-run` | Show matching results without creating anything |
| `-o`, `--output` | `table` (default) or `json` |

**Examples:**

```bash
# Preview what would be matched before committing
playlist-convert convert --from apple-music --to spotify --playlist-id 12345 --dry-run

# Convert and create the playlist on Spotify
playlist-convert convert --from apple-music --to spotify --playlist-id 12345

# Convert with a custom name
playlist-convert convert --from apple-music --to spotify --playlist-id 12345 --name "My Playlist"

# Convert in both directions (Spotify → Apple Music requires developer account)
playlist-convert convert --from spotify --to apple-music --playlist-id 37i9dQZF1DXcBWIGoYBM5M
```

**Example output:**

```
Fetching tracks from Apple Music...
Found 42 track(s). Matching on Spotify...

                   Track Matching Results
┌──────────────────┬───────────────┬──────────────────┬───────────────┬────────┬───────┐
│ Source Title     │ Source Artist │ Matched Title    │ Matched Artist│ Method │ Conf. │
├──────────────────┼───────────────┼──────────────────┼───────────────┼────────┼───────┤
│ Bohemian Rhapsody│ Queen         │ Bohemian Rhapsody│ Queen         │ isrc   │  100% │
│ Blinding Lights  │ The Weeknd    │ Blinding Lights  │ The Weeknd    │ isrc   │  100% │
│ Some Song        │ Artist Name   │ —                │ —             │ none   │     — │
└──────────────────┴───────────────┴──────────────────┴───────────────┴────────┴───────┘

Matched: 41/42
Unmatched: 1 track(s)
  - Artist Name — Some Song

Creating playlist 'My Playlist' on Spotify...
Done! Playlist created with 41 track(s).
Playlist ID: 4uLU6hMCjMI75M1A2tKUQC
```

---

## Song Matching

When converting, the tool matches each source track to the destination service's catalog using a two-step strategy:

1. **ISRC exact match** (confidence 100%): Both Apple Music and Spotify expose the [ISRC](https://en.wikipedia.org/wiki/International_Standard_Recording_Code), a globally unique identifier per recording. When both the source track and a search result have an ISRC, this is checked first.

2. **Fuzzy text match**: Searches by title + artist, then scores candidates using `token_sort_ratio` (handles "feat." variations, word reordering, punctuation differences). The score weights title at 60% and artist at 40%. A candidate must score ≥ 85 to be accepted.

Unmatched tracks are listed in the conversion summary but do not cause an error.

**Tuning the threshold:**

```
FUZZY_MATCH_THRESHOLD=70.0   # more lenient — accepts looser matches
FUZZY_MATCH_THRESHOLD=95.0   # stricter — fewer false positives
```

---

## Configuration

All settings are read from a `.env` file in the project root (or environment variables).

| Variable | Default | Description |
|---|---|---|
| `SPOTIFY_CLIENT_ID` | — | Spotify app Client ID |
| `SPOTIFY_CLIENT_SECRET` | — | Spotify app Client Secret |
| `SPOTIFY_REDIRECT_URI` | `http://localhost:8888/callback` | OAuth redirect URI |
| `APPLE_LIBRARY_PATH` | auto-detected | Path to Music library file |
| `FUZZY_MATCH_THRESHOLD` | `85.0` | Minimum fuzzy match score (0–100) |

---

## Adding a New Service

The provider interface is designed to make adding services straightforward:

1. Create `playlist_convert/providers/<name>.py` and implement `BaseProvider`:

```python
from playlist_convert.providers.base import BaseProvider
from playlist_convert.models import Playlist, Track

class MyServiceProvider(BaseProvider):
    @property
    def service_name(self) -> str:
        return "My Service"

    def authenticate(self) -> None: ...
    def get_user_playlists(self) -> list[Playlist]: ...
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]: ...
    def search_track(self, title: str, artist: str) -> list[Track]: ...
    def create_playlist(self, name: str, description: str = "") -> str: ...
    def add_tracks(self, playlist_id: str, tracks: list[Track]) -> None: ...
```

2. Register it in `playlist_convert/registry.py`:

```python
from playlist_convert.providers.my_service import MyServiceProvider

PROVIDER_REGISTRY = {
    ...
    "my-service": MyServiceProvider,
}
```

3. Add `"my-service"` to `_SERVICES` in `playlist_convert/cli.py`.

---

## Project Structure

```
playlist_convert/
├── pyproject.toml
├── requirements.txt
├── .env.example
└── playlist_convert/
    ├── cli.py              # Click CLI — list-playlists, list-songs, convert
    ├── config.py           # Settings loaded from .env
    ├── matcher.py          # ISRC + fuzzy song matching logic
    ├── models.py           # Track, Playlist dataclasses
    ├── registry.py         # Maps service name string → provider class
    └── providers/
        ├── base.py         # BaseProvider ABC + exception types
        ├── apple_music.py  # Read-only via local macOS plist
        └── spotify.py      # Read/write via Spotify Web API
```

## Dependencies

| Package | Purpose |
|---|---|
| `click` | CLI framework |
| `spotipy` | Spotify Web API client + OAuth |
| `pydantic-settings` | Type-safe settings from env / `.env` file |
| `rapidfuzz` | Fast fuzzy string matching for song title/artist |
| `rich` | Terminal tables and progress display |
