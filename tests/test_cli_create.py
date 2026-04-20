import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from playlist_convert.cli import cli
from playlist_convert.config import Settings
from playlist_convert.models import Track


def _make_settings() -> Settings:
    return Settings(SPOTIFY_CLIENT_ID="test", SPOTIFY_CLIENT_SECRET="test")


def _make_provider(search_results=None, playlist_id="new_pl_id"):
    provider = MagicMock()
    provider.service_name = "Spotify"
    provider.search_track.return_value = search_results if search_results is not None else []
    provider.create_playlist.return_value = playlist_id
    provider.add_tracks.return_value = None
    return provider


VALID_YAML = textwrap.dedent("""\
    name: Test Playlist
    description: A test playlist
    tracks:
      - title: Bohemian Rhapsody
        artist: Queen
      - title: Hotel California
        artist: Eagles
""")

_GOOD_TRACK = Track(title="Bohemian Rhapsody", artist="Queen", provider_uri="spotify:track:abc")


class TestCreateCommand:
    def setup_method(self):
        self.runner = CliRunner()

    def _invoke(self, yaml_content, extra_args=None, provider=None):
        if provider is None:
            provider = _make_provider()
        with self.runner.isolated_filesystem():
            with open("playlist.yaml", "w") as f:
                f.write(yaml_content)
            with patch("playlist_convert.cli._get_authenticated_provider", return_value=provider), \
                 patch("playlist_convert.cli.get_settings", return_value=_make_settings()):
                args = ["create", "--service", "spotify", "--file", "playlist.yaml"] + (extra_args or [])
                return self.runner.invoke(cli, args, catch_exceptions=False)

    # --- happy path ---

    def test_creates_playlist_with_matched_tracks(self):
        provider = _make_provider(search_results=[_GOOD_TRACK], playlist_id="pl_123")
        result = self._invoke(VALID_YAML, provider=provider)
        assert result.exit_code == 0
        assert "pl_123" in result.output
        provider.create_playlist.assert_called_once_with(name="Test Playlist", description="A test playlist")
        provider.add_tracks.assert_called_once()

    def test_name_from_yaml_used_by_default(self):
        provider = _make_provider(search_results=[_GOOD_TRACK])
        self._invoke(VALID_YAML, provider=provider)
        provider.create_playlist.assert_called_once_with(name="Test Playlist", description="A test playlist")

    def test_name_override_flag_takes_precedence(self):
        provider = _make_provider(search_results=[_GOOD_TRACK])
        self._invoke(VALID_YAML, ["--name", "My Override"], provider=provider)
        provider.create_playlist.assert_called_once_with(name="My Override", description="A test playlist")

    def test_track_with_optional_album_field(self):
        yaml_content = textwrap.dedent("""\
            name: Playlist
            tracks:
              - title: Bohemian Rhapsody
                artist: Queen
                album: A Night at the Opera
        """)
        provider = _make_provider(search_results=[_GOOD_TRACK])
        result = self._invoke(yaml_content, provider=provider)
        assert result.exit_code == 0

    # --- dry run ---

    def test_dry_run_does_not_create_playlist(self):
        provider = _make_provider(search_results=[_GOOD_TRACK])
        result = self._invoke(VALID_YAML, ["--dry-run"], provider=provider)
        assert result.exit_code == 0
        assert "Dry run" in result.output
        provider.create_playlist.assert_not_called()
        provider.add_tracks.assert_not_called()

    # --- json output ---

    def test_json_output_dry_run(self):
        provider = _make_provider(search_results=[_GOOD_TRACK])
        result = self._invoke(VALID_YAML, ["--dry-run", "--output", "json"], provider=provider)
        assert result.exit_code == 0
        # Status line is printed before the JSON block; extract from first '{'
        json_str = result.output[result.output.index("{"):]
        data = json.loads(json_str)
        assert data["dry_run"] is True
        assert "results" in data
        assert data["summary"]["total"] == 2

    def test_json_output_includes_matched_tracks(self):
        provider = _make_provider(search_results=[_GOOD_TRACK])
        result = self._invoke(VALID_YAML, ["--dry-run", "--output", "json"], provider=provider)
        json_str = result.output[result.output.index("{"):]
        data = json.loads(json_str)
        matched = [r for r in data["results"] if r["matched"] is not None]
        assert len(matched) > 0

    # --- error cases ---

    def test_aborts_when_no_tracks_matched(self):
        provider = _make_provider(search_results=[])
        result = self.runner.invoke(  # don't use catch_exceptions=False; _abort calls sys.exit
            cli,
            ["create", "--service", "spotify", "--file", "nonexistent.yaml"],
        )
        assert result.exit_code != 0

    def test_aborts_on_missing_name_in_yaml(self):
        yaml_content = "tracks:\n  - title: Song\n    artist: Artist\n"
        with self.runner.isolated_filesystem():
            with open("playlist.yaml", "w") as f:
                f.write(yaml_content)
            with patch("playlist_convert.cli._get_authenticated_provider", return_value=_make_provider()), \
                 patch("playlist_convert.cli.get_settings", return_value=_make_settings()):
                result = self.runner.invoke(cli, ["create", "--service", "spotify", "--file", "playlist.yaml"])
        assert result.exit_code != 0
        assert "name" in result.output.lower()

    def test_aborts_on_missing_tracks_key(self):
        result = self._invoke("name: Playlist\n")
        assert result.exit_code != 0

    def test_aborts_on_empty_tracks_list(self):
        result = self._invoke("name: Playlist\ntracks: []\n")
        assert result.exit_code != 0

    def test_aborts_on_track_missing_title(self):
        yaml_content = "name: Playlist\ntracks:\n  - artist: Queen\n"
        result = self._invoke(yaml_content)
        assert result.exit_code != 0
        assert "title" in result.output.lower() or "1" in result.output

    def test_aborts_on_track_missing_artist(self):
        yaml_content = "name: Playlist\ntracks:\n  - title: Song\n"
        result = self._invoke(yaml_content)
        assert result.exit_code != 0
        assert "artist" in result.output.lower() or "1" in result.output

    def test_no_match_summary_shown(self):
        provider = _make_provider(search_results=[])
        with self.runner.isolated_filesystem():
            with open("playlist.yaml", "w") as f:
                f.write(VALID_YAML)
            with patch("playlist_convert.cli._get_authenticated_provider", return_value=provider), \
                 patch("playlist_convert.cli.get_settings", return_value=_make_settings()):
                result = self.runner.invoke(cli, ["create", "--service", "spotify", "--file", "playlist.yaml"])
        assert result.exit_code != 0
        provider.create_playlist.assert_not_called()
