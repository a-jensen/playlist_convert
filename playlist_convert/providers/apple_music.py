import plistlib
from pathlib import Path

from playlist_convert.config import Settings
from playlist_convert.models import Playlist, Track
from playlist_convert.providers.base import (
    AuthenticationError,
    BaseProvider,
    PlaylistNotFoundError,
)

# Candidate locations for the Music library file, in priority order.
_LIBRARY_CANDIDATES = [
    Path("~/Music/Music/Music Library.musiclibrary/Library.musiclibrary"),
    Path("~/Music/Music/Music Library.musiclibrary"),
    Path("~/Music/iTunes/iTunes Music Library.xml"),
]


def _find_library() -> Path | None:
    for candidate in _LIBRARY_CANDIDATES:
        expanded = candidate.expanduser()
        if expanded.exists():
            return expanded
    return None


class AppleMusicProvider(BaseProvider):
    """
    Read-only provider that parses the local macOS Music app library file.
    No Apple Developer account required.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._library: dict = {}

    @property
    def service_name(self) -> str:
        return "Apple Music"

    def authenticate(self) -> None:
        """Locate and parse the local Music library file."""
        if self._settings.apple_library_path:
            library_path = Path(self._settings.apple_library_path).expanduser()
        else:
            library_path = _find_library()

        if library_path is None or not library_path.exists():
            raise AuthenticationError(
                "Apple Music library file not found. "
                "Ensure the Music app is installed and iCloud sync is enabled, "
                "or set APPLE_LIBRARY_PATH in your .env file.\n"
                "Searched locations:\n"
                + "\n".join(f"  {p.expanduser()}" for p in _LIBRARY_CANDIDATES)
            )

        with open(library_path, "rb") as f:
            self._library = plistlib.load(f)

    def get_user_playlists(self) -> list[Playlist]:
        playlists = []
        for entry in self._library.get("Playlists", []):
            # Skip system/smart playlists that don't have a user-visible name
            if entry.get("Distinguished Kind") or entry.get("Master"):
                continue
            playlists.append(
                Playlist(
                    name=entry.get("Name", "Untitled"),
                    provider_id=str(entry.get("Playlist ID", "")),
                )
            )
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        tracks_dict: dict[int, dict] = self._library.get("Tracks", {})

        target_playlist = None
        for entry in self._library.get("Playlists", []):
            if str(entry.get("Playlist ID", "")) == playlist_id:
                target_playlist = entry
                break

        if target_playlist is None:
            raise PlaylistNotFoundError(
                f"Playlist '{playlist_id}' not found in Apple Music library."
            )

        tracks = []
        for item in target_playlist.get("Playlist Items", []):
            track_id = item.get("Track ID")
            raw = tracks_dict.get(track_id) or tracks_dict.get(str(track_id))
            if raw is None:
                continue
            tracks.append(
                Track(
                    title=raw.get("Name", ""),
                    artist=raw.get("Artist", ""),
                    album=raw.get("Album", ""),
                    duration_ms=raw.get("Total Time", 0),
                    isrc=raw.get("ISRC", ""),
                    provider_id=str(track_id),
                )
            )
        return tracks

    def search_track(self, title: str, artist: str) -> list[Track]:
        raise NotImplementedError(
            "Apple Music (local library) does not support catalog search. "
            "This provider is read-only."
        )

    def create_playlist(self, name: str, description: str = "") -> str:
        raise NotImplementedError(
            "Creating playlists on Apple Music requires an Apple Developer account "
            "and MusicKit API access. This provider is read-only."
        )

    def add_tracks(self, playlist_id: str, tracks: list[Track]) -> None:
        raise NotImplementedError(
            "Adding tracks to Apple Music requires an Apple Developer account "
            "and MusicKit API access. This provider is read-only."
        )
