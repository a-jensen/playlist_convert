import plistlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from playlist_convert.config import Settings
from playlist_convert.providers.apple_music import AppleMusicProvider
from playlist_convert.providers.base import AuthenticationError, PlaylistNotFoundError


def _make_settings(library_path: str = "") -> Settings:
    return Settings(
        SPOTIFY_CLIENT_ID="",
        SPOTIFY_CLIENT_SECRET="",
        APPLE_LIBRARY_PATH=library_path,
    )


def _make_library(playlists=None, tracks=None) -> bytes:
    """Build a minimal Music library plist and return its bytes.

    plistlib requires all dict keys to be strings, matching the real Music library format.
    """
    # Ensure track keys are strings (plist format requirement)
    str_tracks = {str(k): v for k, v in (tracks or {}).items()}
    library = {
        "Tracks": str_tracks,
        "Playlists": playlists or [],
    }
    return plistlib.dumps(library)


def _write_library(tmp_path: Path, playlists=None, tracks=None) -> Path:
    library_file = tmp_path / "Library.musiclibrary"
    library_file.write_bytes(_make_library(playlists=playlists, tracks=tracks))
    return library_file


class TestAuthenticate:
    def test_authenticates_with_explicit_path(self, tmp_path):
        library_file = _write_library(tmp_path)
        provider = AppleMusicProvider(_make_settings(str(library_file)))
        provider.authenticate()  # should not raise

    def test_raises_if_path_not_found(self):
        provider = AppleMusicProvider(_make_settings("/nonexistent/path/Library.musiclibrary"))
        with pytest.raises(AuthenticationError, match="not found"):
            provider.authenticate()

    def test_raises_if_no_library_anywhere(self):
        provider = AppleMusicProvider(_make_settings())
        with patch("playlist_convert.providers.apple_music._find_library", return_value=None):
            with pytest.raises(AuthenticationError, match="not found"):
                provider.authenticate()

    def test_auto_detects_library(self, tmp_path):
        library_file = _write_library(tmp_path)
        provider = AppleMusicProvider(_make_settings())
        with patch("playlist_convert.providers.apple_music._find_library",
                   return_value=library_file):
            provider.authenticate()  # should not raise


class TestGetUserPlaylists:
    def _authenticated_provider(self, tmp_path, playlists=None, tracks=None):
        library_file = _write_library(tmp_path, playlists=playlists, tracks=tracks)
        provider = AppleMusicProvider(_make_settings(str(library_file)))
        provider.authenticate()
        return provider

    def test_returns_user_playlists(self, tmp_path):
        playlists = [
            {"Name": "My Favorites", "Playlist ID": 1, "Playlist Items": []},
            {"Name": "Road Trip", "Playlist ID": 2, "Playlist Items": []},
        ]
        provider = self._authenticated_provider(tmp_path, playlists=playlists)
        result = provider.get_user_playlists()
        assert len(result) == 2
        assert result[0].name == "My Favorites"
        assert result[0].provider_id == "1"
        assert result[1].name == "Road Trip"

    def test_skips_master_playlist(self, tmp_path):
        playlists = [
            {"Name": "Library", "Playlist ID": 1, "Master": True, "Playlist Items": []},
            {"Name": "My Mix", "Playlist ID": 2, "Playlist Items": []},
        ]
        provider = self._authenticated_provider(tmp_path, playlists=playlists)
        result = provider.get_user_playlists()
        assert len(result) == 1
        assert result[0].name == "My Mix"

    def test_skips_distinguished_kind_playlists(self, tmp_path):
        playlists = [
            {"Name": "Recently Added", "Playlist ID": 1,
             "Distinguished Kind": 22, "Playlist Items": []},
            {"Name": "My Playlist", "Playlist ID": 2, "Playlist Items": []},
        ]
        provider = self._authenticated_provider(tmp_path, playlists=playlists)
        result = provider.get_user_playlists()
        assert len(result) == 1
        assert result[0].name == "My Playlist"

    def test_empty_library(self, tmp_path):
        provider = self._authenticated_provider(tmp_path)
        assert provider.get_user_playlists() == []

    def test_playlist_has_no_tracks_loaded(self, tmp_path):
        playlists = [{"Name": "Test", "Playlist ID": 1, "Playlist Items": []}]
        provider = self._authenticated_provider(tmp_path, playlists=playlists)
        result = provider.get_user_playlists()
        assert result[0].tracks == []


class TestGetPlaylistTracks:
    def _provider_with_data(self, tmp_path):
        tracks = {
            101: {
                "Name": "Bohemian Rhapsody",
                "Artist": "Queen",
                "Album": "A Night at the Opera",
                "Total Time": 354000,
                "ISRC": "GBBKS7200074",
            },
            102: {
                "Name": "We Will Rock You",
                "Artist": "Queen",
                "Album": "News of the World",
                "Total Time": 122000,
                "ISRC": "GBBKS7800119",
            },
        }
        playlists = [
            {
                "Name": "Queen Hits",
                "Playlist ID": 10,
                "Playlist Items": [{"Track ID": 101}, {"Track ID": 102}],
            },
            {
                "Name": "Empty Playlist",
                "Playlist ID": 20,
                "Playlist Items": [],
            },
        ]
        library_file = _write_library(tmp_path, playlists=playlists, tracks=tracks)
        provider = AppleMusicProvider(_make_settings(str(library_file)))
        provider.authenticate()
        return provider

    def test_returns_tracks_for_playlist(self, tmp_path):
        provider = self._provider_with_data(tmp_path)
        tracks = provider.get_playlist_tracks("10")
        assert len(tracks) == 2
        assert tracks[0].title == "Bohemian Rhapsody"
        assert tracks[0].artist == "Queen"
        assert tracks[0].album == "A Night at the Opera"
        assert tracks[0].duration_ms == 354000
        assert tracks[0].isrc == "GBBKS7200074"
        assert tracks[0].provider_id == "101"

    def test_second_track_populated(self, tmp_path):
        provider = self._provider_with_data(tmp_path)
        tracks = provider.get_playlist_tracks("10")
        assert tracks[1].title == "We Will Rock You"
        assert tracks[1].isrc == "GBBKS7800119"

    def test_empty_playlist_returns_empty_list(self, tmp_path):
        provider = self._provider_with_data(tmp_path)
        tracks = provider.get_playlist_tracks("20")
        assert tracks == []

    def test_raises_for_unknown_playlist_id(self, tmp_path):
        provider = self._provider_with_data(tmp_path)
        with pytest.raises(PlaylistNotFoundError):
            provider.get_playlist_tracks("9999")

    def test_skips_missing_track_ids(self, tmp_path):
        tracks = {101: {"Name": "Real Track", "Artist": "Artist"}}
        playlists = [
            {
                "Name": "Mixed",
                "Playlist ID": 1,
                "Playlist Items": [{"Track ID": 101}, {"Track ID": 9999}],
            }
        ]
        library_file = _write_library(tmp_path, playlists=playlists, tracks=tracks)
        provider = AppleMusicProvider(_make_settings(str(library_file)))
        provider.authenticate()
        tracks_result = provider.get_playlist_tracks("1")
        assert len(tracks_result) == 1
        assert tracks_result[0].title == "Real Track"


class TestReadOnlyMethods:
    def _provider(self, tmp_path):
        library_file = _write_library(tmp_path)
        provider = AppleMusicProvider(_make_settings(str(library_file)))
        provider.authenticate()
        return provider

    def test_search_track_raises(self, tmp_path):
        provider = self._provider(tmp_path)
        with pytest.raises(NotImplementedError):
            provider.search_track("Any", "Artist")

    def test_create_playlist_raises(self, tmp_path):
        provider = self._provider(tmp_path)
        with pytest.raises(NotImplementedError):
            provider.create_playlist("New Playlist")

    def test_add_tracks_raises(self, tmp_path):
        provider = self._provider(tmp_path)
        with pytest.raises(NotImplementedError):
            provider.add_tracks("1", [])

    def test_service_name(self, tmp_path):
        provider = self._provider(tmp_path)
        assert provider.service_name == "Apple Music"
