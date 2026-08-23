"""nugs-cli: Reverse-engineered CLI and SDK for nugs.net catalog, shows, setlists, and livestreams."""

from .api import (
    NugsAPIError,
    extract_show_id,
    get_artists,
    get_featured_releases,
    get_livestreams,
    get_popular_releases,
    get_show,
    get_shows_by_artist,
    resolve_artist,
)

__version__ = "1.0.0"
__all__ = [
    "NugsAPIError",
    "extract_show_id",
    "get_artists",
    "get_featured_releases",
    "get_livestreams",
    "get_popular_releases",
    "get_show",
    "get_shows_by_artist",
    "resolve_artist",
]
