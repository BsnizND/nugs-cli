#!/usr/bin/env python3
"""CLI for the unofficial nugs.net catalog client."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from typing import Any

from . import api, player

MAX_CLIP_BYTES = 25 * 1024 * 1024


class CLIError(RuntimeError):
    """Expected command-line failure that should not produce a traceback."""


def _emit_json(value: Any) -> None:
    """Emit exactly one compact JSON document for machine consumers."""

    print(json.dumps(value, separators=(",", ":")))


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


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
    selected = artists if args.limit == 0 else artists[:args.limit]
    if args.json:
        _emit_json(selected)
        return 0

    if not artists:
        print(f"No artists found matching {args.query!r}")
        return 0

    rows = [[str(a["id"]), a["name"], str(a["num_shows"]), str(a["num_albums"])] for a in selected]
    print(format_table(["Artist ID", "Artist Name", "Shows", "Albums"], rows))
    if len(artists) > len(selected):
        print(f"\n... and {len(artists) - len(selected)} more (use --limit 0 to show all)")
    return 0


def cmd_shows(args: argparse.Namespace) -> int:
    data = api.get_shows_by_artist(args.artist, limit=args.limit, offset=args.offset)

    if args.json:
        _emit_json(data)
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
    data = api.get_show(args.target)

    if args.json:
        _emit_json(data)
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


def cmd_search(args: argparse.Namespace) -> int:
    data = api.search_catalog(
        args.query,
        artist=args.artist,
        year=args.year,
        venue=args.venue,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
        offset=args.offset,
    )
    if args.json:
        _emit_json(data)
        return 0

    if data["artists"]:
        print("Artists")
        print(format_table(
            ["Artist ID", "Artist Name", "Shows"],
            [[str(item["id"]), item["name"], str(item.get("num_shows", ""))] for item in data["artists"]],
        ))
    if data["shows"]:
        if data["artists"]:
            print()
        print("Shows")
        rows = []
        for show in data["shows"]:
            matches = ", ".join(track.get("title") or "" for track in show.get("matched_tracks", []))
            venue = ", ".join(filter(None, [show.get("venue_name"), show.get("venue_city"), show.get("venue_state")]))
            rows.append([
                str(show.get("show_id", "")),
                show.get("artist_name") or "",
                show.get("performance_date") or "",
                venue,
                matches,
            ])
        print(format_table(["Show ID", "Artist", "Date", "Venue", "Matching tracks"], rows))
    if not data["artists"] and not data["shows"]:
        print("No results found.")
    return 0


def cmd_featured(args: argparse.Namespace) -> int:
    data = api.get_featured_releases(limit=args.limit, offset=args.offset)
    if args.json:
        _emit_json(data)
        return 0

    rows = []
    for item in data.get("items", []):
        rows.append([
            str(item.get("id", "")),
            item.get("artist_name") or "",
            (item.get("performance_date") or "")[:10],
            item.get("title") or "",
        ])
    print(format_table(["Show ID", "Artist", "Date", "Title"], rows))
    return 0


def cmd_popular(args: argparse.Namespace) -> int:
    data = api.get_popular_releases(limit=args.limit, offset=args.offset)
    if args.json:
        _emit_json(data)
        return 0

    rows = []
    for item in data.get("items", []):
        rows.append([
            str(item.get("id", "")),
            item.get("artist_name") or "",
            (item.get("performance_date") or "")[:10],
            item.get("title") or "",
        ])
    print(format_table(["Show ID", "Artist", "Date", "Title"], rows))
    return 0


def cmd_livestreams(args: argparse.Namespace) -> int:
    data = api.get_livestreams(limit=args.limit, offset=args.offset)
    if args.json:
        _emit_json(data)
        return 0

    rows = []
    for item in data.get("items", []):
        date = item.get("start_date") or ""
        rows.append([
            str(item.get("sku_id", "")),
            item.get("artist_name") or "",
            date[:16],
            item.get("title") or "",
        ])
    print(format_table(["SKU ID", "Artist", "Start Date", "Title"], rows))
    return 0


def _resolve_track_from_show(show_data: dict[str, Any], track_arg: str | None) -> dict[str, Any] | None:
    tracks = show_data.get("tracks", [])
    if not tracks:
        return None
    if not track_arg:
        return tracks[0]
    t_arg = track_arg.strip()
    if t_arg.isdigit():
        t_num = int(t_arg)
        matched = next((t for t in tracks if t.get("track_id") == t_num), None)
        if not matched:
            matched = next((t for t in tracks if t.get("track_num") == t_num), None)
        return matched

    normalized = t_arg.casefold()
    exact = [t for t in tracks if (t.get("title") or "").strip().casefold() == normalized]
    if exact:
        return exact[0]

    partial = [t for t in tracks if normalized in (t.get("title") or "").strip().casefold()]
    if len(partial) > 1:
        choices = ", ".join(f"{t.get('track_num')}: {(t.get('title') or '').strip()}" for t in partial)
        raise CLIError(f"Track title {track_arg!r} is ambiguous; choose a track number or one of: {choices}")
    return partial[0] if partial else None


def cmd_clip_url(args: argparse.Namespace) -> int:
    data = api.get_show(args.target)

    selected_track = _resolve_track_from_show(data, args.track)
    if not selected_track or not selected_track.get("clip_url"):
        raise CLIError(f"No clip URL available for track {args.track or 1}")

    if args.json:
        _emit_json(selected_track)
    else:
        print(selected_track["clip_url"])
    return 0


def cmd_play_clip(args: argparse.Namespace) -> int:
    data = api.get_show(args.target)

    selected_track = _resolve_track_from_show(data, args.track)
    if not selected_track or not selected_track.get("clip_url"):
        raise CLIError(f"No preview clip found for track {args.track or 1}")

    clip_url = selected_track["clip_url"]
    parsed_url = urllib.parse.urlparse(clip_url)
    if parsed_url.scheme != "https":
        raise CLIError(f"Refusing non-HTTPS clip URL: {clip_url}")

    if shutil.which("afplay"):
        player = "afplay"
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            temp_path = tf.name
        try:
            request = urllib.request.Request(clip_url, headers={"User-Agent": api.USER_AGENT})
            with urllib.request.urlopen(request, timeout=15) as response, open(temp_path, "wb") as output:
                content = response.read(MAX_CLIP_BYTES + 1)
                if len(content) > MAX_CLIP_BYTES:
                    raise CLIError("Preview clip exceeds the 25 MB safety limit")
                output.write(content)
            cmd = [player, "-t", str(args.seconds)]
            cmd.append(temp_path)
            subprocess.run(cmd, check=True, timeout=args.seconds + 15)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
    elif shutil.which("ffplay"):
        player = "ffplay"
        cmd = [player, "-nodisp", "-autoexit", "-t", str(args.seconds)]
        cmd.append(clip_url)
        subprocess.run(cmd, check=True, timeout=args.seconds + 15)
    elif shutil.which("mpv"):
        player = "mpv"
        cmd = [player, "--no-video", f"--length={args.seconds}"]
        cmd.append(clip_url)
        subprocess.run(cmd, check=True, timeout=args.seconds + 15)
    else:
        raise CLIError("No local audio player found (supported: afplay, ffplay, mpv)")

    result = {
        "status": "played",
        "player": player,
        "seconds": args.seconds,
        "show_id": data.get("show_id"),
        "artist_name": data.get("artist_name"),
        "show_title": data.get("title"),
        "track": selected_track,
    }
    if args.json:
        _emit_json(result)
    else:
        print(f"Played preview: {data['artist_name']} — {selected_track['title']} ({data['title']})")
        print(f"Player: {player} | Duration: {args.seconds}s")
        print(f"Clip URL: {clip_url}")
    return 0


def cmd_player(args: argparse.Namespace) -> int:
    track_title = getattr(args, "track_title", None)
    track_id = None
    if args.command == "play" and getattr(args, "track", None):
        show = api.get_show(args.target)
        selected_track = _resolve_track_from_show(show, args.track)
        if selected_track is None:
            raise CLIError(f"No track found matching {args.track!r} in release {show['show_id']}")
        track_title = selected_track.get("title")
        track_id = selected_track.get("track_id")
        if not track_title:
            raise CLIError(f"Track {args.track!r} has no playable title")
    result = asyncio.run(
        player.run_command(
            args.command,
            endpoint=args.cdp_endpoint,
            target=getattr(args, "target", None),
            source_url=getattr(args, "url", None),
            track_title=track_title,
            track_id=track_id,
            from_track_title=getattr(args, "from_track_title", None),
            to_track_title=getattr(args, "to_track_title", None),
        )
    )
    if args.json:
        _emit_json(result)
    elif result.get("player_present"):
        track = f" — {result['track_title']}" if result.get("track_title") else ""
        print(f"{result['state']}: nugs release {result['release_id']}{track}")
    else:
        print(result["state"])
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    result = asyncio.run(player.diagnose(endpoint=args.cdp_endpoint, target=args.target))
    if args.json:
        _emit_json(result)
    else:
        print(f"nugs-cli {result['version']} on Python {result['python']}")
        for check in result["checks"]:
            mark = "OK" if check["ok"] else "FAIL"
            print(f"{mark:4}  {check['name']}: {check['detail']}")
    return 0 if result["ok"] else 1


def _add_player_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cdp-endpoint",
        default=player.DEFAULT_CDP_ENDPOINT,
        help=f"Logged-in Chrome DevTools endpoint (default: {player.DEFAULT_CDP_ENDPOINT})",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    has_json_flag = "--json" in raw_argv

    parser = argparse.ArgumentParser(
        prog="nugs",
        description="Unofficial nugs.net CLI for catalog discovery and logged-in web-player control.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # artists
    p_artists = subparsers.add_parser("artists", help="Search or list artists")
    p_artists.add_argument("query", nargs="?", help="Artist name search query")
    p_artists.add_argument("--limit", type=_nonnegative_int, default=20, help="Maximum artists to return; 0 shows all (default: 20)")
    p_artists.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_artists.set_defaults(func=cmd_artists)

    # shows
    p_shows = subparsers.add_parser("shows", help="List shows for an artist")
    p_shows.add_argument("artist", help="Artist name or ID")
    p_shows.add_argument("--limit", type=_positive_int, default=20, help="Limit (default: 20)")
    p_shows.add_argument("--offset", type=_nonnegative_int, default=0, help="Offset (default: 0)")
    p_shows.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_shows.set_defaults(func=cmd_shows)

    # show
    p_show = subparsers.add_parser("show", help="Get show setlist, venue, and track details")
    p_show.add_argument("target", help="Show ID or URL")
    p_show.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_show.set_defaults(func=cmd_show)

    # search
    p_search = subparsers.add_parser("search", help="Search artists and shows containing a song")
    p_search.add_argument("query", nargs="?", help="Artist name or song-title query")
    p_search.add_argument("--artist", help="Filter to one artist name or ID")
    p_search.add_argument("--year", type=int, help="Filter by performance year")
    p_search.add_argument("--venue", help="Filter returned shows by venue or location text")
    p_search.add_argument("--date-from", help="Filter returned shows from YYYY-MM-DD")
    p_search.add_argument("--date-to", help="Filter returned shows through YYYY-MM-DD")
    p_search.add_argument("--limit", type=_positive_int, default=20, help="Maximum shows to return (default: 20)")
    p_search.add_argument("--offset", type=_nonnegative_int, default=0, help="Result offset (default: 0)")
    p_search.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_search.set_defaults(func=cmd_search)

    # featured
    p_featured = subparsers.add_parser("featured", help="Get featured releases")
    p_featured.add_argument("--limit", type=_positive_int, default=20, help="Limit (default: 20)")
    p_featured.add_argument("--offset", type=_nonnegative_int, default=0, help="Offset (default: 0)")
    p_featured.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_featured.set_defaults(func=cmd_featured)

    # popular
    p_popular = subparsers.add_parser("popular", help="Get popular releases")
    p_popular.add_argument("--limit", type=_positive_int, default=20, help="Limit (default: 20)")
    p_popular.add_argument("--offset", type=_nonnegative_int, default=0, help="Offset (default: 0)")
    p_popular.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_popular.set_defaults(func=cmd_popular)

    # livestreams
    p_livestreams = subparsers.add_parser("livestreams", help="Get active and upcoming livestreams")
    p_livestreams.add_argument("--limit", type=_positive_int, default=20, help="Limit (default: 20)")
    p_livestreams.add_argument("--offset", type=_nonnegative_int, default=0, help="Offset (default: 0)")
    p_livestreams.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_livestreams.set_defaults(func=cmd_livestreams)

    # clip-url
    p_clip = subparsers.add_parser("clip-url", help="Get preview clip URL for a track")
    p_clip.add_argument("target", help="Show ID or URL")
    p_clip.add_argument("track", nargs="?", help="Track number, ID, or title")
    p_clip.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_clip.set_defaults(func=cmd_clip_url)

    # play-clip
    p_play = subparsers.add_parser("play-clip", help="Play audio preview clip for a track")
    p_play.add_argument("target", help="Show ID or URL")
    p_play.add_argument("track", nargs="?", help="Track number, ID, or title")
    p_play.add_argument("--seconds", type=_positive_int, default=10, help="Playback duration in seconds (default: 10)")
    p_play.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p_play.set_defaults(func=cmd_play_clip)

    # authenticated first-party web player
    p_release_play = subparsers.add_parser("play", help="Play a release in a logged-in nugs web player")
    p_release_play.add_argument("target", help="Show ID or URL")
    p_release_play.add_argument("--track", help="Exact track number, ID, or title")
    _add_player_options(p_release_play)
    p_release_play.set_defaults(func=cmd_player)

    p_track_play = subparsers.add_parser("play-track", help="Play an exact track of a release")
    p_track_play.add_argument("--target", required=True, help="Show ID or URL")
    p_track_play.add_argument("--track-title", required=True, help="Exact rendered track title")
    p_track_play.add_argument("--url", help="Accepted for LifeOS compatibility; playback uses the exact release target")
    _add_player_options(p_track_play)
    p_track_play.set_defaults(func=cmd_player)

    p_doctor = subparsers.add_parser("doctor", help="Check logged-in web-player readiness without playback")
    p_doctor.add_argument("--target", help="Optional release ID or URL for a deeper rendered-control check")
    _add_player_options(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    for command in ("status", "pause", "resume", "stop"):
        command_parser = subparsers.add_parser(command, help=f"{command.title()} the logged-in nugs web player")
        if command == "resume":
            command_parser.add_argument("--target", help="Optional expected release target")
        _add_player_options(command_parser)
        command_parser.set_defaults(func=cmd_player)

    for command in ("next", "previous"):
        command_parser = subparsers.add_parser(command, help=f"Select the {command} track")
        command_parser.add_argument("--target", help="Optional expected release target")
        command_parser.add_argument("--from-track-title", required=True, help="Exact current track title")
        command_parser.add_argument("--to-track-title", required=True, help="Exact expected track title")
        _add_player_options(command_parser)
        command_parser.set_defaults(func=cmd_player)

    args = parser.parse_args(argv)
    if has_json_flag:
        args.json = True

    if not args.command:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except (api.NugsAPIError, player.PlayerError, CLIError, ValueError, OSError, subprocess.SubprocessError) as error:
        if getattr(args, "json", False):
            _emit_json({"error": str(error)})
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
