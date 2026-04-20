from dataclasses import dataclass, field


@dataclass
class Track:
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    isrc: str = ""          # ISO Recording Code — used for exact matching across services
    provider_id: str = ""
    provider_uri: str = ""  # e.g. "spotify:track:4uLU6hMCjMI75M1A2tKUQC"


@dataclass
class Playlist:
    name: str
    description: str = ""
    provider_id: str = ""
    tracks: list[Track] = field(default_factory=list)
