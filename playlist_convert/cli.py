import json
import sys

import yaml

import click
from rich.console import Console
from rich.table import Table

from playlist_convert.config import get_settings
from playlist_convert.matcher import MatchResult, match_track
from playlist_convert.models import Track
from playlist_convert.providers.base import PlaylistConvertError
from playlist_convert.providers.spotify import SpotifyProvider
from playlist_convert.registry import get_provider

console = Console()
err_console = Console(stderr=True)

_SERVICES = ["spotify", "apple-music"]


def _abort(message: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {message}")
    sys.exit(1)


def _get_authenticated_provider(service: str):
    settings = get_settings()
    try:
        provider = get_provider(service, settings)
        provider.authenticate()
        return provider
    except PlaylistConvertError as e:
        _abort(str(e))
    except ValueError as e:
        _abort(str(e))


@click.group()
def cli():
    """Convert and list playlists between streaming music services."""


@cli.command("list-playlists")
@click.option(
    "--service", "-s",
    required=True,
    type=click.Choice(_SERVICES),
    help="Streaming service to list playlists from.",
)
@click.option(
    "--output", "-o",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Output format.",
)
def list_playlists(service: str, output: str) -> None:
    """List all playlists for a streaming service."""
    provider = _get_authenticated_provider(service)
    try:
        playlists = provider.get_user_playlists()
    except PlaylistConvertError as e:
        _abort(str(e))
        return

    if output == "json":
        data = [{"id": p.provider_id, "name": p.name, "description": p.description}
                for p in playlists]
        click.echo(json.dumps(data, indent=2))
        return

    table = Table(title=f"{provider.service_name} Playlists", show_lines=False)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Description")

    for p in playlists:
        table.add_row(p.provider_id, p.name, p.description or "")

    console.print(table)
    console.print(f"\n[dim]{len(playlists)} playlist(s)[/dim]")


@cli.command("list-songs")
@click.option(
    "--service", "-s",
    required=True,
    type=click.Choice(_SERVICES),
    help="Streaming service.",
)
@click.option("--playlist-id", "-p", required=True, help="Provider-native playlist ID.")
@click.option(
    "--output", "-o",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Output format.",
)
def list_songs(service: str, playlist_id: str, output: str) -> None:
    """List songs in a playlist."""
    provider = _get_authenticated_provider(service)
    try:
        tracks = provider.get_playlist_tracks(playlist_id)
    except PlaylistConvertError as e:
        _abort(str(e))
        return

    if output == "json":
        data = [
            {
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "duration_ms": t.duration_ms,
                "isrc": t.isrc,
                "id": t.provider_id,
            }
            for t in tracks
        ]
        click.echo(json.dumps(data, indent=2))
        return

    table = Table(title=f"Songs in playlist {playlist_id}", show_lines=False)
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Title", style="bold")
    table.add_column("Artist")
    table.add_column("Album")
    table.add_column("Duration", justify="right", width=8)

    for i, t in enumerate(tracks, 1):
        duration = _format_duration(t.duration_ms)
        table.add_row(str(i), t.title, t.artist, t.album, duration)

    console.print(table)
    console.print(f"\n[dim]{len(tracks)} track(s)[/dim]")


@cli.command("convert")
@click.option(
    "--from", "from_service",
    required=True,
    type=click.Choice(_SERVICES),
    help="Source streaming service.",
)
@click.option(
    "--to", "to_service",
    required=True,
    type=click.Choice(_SERVICES),
    help="Destination streaming service.",
)
@click.option("--playlist-id", "-p", required=True, help="Playlist ID on the source service.")
@click.option("--name", "-n", default=None, help="Name for the new playlist. Defaults to the original name.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be added without creating anything.")
@click.option(
    "--output", "-o",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Output format.",
)
def convert(
    from_service: str,
    to_service: str,
    playlist_id: str,
    name: str | None,
    dry_run: bool,
    output: str,
) -> None:
    """Convert a playlist from one service to another."""
    if from_service == to_service:
        _abort("Source and destination services must be different.")

    source = _get_authenticated_provider(from_service)
    dest = _get_authenticated_provider(to_service)

    # Fetch source playlist tracks
    try:
        playlists = source.get_user_playlists()
        source_playlist = next((p for p in playlists if p.provider_id == playlist_id), None)
        playlist_name = source_playlist.name if source_playlist else playlist_id

        console.print(f"Fetching tracks from [bold]{source.service_name}[/bold]...")
        tracks = source.get_playlist_tracks(playlist_id)
    except PlaylistConvertError as e:
        _abort(str(e))
        return

    console.print(f"Found [bold]{len(tracks)}[/bold] track(s). Matching on {dest.service_name}...")

    settings = get_settings()
    results: list[MatchResult] = []

    with console.status("Matching tracks..."):
        for track in tracks:
            candidates = _search_with_isrc(dest, track)
            result = match_track(track, candidates, threshold=settings.fuzzy_match_threshold)
            results.append(result)

    matched = [r for r in results if r.matched_track is not None]
    failed = [r for r in results if r.matched_track is None]

    if output == "json":
        _output_convert_json(results, dry_run)
        return

    _print_convert_table(results)

    console.print(f"\n[green]Matched:[/green] {len(matched)}/{len(tracks)}")
    if failed:
        console.print(f"[yellow]Unmatched:[/yellow] {len(failed)} track(s)")
        for r in failed:
            console.print(f"  [dim]- {r.source_track.artist} — {r.source_track.title}[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run — no playlist was created.[/yellow]")
        return

    if not matched:
        _abort("No tracks could be matched. Playlist not created.")
        return

    new_name = name or playlist_name
    console.print(f"\nCreating playlist [bold]{new_name!r}[/bold] on {dest.service_name}...")

    try:
        new_playlist_id = dest.create_playlist(
            name=new_name,
            description=f"Converted from {source.service_name}",
        )
        dest.add_tracks(new_playlist_id, [r.matched_track for r in matched])  # type: ignore[misc]
    except (PlaylistConvertError, NotImplementedError) as e:
        _abort(str(e))
        return

    console.print(f"[green]Done![/green] Playlist created with {len(matched)} track(s).")
    console.print(f"Playlist ID: [bold]{new_playlist_id}[/bold]")


@cli.command("create")
@click.option(
    "--service", "-s",
    required=True,
    type=click.Choice(_SERVICES),
    help="Streaming service to create the playlist on.",
)
@click.option(
    "--file", "-f", "yaml_file",
    required=True,
    type=click.Path(exists=True),
    help="Path to YAML file defining the playlist.",
)
@click.option("--name", "-n", default=None, help="Playlist name. Overrides the name field in the YAML file.")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be added without creating anything.")
@click.option(
    "--output", "-o",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Output format.",
)
def create(service: str, yaml_file: str, name: str | None, dry_run: bool, output: str) -> None:
    """Create a playlist on a service from a YAML file."""
    try:
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        _abort(f"Failed to parse YAML file: {e}")
        return

    if not isinstance(data, dict):
        _abort("YAML file must be a mapping with 'name' and 'tracks' keys.")
        return

    playlist_name = name or data.get("name")
    if not playlist_name:
        _abort("Playlist name is required (set 'name' in YAML or use --name).")
        return

    description = data.get("description", "")
    raw_tracks = data.get("tracks")
    if not raw_tracks or not isinstance(raw_tracks, list):
        _abort("YAML file must contain a 'tracks' list with at least one entry.")
        return

    tracks: list[Track] = []
    for i, entry in enumerate(raw_tracks, 1):
        if not isinstance(entry, dict) or not entry.get("title") or not entry.get("artist"):
            _abort(f"Track {i} is missing required 'title' or 'artist' field.")
            return
        tracks.append(Track(title=entry["title"], artist=entry["artist"], album=entry.get("album", "")))

    dest = _get_authenticated_provider(service)
    settings = get_settings()

    console.print(f"Loaded [bold]{len(tracks)}[/bold] track(s). Matching on {dest.service_name}...")

    results: list[MatchResult] = []
    with console.status("Matching tracks..."):
        for track in tracks:
            candidates = _search_with_isrc(dest, track)
            result = match_track(track, candidates, threshold=settings.fuzzy_match_threshold)
            results.append(result)

    matched = [r for r in results if r.matched_track is not None]
    failed = [r for r in results if r.matched_track is None]

    if output == "json":
        _output_convert_json(results, dry_run)
        return

    _print_convert_table(results)
    console.print(f"\n[green]Matched:[/green] {len(matched)}/{len(tracks)}")
    if failed:
        console.print(f"[yellow]Unmatched:[/yellow] {len(failed)} track(s)")
        for r in failed:
            console.print(f"  [dim]- {r.source_track.artist} — {r.source_track.title}[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run — no playlist was created.[/yellow]")
        return

    if not matched:
        _abort("No tracks could be matched. Playlist not created.")
        return

    console.print(f"\nCreating playlist [bold]{playlist_name!r}[/bold] on {dest.service_name}...")
    try:
        new_playlist_id = dest.create_playlist(name=playlist_name, description=description)
        dest.add_tracks(new_playlist_id, [r.matched_track for r in matched])  # type: ignore[misc]
    except (PlaylistConvertError, NotImplementedError) as e:
        _abort(str(e))
        return

    console.print(f"[green]Done![/green] Playlist created with {len(matched)} track(s).")
    console.print(f"Playlist ID: [bold]{new_playlist_id}[/bold]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _search_with_isrc(dest, track: Track) -> list[Track]:
    """Search on dest, preferring ISRC lookup when available."""
    if track.isrc and isinstance(dest, SpotifyProvider):
        isrc_results = dest.search_track_by_isrc(track.isrc)
        if isrc_results:
            return isrc_results
    try:
        return dest.search_track(track.title, track.artist)
    except (PlaylistConvertError, NotImplementedError):
        return []


def _format_duration(ms: int) -> str:
    if ms <= 0:
        return ""
    total_seconds = ms // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _print_convert_table(results: list[MatchResult]) -> None:
    table = Table(title="Track Matching Results", show_lines=False)
    table.add_column("Source Title", style="bold")
    table.add_column("Source Artist")
    table.add_column("Matched Title")
    table.add_column("Matched Artist")
    table.add_column("Method", width=6)
    table.add_column("Conf.", justify="right", width=6)

    for r in results:
        if r.matched_track:
            method_style = "green" if r.method == "isrc" else "cyan"
            table.add_row(
                r.source_track.title,
                r.source_track.artist,
                r.matched_track.title,
                r.matched_track.artist,
                f"[{method_style}]{r.method}[/{method_style}]",
                f"{r.confidence:.0%}",
            )
        else:
            table.add_row(
                r.source_track.title,
                r.source_track.artist,
                "[red]—[/red]",
                "[red]—[/red]",
                "[red]none[/red]",
                "[red]—[/red]",
            )

    console.print(table)


def _output_convert_json(results: list[MatchResult], dry_run: bool) -> None:
    data = {
        "dry_run": dry_run,
        "results": [
            {
                "source": {
                    "title": r.source_track.title,
                    "artist": r.source_track.artist,
                    "isrc": r.source_track.isrc,
                },
                "matched": {
                    "title": r.matched_track.title,
                    "artist": r.matched_track.artist,
                    "uri": r.matched_track.provider_uri,
                    "isrc": r.matched_track.isrc,
                }
                if r.matched_track
                else None,
                "confidence": r.confidence,
                "method": r.method,
            }
            for r in results
        ],
        "summary": {
            "total": len(results),
            "matched": sum(1 for r in results if r.matched_track),
            "unmatched": sum(1 for r in results if not r.matched_track),
        },
    }
    click.echo(json.dumps(data, indent=2))
