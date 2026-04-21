import spotipy
from spotipy.oauth2 import SpotifyOAuth

from playlist_convert.config import Settings
from playlist_convert.models import Playlist, Track
from playlist_convert.providers.base import (
    AuthenticationError,
    BaseProvider,
    PlaylistNotFoundError,
    RateLimitError,
)

_SCOPES = (
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-public "
    "playlist-modify-private"
)

_ADD_BATCH_SIZE = 100  # Spotify API limit per add-items call


class SpotifyProvider(BaseProvider):
    """Read/write provider using the Spotify Web API via spotipy."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sp: spotipy.Spotify | None = None
        self._user_id: str = ""

    @property
    def service_name(self) -> str:
        return "Spotify"

    def authenticate(self) -> None:
        """Initialize spotipy with OAuth. Opens browser on first run."""
        if not self._settings.spotify_client_id or not self._settings.spotify_client_secret:
            raise AuthenticationError(
                "Spotify credentials not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file.\n"
                "Create an app at https://developer.spotify.com/dashboard and add "
                f"{self._settings.spotify_redirect_uri} as a Redirect URI."
            )

        try:
            auth_manager = SpotifyOAuth(
                client_id=self._settings.spotify_client_id,
                client_secret=self._settings.spotify_client_secret,
                redirect_uri=self._settings.spotify_redirect_uri,
                scope=_SCOPES,
            )
            self._sp = spotipy.Spotify(auth_manager=auth_manager)
            user = self._sp.current_user()
            self._user_id = user["id"]
        except spotipy.SpotifyException as e:
            raise AuthenticationError(f"Spotify authentication failed: {e}") from e

    @property
    def _client(self) -> spotipy.Spotify:
        if self._sp is None:
            raise AuthenticationError("authenticate() must be called before using this provider.")
        return self._sp

    def get_user_playlists(self) -> list[Playlist]:
        playlists = []
        results = self._client.current_user_playlists(limit=50)
        while results:
            for item in results["items"]:
                playlists.append(
                    Playlist(
                        name=item["name"],
                        description=item.get("description", ""),
                        provider_id=item["id"],
                    )
                )
            results = self._client.next(results) if results["next"] else None
        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        try:
            results = self._client.playlist_tracks(playlist_id, limit=100)
        except spotipy.SpotifyException as e:
            if e.http_status == 404:
                raise PlaylistNotFoundError(
                    f"Spotify playlist '{playlist_id}' not found."
                ) from e
            raise

        tracks = []
        while results:
            for item in results["items"]:
                raw = item.get("track")
                if raw is None or raw.get("id") is None:
                    continue
                artists = ", ".join(a["name"] for a in raw.get("artists", []))
                album = raw.get("album", {}).get("name", "")
                isrc = raw.get("external_ids", {}).get("isrc", "")
                tracks.append(
                    Track(
                        title=raw["name"],
                        artist=artists,
                        album=album,
                        duration_ms=raw.get("duration_ms", 0),
                        isrc=isrc,
                        provider_id=raw["id"],
                        provider_uri=raw["uri"],
                    )
                )
            results = self._client.next(results) if results["next"] else None
        return tracks

    def search_track(self, title: str, artist: str) -> list[Track]:
        query = f"track:{title} artist:{artist}"
        try:
            results = self._client.search(q=query, type="track", limit=5)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get("Retry-After", 1))
                raise RateLimitError("Spotify rate limit hit.", retry_after=retry_after) from e
            raise

        tracks = []
        for raw in results["tracks"]["items"]:
            artists = ", ".join(a["name"] for a in raw.get("artists", []))
            isrc = raw.get("external_ids", {}).get("isrc", "")
            tracks.append(
                Track(
                    title=raw["name"],
                    artist=artists,
                    album=raw.get("album", {}).get("name", ""),
                    duration_ms=raw.get("duration_ms", 0),
                    isrc=isrc,
                    provider_id=raw["id"],
                    provider_uri=raw["uri"],
                )
            )
        return tracks

    def search_track_by_isrc(self, isrc: str) -> list[Track]:
        """Search by ISRC for high-confidence exact matching."""
        try:
            results = self._client.search(q=f"isrc:{isrc}", type="track", limit=5)
        except spotipy.SpotifyException:
            return []

        tracks = []
        for raw in results["tracks"]["items"]:
            artists = ", ".join(a["name"] for a in raw.get("artists", []))
            tracks.append(
                Track(
                    title=raw["name"],
                    artist=artists,
                    album=raw.get("album", {}).get("name", ""),
                    duration_ms=raw.get("duration_ms", 0),
                    isrc=raw.get("external_ids", {}).get("isrc", ""),
                    provider_id=raw["id"],
                    provider_uri=raw["uri"],
                )
            )
        return tracks

    def create_playlist(self, name: str, description: str = "") -> str:
        result = self._client._post(
            "me/playlists",
            payload={"name": name, "public": False, "description": description},
        )
        return result["id"]

    def add_tracks(self, playlist_id: str, tracks: list[Track]) -> None:
        uris = [t.provider_uri for t in tracks if t.provider_uri]
        for i in range(0, len(uris), _ADD_BATCH_SIZE):
            batch = uris[i : i + _ADD_BATCH_SIZE]
            self._client.playlist_add_items(playlist_id, batch)
