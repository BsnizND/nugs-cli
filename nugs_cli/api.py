#!/usr/bin/env python3
"""Unofficial API client for nugs.net catalog, artists, shows, and livestreams."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

CATALOG_API_BASE = "https://catalog.nugs.net/api/v1"
STREAM_API_BASE = "https://streamapi.nugs.net/api.aspx"
USER_AGENT = "nugs-cli/1.0.0 (https://github.com/BsnizND/nugs-cli)"

SHOW_URL_RE = re.compile(r"(?:/release/|/shows/|/live-[^/]+/|/)(\d+)(?:\.html)?(?:$|[?#])")


class NugsAPIError(RuntimeError):
    """Exception raised when a nugs API call fails."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _validate_pagination(limit: int, offset: int) -> None:
    if limit < 0:
        raise ValueError("limit must be 0 or greater")
    if offset < 0:
        raise ValueError("offset must be 0 or greater")


def _as_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _image_url(item: dict[str, Any]) -> str | None:
    image = item.get("image") or item.get("coverImage")
    if isinstance(image, dict):
        image = image.get("url")
    if isinstance(image, str) and image.startswith("/"):
        return f"https://catalog.nugs.net{image}"
    return image if isinstance(image, str) else None


def _venue_text(venue: Any) -> str | None:
    if isinstance(venue, str):
        return venue
    if not isinstance(venue, dict):
        return None
    name = venue.get("name") or venue.get("title")
    location = ", ".join(filter(None, [venue.get("city"), venue.get("state")]))
    return f"{name} ({location})" if name and location else (name or location or None)


def _normalize_release(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize the different featured/popular release payloads."""
    artist = item.get("artist") if isinstance(item.get("artist"), dict) else {}
    show_details = item.get("showDetails") if isinstance(item.get("showDetails"), dict) else {}
    venue = item.get("venue") or show_details.get("venue")
    album_details = item.get("albumDetails") if isinstance(item.get("albumDetails"), dict) else {}
    title = (
        item.get("title")
        or item.get("headline")
        or album_details.get("title")
        or (venue.get("title") if isinstance(venue, dict) else venue)
    )
    return {
        "id": _as_int(item.get("id")),
        "title": title,
        "artist_id": _as_int(artist.get("id")) if artist else None,
        "artist_name": artist.get("name") or item.get("artistName"),
        "performance_date": item.get("performanceDate") or show_details.get("performanceDate"),
        "venue": _venue_text(venue),
        "status": item.get("status") or item.get("availabilityType"),
        "type": item.get("type") or item.get("releaseType"),
        "has_video": item.get("hasVideoOnDemand", item.get("hasVideoContent", False)),
        "audio_formats": item.get("audioFormatTypes", []),
        "video_formats": item.get("videoFormatTypes", []),
        "image_url": _image_url(item),
    }


def _parse_api_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _http_get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    if params:
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{query_string}" if "?" not in url else f"{url}&{query_string}"

    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            if not content:
                return {}
            try:
                return json.loads(content)
            except json.JSONDecodeError as error:
                raise NugsAPIError(f"Invalid JSON response from {url}", response_body=content[:500]) from error
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else None
        raise NugsAPIError(f"HTTP {e.code} for {url}: {e.reason}", status_code=e.code, response_body=body) from e
    except NugsAPIError:
        raise
    except Exception as e:
        raise NugsAPIError(f"Network error requesting {url}: {e}") from e


def extract_show_id(target: str | int) -> int:
    """Extract numeric show ID from integer, digit string, or nugs URL."""
    if isinstance(target, int):
        return target
    target_str = str(target).strip()
    if target_str.isdigit():
        return int(target_str)
    match = SHOW_URL_RE.search(target_str)
    if match:
        return int(match.group(1))
    match2 = re.search(r"/(\d+)(?:\.html)?(?:$|[?#])", target_str)
    if match2:
        return int(match2.group(1))
    raise ValueError(f"Could not extract a valid show ID from: {target!r}")


def get_artists(query: str | None = None) -> list[dict[str, Any]]:
    """Fetch all 640+ artists from nugs directory, optionally filtering by query."""
    data = _http_get(STREAM_API_BASE, params={"method": "catalog.artists", "availType": 1})
    artists_raw = data.get("Response", {}).get("artists", [])
    artists = []
    for a in artists_raw:
        artist_id = a.get("artistID")
        name = a.get("artistName", "").strip()
        if not artist_id or not name:
            continue
        artists.append({
            "id": int(artist_id),
            "name": name,
            "name_normalized": a.get("artistNameNoThe", "").strip(),
            "num_shows": a.get("numShows", 0),
            "num_albums": a.get("numAlbums", 0),
            "image_url": a.get("artistImage"),
            "page_url": a.get("pageURL"),
        })

    if query:
        q = query.strip().lower()
        exact = [a for a in artists if a["name"].lower() == q or a["name_normalized"].lower() == q]
        prefix = [a for a in artists if a["name"].lower().startswith(q) and a not in exact]
        substr = [a for a in artists if q in a["name"].lower() and a not in exact and a not in prefix]
        return exact + prefix + substr

    return artists


def resolve_artist(artist_query_or_id: str | int) -> dict[str, Any]:
    """Resolve an artist query string or numeric ID to an artist record."""
    if isinstance(artist_query_or_id, int) or (isinstance(artist_query_or_id, str) and str(artist_query_or_id).isdigit()):
        target_id = int(artist_query_or_id)
        all_artists = get_artists()
        for a in all_artists:
            if a["id"] == target_id:
                return a
        return {"id": target_id, "name": f"Artist #{target_id}", "num_shows": 0, "num_albums": 0}

    results = get_artists(query=str(artist_query_or_id))
    if not results:
        raise NugsAPIError(f"No artist found matching {artist_query_or_id!r}")
    return results[0]


def get_shows_by_artist(artist_query_or_id: str | int, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Get paginated shows/releases for a given artist."""
    _validate_pagination(limit, offset)
    artist = resolve_artist(artist_query_or_id)
    artist_id = artist["id"]

    data = _http_get(f"{CATALOG_API_BASE}/releases", params={
        "artistIds": artist_id,
        "limit": limit,
        "offset": offset,
    })

    items = []
    for item in data.get("items", []):
        venue_str = _venue_text(item.get("venue")) or item.get("location")

        items.append({
            "id": int(item["id"]),
            "title": item.get("title"),
            "artist_name": item.get("artistName") or artist["name"],
            "artist_id": artist_id,
            "performance_date": (item.get("performanceDate") or "")[:10],
            "venue": venue_str,
            "location": item.get("location"),
            "status": item.get("status"),
            "has_video": item.get("hasVideoOnDemand", False),
            "formats": item.get("audioFormatTypes", []),
            "image_url": item.get("image", {}).get("url") if isinstance(item.get("image"), dict) else None,
        })

    items.sort(key=lambda item: item.get("performance_date") or "", reverse=True)

    return {
        "artist": artist,
        "items": items,
        "total": data.get("total", len(items)),
        "limit": limit,
        "offset": offset,
    }


def get_show(show_target: str | int) -> dict[str, Any]:
    """Fetch complete show details, venue, date, tracklist with song titles and clip URLs."""
    show_id = extract_show_id(show_target)
    data = _http_get(f"{CATALOG_API_BASE}/shows/{show_id}")
    resp = data.get("Response")
    if not resp:
        raise NugsAPIError(f"Show #{show_id} returned empty or invalid response", status_code=404)

    tracks = []
    for s in resp.get("songs", []):
        tracks.append({
            "track_id": s.get("trackID"),
            "song_id": s.get("songID"),
            "title": s.get("songTitle"),
            "set_num": s.get("setNum", 1),
            "track_num": s.get("trackNum", 1),
            "disc_num": s.get("discNum", 1),
            "clip_url": s.get("clipURL"),
            "duration_seconds": s.get("trackLength"),
        })

    products = []
    for p in resp.get("productFormatList", []):
        products.append({
            "sku_id": p.get("skuID"),
            "format": p.get("formatStr"),
            "sku_code": p.get("skuCode"),
            "cost_cents": p.get("cost"),
        })

    img = resp.get("img") or {}
    image_url = img.get("url")
    if image_url and not image_url.startswith("http"):
        image_url = f"https://assets-01.nugscdn.net{image_url}" if not image_url.startswith("/images") else f"https://catalog.nugs.net{image_url}"

    return {
        "show_id": int(resp.get("containerID", show_id)),
        "title": resp.get("containerInfo"),
        "artist_id": resp.get("artistID"),
        "artist_name": resp.get("artistName"),
        "venue_name": resp.get("venueName"),
        "venue_city": resp.get("venueCity"),
        "venue_state": resp.get("venueState"),
        "performance_date": resp.get("performanceDate"),
        "performance_date_formatted": resp.get("performanceDateFormatted"),
        "duration": resp.get("hhmmssTotalRunningTime"),
        "duration_seconds": resp.get("totalContainerRunningTime"),
        "image_url": image_url,
        "page_url": resp.get("pageURL"),
        "tracks": tracks,
        "track_count": len(tracks),
        "products": products,
        "is_in_subscription": resp.get("isInSubscriptionProgram", True),
    }


def get_featured_releases(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Fetch featured releases."""
    _validate_pagination(limit, offset)
    data = _http_get(f"{CATALOG_API_BASE}/releases/featured")
    all_items = [_normalize_release(item) for item in data.get("items", [])]
    items = all_items[offset:offset + limit] if limit else []
    return {
        "items": items,
        "total": len(all_items),
        "limit": limit,
        "offset": offset,
    }


def get_popular_releases(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Fetch popular releases."""
    _validate_pagination(limit, offset)
    data = _http_get(f"{CATALOG_API_BASE}/releases/popular", params={"limit": limit, "offset": offset})
    items = [_normalize_release(item) for item in data.get("items", [])]
    return {
        "items": items,
        "total": data.get("total", len(items)),
        "limit": limit,
        "offset": offset,
    }


def get_livestreams(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Fetch active and upcoming livestreams / webcasts."""
    _validate_pagination(limit, offset)
    raw_items = []
    page_offset = 0
    while True:
        data = _http_get(f"{CATALOG_API_BASE}/livestreams", params={"limit": 100, "offset": page_offset})
        page = data.get("items", [])
        raw_items.extend(page)
        total = data.get("total", len(raw_items))
        if not page or len(raw_items) >= total:
            break
        page_offset += len(page)

    now = datetime.now(timezone.utc)
    upcoming = []
    for item in raw_items:
        start = _parse_api_datetime(item.get("startDate"))
        end = _parse_api_datetime(item.get("endDate"))
        if (end and end < now) or (not end and start and start < now):
            continue
        release_raw = item.get("release") if isinstance(item.get("release"), dict) else {}
        release = _normalize_release(release_raw)
        upcoming.append({
            "sku_id": _as_int(item.get("skuId")),
            "event_type": item.get("eventType"),
            "content_type": item.get("contentType"),
            "start_date": item.get("startDate"),
            "end_date": item.get("endDate"),
            "show_id": release.get("id"),
            "artist_id": release.get("artist_id"),
            "artist_name": release.get("artist_name"),
            "title": release.get("title"),
            "venue": release.get("venue"),
            "image_url": release.get("image_url"),
        })
    upcoming.sort(key=lambda item: item.get("start_date") or "")
    items = upcoming[offset:offset + limit] if limit else []
    return {
        "items": items,
        "total": len(upcoming),
        "limit": limit,
        "offset": offset,
    }
