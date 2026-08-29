"""nugs-cli: unofficial nugs.net catalog and logged-in web-player client."""

from .api import (
    NugsAPIError,
    extract_show_id,
    get_artists,
    get_featured_releases,
    get_livestreams,
    get_popular_releases,
    search_catalog,
    get_show,
    get_shows_by_artist,
    resolve_artist,
)

__version__ = "1.2.0"
__all__ = [
    "NugsAPIError",
    "extract_show_id",
    "get_artists",
    "get_featured_releases",
    "get_livestreams",
    "get_popular_releases",
    "search_catalog",
    "get_show",
    "get_shows_by_artist",
    "resolve_artist",
]
