from unittest.mock import MagicMock, patch

import pytest
import spotipy

from playlist_convert.config import Settings
from playlist_convert.models import Track
from playlist_convert.providers.base import AuthenticationError, PlaylistNotFoundError
from playlist_convert.providers.spotify import SpotifyProvider


def _make_settings(**kwargs) -> Settings:
    defaults = dict(
        SPOTIFY_CLIENT_ID="test_client_id",
        SPOTIFY_CLIENT_SECRET="test_client_secret",
        SPOTIFY_REDIRECT_URI="http://localhost:8888/callback",
    )
    return Settings(**{**defaults, **kwargs})


def _make_raw_track(
    track_id="abc123",
    name="Test Song",
    artists=None,
    album="Test Album",
    duration_ms=200000,
    isrc="USAT29900609",
    uri=None,
) -> dict:
    return {
        "id": track_id,
        "name": name,
        "artists": artists or [{"name": "Test Artist"}],
        "album": {"name": album},
        "duration_ms": duration_ms,
        "external_ids": {"isrc": isrc},
        "uri": uri or f"spotify:track:{track_id}",
    }


def _make_playlist_item(raw_track: dict) -> dict:
    return {"track": raw_track}


def _make_provider(settings=None) -> tuple[SpotifyProvider, MagicMock]:
    """Return (provider, mock_spotipy_client). Provider is already authenticated."""
    settings = settings or _make_settings()
    provider = SpotifyProvider(settings)

    mock_sp = MagicMock(spec=spotipy.Spotify)
    mock_sp.current_user.return_value = {"id": "test_user"}

    with patch("playlist_convert.providers.spotify.SpotifyOAuth"), \
         patch("playlist_convert.providers.spotify.spotipy.Spotify", return_value=mock_sp):
        provider.authenticate()

    return provider, mock_sp


class TestAuthenticate:
    def test_raises_if_no_credentials(self):
        provider = SpotifyProvider(_make_settings(SPOTIFY_CLIENT_ID="", SPOTIFY_CLIENT_SECRET=""))
        with pytest.raises(AuthenticationError, match="credentials not configured"):
            provider.authenticate()

    def test_raises_if_client_id_missing(self):
        provider = SpotifyProvider(_make_settings(SPOTIFY_CLIENT_ID=""))
        with pytest.raises(AuthenticationError):
            provider.authenticate()

    def test_successful_auth_stores_user_id(self):
        provider, mock_sp = _make_provider()
        assert provider._user_id == "test_user"

    def test_raises_auth_error_on_spotify_exception(self):
        settings = _make_settings()
        provider = SpotifyProvider(settings)
        mock_sp = MagicMock(spec=spotipy.Spotify)
        mock_sp.current_user.side_effect = spotipy.SpotifyException(401, -1, "Unauthorized")

        with patch("playlist_convert.providers.spotify.SpotifyOAuth"), \
             patch("playlist_convert.providers.spotify.spotipy.Spotify", return_value=mock_sp):
            with pytest.raises(AuthenticationError, match="authentication failed"):
                provider.authenticate()

    def test_service_name(self):
        provider = SpotifyProvider(_make_settings())
        assert provider.service_name == "Spotify"


class TestGetUserPlaylists:
    def test_returns_playlists(self):
        provider, mock_sp = _make_provider()
        mock_sp.current_user_playlists.return_value = {
            "items": [
                {"id": "pl1", "name": "My Mix", "description": "A great mix"},
                {"id": "pl2", "name": "Chill", "description": ""},
            ],
            "next": None,
        }
        playlists = provider.get_user_playlists()
        assert len(playlists) == 2
        assert playlists[0].provider_id == "pl1"
        assert playlists[0].name == "My Mix"
        assert playlists[0].description == "A great mix"
        assert playlists[1].name == "Chill"

    def test_handles_pagination(self):
        provider, mock_sp = _make_provider()
        page1 = {
            "items": [{"id": "pl1", "name": "Playlist 1", "description": ""}],
            "next": "http://next-page",
        }
        page2 = {
            "items": [{"id": "pl2", "name": "Playlist 2", "description": ""}],
            "next": None,
        }
        mock_sp.current_user_playlists.return_value = page1
        mock_sp.next.side_effect = [page2, None]
        playlists = provider.get_user_playlists()
        assert len(playlists) == 2

    def test_empty_playlists(self):
        provider, mock_sp = _make_provider()
        mock_sp.current_user_playlists.return_value = {"items": [], "next": None}
        assert provider.get_user_playlists() == []


class TestGetPlaylistTracks:
    def test_returns_tracks(self):
        provider, mock_sp = _make_provider()
        raw = _make_raw_track("t1", "Bohemian Rhapsody",
                              artists=[{"name": "Queen"}], isrc="GBBKS7200074")
        mock_sp.playlist_tracks.return_value = {
            "items": [_make_playlist_item(raw)],
            "next": None,
        }
        tracks = provider.get_playlist_tracks("pl1")
        assert len(tracks) == 1
        assert tracks[0].title == "Bohemian Rhapsody"
        assert tracks[0].artist == "Queen"
        assert tracks[0].isrc == "GBBKS7200074"
        assert tracks[0].provider_uri == "spotify:track:t1"

    def test_multiple_artists_joined(self):
        provider, mock_sp = _make_provider()
        raw = _make_raw_track(artists=[{"name": "Post Malone"}, {"name": "Swae Lee"}])
        mock_sp.playlist_tracks.return_value = {"items": [_make_playlist_item(raw)], "next": None}
        tracks = provider.get_playlist_tracks("pl1")
        assert tracks[0].artist == "Post Malone, Swae Lee"

    def test_skips_null_tracks(self):
        provider, mock_sp = _make_provider()
        mock_sp.playlist_tracks.return_value = {
            "items": [{"track": None}, _make_playlist_item(_make_raw_track())],
            "next": None,
        }
        tracks = provider.get_playlist_tracks("pl1")
        assert len(tracks) == 1

    def test_raises_playlist_not_found(self):
        provider, mock_sp = _make_provider()
        mock_sp.playlist_tracks.side_effect = spotipy.SpotifyException(404, -1, "Not found")
        with pytest.raises(PlaylistNotFoundError):
            provider.get_playlist_tracks("bad_id")

    def test_handles_pagination(self):
        provider, mock_sp = _make_provider()
        page1 = {
            "items": [_make_playlist_item(_make_raw_track("t1"))],
            "next": "http://next",
        }
        page2 = {
            "items": [_make_playlist_item(_make_raw_track("t2"))],
            "next": None,
        }
        mock_sp.playlist_tracks.return_value = page1
        mock_sp.next.side_effect = [page2, None]
        tracks = provider.get_playlist_tracks("pl1")
        assert len(tracks) == 2


class TestSearchTrack:
    def test_returns_candidates(self):
        provider, mock_sp = _make_provider()
        raw1 = _make_raw_track("s1", "Hello", artists=[{"name": "Adele"}])
        raw2 = _make_raw_track("s2", "Hello", artists=[{"name": "Lionel Richie"}])
        mock_sp.search.return_value = {"tracks": {"items": [raw1, raw2]}}
        results = provider.search_track("Hello", "Adele")
        assert len(results) == 2
        assert results[0].title == "Hello"
        assert results[0].artist == "Adele"

    def test_empty_results(self):
        provider, mock_sp = _make_provider()
        mock_sp.search.return_value = {"tracks": {"items": []}}
        assert provider.search_track("Unknown Song", "Unknown Artist") == []

    def test_search_includes_isrc_field(self):
        provider, mock_sp = _make_provider()
        raw = _make_raw_track(isrc="USAT29900609")
        mock_sp.search.return_value = {"tracks": {"items": [raw]}}
        results = provider.search_track("Livin on a Prayer", "Bon Jovi")
        assert results[0].isrc == "USAT29900609"


class TestSearchTrackByIsrc:
    def test_returns_results_for_valid_isrc(self):
        provider, mock_sp = _make_provider()
        raw = _make_raw_track("t1", "Some Song", isrc="GBBKS7200074")
        mock_sp.search.return_value = {"tracks": {"items": [raw]}}
        results = provider.search_track_by_isrc("GBBKS7200074")
        assert len(results) == 1
        assert results[0].provider_id == "t1"

    def test_returns_empty_on_spotify_exception(self):
        provider, mock_sp = _make_provider()
        mock_sp.search.side_effect = spotipy.SpotifyException(400, -1, "Bad request")
        results = provider.search_track_by_isrc("BADINPUT")
        assert results == []


class TestCreatePlaylist:
    def test_returns_new_playlist_id(self):
        provider, mock_sp = _make_provider()
        mock_sp.user_playlist_create.return_value = {"id": "new_pl_id"}
        result = provider.create_playlist("My New Playlist", "A description")
        assert result == "new_pl_id"
        mock_sp.user_playlist_create.assert_called_once_with(
            user="test_user",
            name="My New Playlist",
            public=False,
            description="A description",
        )

    def test_creates_with_empty_description(self):
        provider, mock_sp = _make_provider()
        mock_sp.user_playlist_create.return_value = {"id": "pl_id"}
        provider.create_playlist("Minimal")
        mock_sp.user_playlist_create.assert_called_once()


class TestAddTracks:
    def test_adds_tracks_in_single_batch(self):
        provider, mock_sp = _make_provider()
        tracks = [Track(title="T", artist="A", provider_uri=f"spotify:track:{i}") for i in range(3)]
        provider.add_tracks("pl1", tracks)
        mock_sp.playlist_add_items.assert_called_once_with(
            "pl1", [f"spotify:track:{i}" for i in range(3)]
        )

    def test_batches_large_track_lists(self):
        provider, mock_sp = _make_provider()
        # 150 tracks should be sent in 2 batches (100 + 50)
        tracks = [Track(title="T", artist="A", provider_uri=f"spotify:track:{i}") for i in range(150)]
        provider.add_tracks("pl1", tracks)
        assert mock_sp.playlist_add_items.call_count == 2
        first_batch = mock_sp.playlist_add_items.call_args_list[0][0][1]
        second_batch = mock_sp.playlist_add_items.call_args_list[1][0][1]
        assert len(first_batch) == 100
        assert len(second_batch) == 50

    def test_skips_tracks_without_uri(self):
        provider, mock_sp = _make_provider()
        tracks = [
            Track(title="Has URI", artist="A", provider_uri="spotify:track:abc"),
            Track(title="No URI", artist="B", provider_uri=""),
        ]
        provider.add_tracks("pl1", tracks)
        mock_sp.playlist_add_items.assert_called_once_with("pl1", ["spotify:track:abc"])

    def test_does_not_call_api_if_no_valid_uris(self):
        provider, mock_sp = _make_provider()
        tracks = [Track(title="T", artist="A", provider_uri="")]
        provider.add_tracks("pl1", tracks)
        mock_sp.playlist_add_items.assert_not_called()
