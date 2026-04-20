from playlist_convert.config import Settings
from playlist_convert.providers.apple_music import AppleMusicProvider
from playlist_convert.providers.base import BaseProvider
from playlist_convert.providers.spotify import SpotifyProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "spotify": SpotifyProvider,
    "apple-music": AppleMusicProvider,
}


def get_provider(name: str, settings: Settings) -> BaseProvider:
    """
    Instantiate a provider by service name.

    To add a new service: create providers/<name>.py implementing BaseProvider,
    then add an entry to PROVIDER_REGISTRY above.
    """
    key = name.lower().replace("_", "-")
    if key not in PROVIDER_REGISTRY:
        known = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown service '{name}'. Known services: {known}")
    return PROVIDER_REGISTRY[key](settings)
