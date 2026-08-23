#!/usr/bin/env python3
"""CLI for nugs.net reverse-engineered API."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import api


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format a simple aligned text table."""
    if not rows:
        return "No results found."
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    lines = []
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(str(val).ljust(widths[i]) for i, val in enumerate(row)))
    return "\n".join(lines)


def cmd_artists(args: argparse.Namespace) -> int:
    artists = api.get_artists(query=args.query)
    if args.json:
        print(json.dumps(artists, indent=2))
        return 0

    if not artists:
        print(f"No artists found matching {args.query!r}")
        return 0

    limit = args.limit if args.limit and args.limit > 0 else (20 if not args.query else len(artists))
    rows = [[str(a["id"]), a["name"], str(a["num_shows"]), str(a["num_albums"])] for a in artists[:limit]]
    print(format_table(["Artist ID", "Artist Name", "Shows", "Albums"], rows))
    if len(artists) > limit:
        print(f"\n... and {len(artists) - limit} more (use --limit 0 to show all)")
    return 0


def cmd_shows(args: argparse.Namespace) -> int:
    try:
        data = api.get_shows_by_artist(args.artist, limit=args.limit, offset=args.offset)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    artist = data["artist"]
    print(f"Shows for: {artist['name']} (ID: {artist['id']}) — Total: {data['total']}\n")
    rows = []
    for item in data["items"]:
        date = item.get("performance_date") or ""
        venue = item.get("venue") or item.get("location") or ""
        rows.append([str(item["id"]), date, venue, item.get("title", "")])

    print(format_table(["Show ID", "Date", "Venue", "Title"], rows))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        data = api.get_show(args.target)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print(f"{data['artist_name']} — {data['title']}")
    print(f"Date: {data['performance_date']} | Duration: {data['duration']} | Show ID: {data['show_id']}")
    if data.get("venue_name"):
        location = ", ".join(filter(None, [data.get("venue_city"), data.get("venue_state")]))
        print(f"Venue: {data['venue_name']}" + (f" ({location})" if location else ""))
    print(f"\nSetlist ({data['track_count']} tracks):")

    rows = []
    for t in data["tracks"]:
        set_str = f"Set {t['set_num']}" if t['set_num'] < 4 else "Encore"
        rows.append([str(t["track_id"]), set_str, str(t["track_num"]), t["title"] or ""])
    print(format_table(["Track ID", "Set", "#", "Song Title"], rows))

    if data.get("products"):
        formats = [p["format"] for p in data["products"] if p.get("format")]
        print(f"\nAvailable formats: {', '.join(formats)}")
    return 0


def cmd_featured(args: argparse.Namespace) -> int:
    data = api.get_featured_releases(limit=args.limit, offset=args.offset)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    rows = []
    for item in data.get("items", []):
        rows.append([str(item.get("id")), item.get("artistName", ""), (item.get("performanceDate") or "")[:10], item.get("title", "")])
    print(format_table(["Show ID", "Artist", "Date", "Title"], rows))
    return 0


def cmd_popular(args: argparse.Namespace) -> int:
    data = api.get_popular_releases(limit=args.limit, offset=args.offset)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    rows = []
    for item in data.get("items", []):
        rows.append([str(item.get("id")), item.get("artistName", ""), (item.get("performanceDate") or "")[:10], item.get("title", "")])
    print(format_table(["Show ID", "Artist", "Date", "Title"], rows))
    return 0


def cmd_livestreams(args: argparse.Namespace) -> int:
    data = api.get_livestreams(limit=args.limit, offset=args.offset)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    rows = []
    for item in data.get("items", []):
        artist = item.get("artist", {}).get("name", "") if isinstance(item.get("artist"), dict) else ""
        date = item.get("startDate", "")
        title = item.get("title") or item.get("headline") or ""
        rows.append([str(item.get("skuId", "")), artist, date[:16] if date else "", title])
    print(format_table(["SKU ID", "Artist", "Start Date", "Title"], rows))
    return 0


def cmd_clip_url(args: argparse.Namespace) -> int:
    try:
        data = api.get_show(args.target)
    except Exception as e:
        print(f"Error fetching show: {e}", file=sys.stderr)
        return 1

    tracks = data.get("tracks", [])
    if not tracks:
        print("No tracks found in show", file=sys.stderr)
        return 1

    selected_track = None
    if args.track:
        t_arg = args.track.strip()
        if t_arg.isdigit():
            t_num = int(t_arg)
            selected_track = next((t for t in tracks if t.get("track_id") == t_num), None)
            if not selected_track:
                selected_track = next((t for t in tracks if t.get("track_num") == t_num), None)
        else:
            selected_track = next((t for t in tracks if t_arg.lower() in (t.get("title") or "").lower()), None)
    else:
        selected_track = tracks[0]

    if not selected_track or not selected_track.get("clip_url"):
        print(f"No clip URL available for track {args.track or 1}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(selected_track, indent=2))
    else:
        print(selected_track["clip_url"])
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    has_json_flag = "--json" in raw_argv

    parser = argparse.ArgumentParser(
        prog="nugs",
        description="nugs.net reverse-engineered CLI for catalog, shows, setlists, and livestreams.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # artists
    p_artists = subparsers.add_parser("artists", help="Search or list artists")
    p_artists.add_argument("query", nargs="?", help="Artist name search query")
    p_artists.add_argument("--limit", type=int, default=20, help="Maximum artists to return (default: 20)")
    p_artists.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_artists.set_defaults(func=cmd_artists)

    # shows
    p_shows = subparsers.add_parser("shows", help="List shows for an artist")
    p_shows.add_argument("artist", help="Artist name or ID")
    p_shows.add_argument("--limit", type=int, default=20, help="Limit (default: 20)")
    p_shows.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")
    p_shows.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_shows.set_defaults(func=cmd_shows)

    # show
    p_show = subparsers.add_parser("show", help="Get show setlist, venue, and track details")
    p_show.add_argument("target", help="Show ID or URL")
    p_show.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_show.set_defaults(func=cmd_show)

    # featured
    p_featured = subparsers.add_parser("featured", help="Get featured releases")
    p_featured.add_argument("--limit", type=int, default=20, help="Limit (default: 20)")
    p_featured.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")
    p_featured.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_featured.set_defaults(func=cmd_featured)

    # popular
    p_popular = subparsers.add_parser("popular", help="Get popular releases")
    p_popular.add_argument("--limit", type=int, default=20, help="Limit (default: 20)")
    p_popular.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")
    p_popular.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_popular.set_defaults(func=cmd_popular)

    # livestreams
    p_livestreams = subparsers.add_parser("livestreams", help="Get active and upcoming livestreams")
    p_livestreams.add_argument("--limit", type=int, default=20, help="Limit (default: 20)")
    p_livestreams.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")
    p_livestreams.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_livestreams.set_defaults(func=cmd_livestreams)

    # clip-url
    p_clip = subparsers.add_parser("clip-url", help="Get preview clip URL for a track")
    p_clip.add_argument("target", help="Show ID or URL")
    p_clip.add_argument("track", nargs="?", help="Track number, ID, or title")
    p_clip.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_clip.set_defaults(func=cmd_clip_url)

    args = parser.parse_args(argv)
    if has_json_flag:
        args.json = True

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
