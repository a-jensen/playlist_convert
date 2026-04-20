from abc import ABC, abstractmethod

from playlist_convert.models import Playlist, Track


class PlaylistConvertError(Exception):
    """Base class for all domain exceptions."""


class AuthenticationError(PlaylistConvertError):
    """Authentication failed or credentials not found."""


class PlaylistNotFoundError(PlaylistConvertError):
    """Playlist ID is invalid or inaccessible."""


class TrackNotFoundError(PlaylistConvertError):
    """No matching track found on the target service."""


class RateLimitError(PlaylistConvertError):
    """Provider rate limit hit."""

    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BaseProvider(ABC):
    """
    Abstract interface every streaming service provider must implement.

    Lifecycle:
        provider = ConcreteProvider(settings)
        provider.authenticate()
        playlists = provider.get_user_playlists()
        tracks = provider.get_playlist_tracks(playlist_id)
        new_id = provider.create_playlist(name, description)
        provider.add_tracks(new_id, tracks)
    """

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Human-readable name, e.g. 'Spotify' or 'Apple Music'."""

    @abstractmethod
    def authenticate(self) -> None:
        """
        Perform authentication. Must be called before any other method.
        Raises AuthenticationError on failure.
        """

    @abstractmethod
    def get_user_playlists(self) -> list[Playlist]:
        """
        Return all playlists owned by or saved to the authenticated user.
        Tracks list on each Playlist will be empty.
        """

    @abstractmethod
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """
        Return all tracks for the given provider-native playlist ID.
        Raises PlaylistNotFoundError if the ID is invalid or inaccessible.
        """

    @abstractmethod
    def search_track(self, title: str, artist: str) -> list[Track]:
        """
        Search the service's catalog. Returns up to 5 candidate Track objects.
        """

    @abstractmethod
    def create_playlist(self, name: str, description: str = "") -> str:
        """
        Create a new empty playlist owned by the authenticated user.
        Returns the provider-native playlist ID.
        """

    @abstractmethod
    def add_tracks(self, playlist_id: str, tracks: list[Track]) -> None:
        """
        Add the given tracks to the playlist. Tracks must have provider_uri populated.
        Batches requests internally as needed.
        """
