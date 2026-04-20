import pytest

from playlist_convert.config import Settings
from playlist_convert.providers.apple_music import AppleMusicProvider
from playlist_convert.providers.spotify import SpotifyProvider
from playlist_convert.registry import get_provider


def _settings() -> Settings:
    return Settings(SPOTIFY_CLIENT_ID="", SPOTIFY_CLIENT_SECRET="")


class TestGetProvider:
    def test_returns_spotify_provider(self):
        provider = get_provider("spotify", _settings())
        assert isinstance(provider, SpotifyProvider)

    def test_returns_apple_music_provider(self):
        provider = get_provider("apple-music", _settings())
        assert isinstance(provider, AppleMusicProvider)

    def test_case_insensitive(self):
        provider = get_provider("Spotify", _settings())
        assert isinstance(provider, SpotifyProvider)

    def test_underscore_normalized_to_hyphen(self):
        provider = get_provider("apple_music", _settings())
        assert isinstance(provider, AppleMusicProvider)

    def test_raises_for_unknown_service(self):
        with pytest.raises(ValueError, match="Unknown service"):
            get_provider("tidal", _settings())

    def test_error_message_lists_known_services(self):
        with pytest.raises(ValueError, match="spotify"):
            get_provider("unknown", _settings())
