# nugs-cli

An unofficial CLI and Python client for exploring the public [nugs.net](https://www.nugs.net) live-music catalog and controlling the official web player in your own logged-in Chrome session.

Catalog and preview commands use Python's standard library only. Full playback is an optional Playwright extra that operates rendered first-party player controls; it does not resolve or download subscriber streams.

---

## Features

- **Artist Directory:** Search and resolve artist IDs and catalog counts (Dave Matthews Band, Phish, Dead & Company, Goose, Billy Strings, Pearl Jam, Bruce Springsteen, Metallica, etc.).
- **Unified Search:** Find artists and shows containing a song, then narrow by artist, year, venue, or date range.
- **Concert & Show Catalogs:** List recent and historical shows by artist with venue, date, city, state, and container ID.
- **Setlist & Track Inspection:** Show set breakdown, track numbers, track IDs, and available durations.
- **Preview Clips:** Resolve and play the public audio preview when nugs provides one for a track.
- **Webcasts & Livestreams:** Active, upcoming, and exclusive livestream schedule discovery.
- **Full Web-Player Control:** Play a release or any exact track, inspect status, pause, resume, skip, go back, and stop.
- **Readiness Doctor:** Check the local browser, logged-in session, and optional rendered release controls without starting playback.
- **Text or JSON:** Readable console tables for humans and structured `--json` output for automation.

---

## Endpoint Reference

The client uses undocumented JSON endpoints also used by nugs.net's public catalog experience. No account credentials are read or stored. Because these are not a supported public developer API, their response formats can change without notice.

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `https://streamapi.nugs.net/api.aspx?method=catalog.artists&availType=1` | `GET` | Complete directory of 640+ artists with IDs, show counts, and avatars |
| `https://streamapi.nugs.net/api.aspx?method=catalog.containersAll&songsPlayed={query}` | `GET` | Shows containing a matching song, with setlists and catalog identities |
| `https://catalog.nugs.net/api/v1/releases?artistIds={artistId}&limit=20` | `GET` | Paginated show list for any artist ID |
| `https://catalog.nugs.net/api/v1/shows/{showId}` | `GET` | Complete show details, venue, date, full setlist, track IDs, clip URLs, SKUs |
| `https://catalog.nugs.net/api/v1/releases/featured` | `GET` | Currently featured releases |
| `https://catalog.nugs.net/api/v1/releases/popular` | `GET` | Most popular releases |
| `https://catalog.nugs.net/api/v1/livestreams` | `GET` | Upcoming and active live webcasts |

---

## Installation

### With pip
```bash
pip install "nugs-cli[player] @ git+https://github.com/BsnizND/nugs-cli.git@v1.2.0"
```

### With pipx (Recommended for standalone CLI)
```bash
pipx install "nugs-cli[player] @ git+https://github.com/BsnizND/nugs-cli.git@v1.2.0"
```

### From Source
```bash
git clone https://github.com/BsnizND/nugs-cli.git
cd nugs-cli
pip install -e ".[player]"
```

---

## CLI Usage

### Search Artists
```bash
# Search for an artist by name
nugs artists "Dave Matthews Band"
nugs artists "Goose"
nugs artists "Billy Strings"

# List top 20 artists
nugs artists
```

Output:
```
Artist ID  Artist Name         Shows  Albums
---------  ------------------  -----  ------
803        Dave Matthews Band  128    0     
```

### List Shows by Artist
```bash
# By artist name or ID
nugs shows "Goose" --limit 5
nugs shows 803 --limit 5
```

Output:
```
Shows for: Goose (ID: 1205) — Total: 493

Show ID  Date        Venue                                 Title
-------  ----------  ------------------------------------  --------------------------------------------
46891    2026-08-22  Hayden Homes Amphitheater (Bend, OR)  8-22-2026 Hayden Homes Amphitheater Bend, OR
46890    2026-08-21  Hayden Homes Amphitheater (Bend, OR)  8-21-2026 Hayden Homes Amphitheater Bend, OR
46889    2026-08-19  WaMu Theater (Seattle, WA)            8-19-2026 WaMu Theater Seattle, WA
```

### Search Artists and Setlists

```bash
# Find exact song performances, optionally narrowed to one artist and year
nugs search "Two Step" --artist "Dave Matthews Band" --year 2026

# Filter that result set by venue and date range
nugs search "Two Step" --artist 803 --venue "Saratoga" \
  --date-from 2026-01-01 --date-to 2026-12-31
```

Nugs exposes song/setlist search rather than unrestricted free-text release search. Venue and date options filter the bounded song, artist, or year result set; the CLI does not crawl the catalog and pretend that filter is a global search.

### Inspect Show & Setlist
```bash
# By show ID or nugs URL
nugs show 48955
nugs show "https://play.nugs.net/release/48955"
```

Output:
```
Dave Matthews Band — 07/25/26 The Meadows Music Theatre, Hartford, CT 
Date: 7/25/2026 | Duration: 02:28:50 | Show ID: 48955
Venue: The Meadows Music Theatre (Hartford, CT)

Setlist (24 tracks):
Track ID  Set     #   Song Title                   
--------  ------  --  -----------------------------
781979    Set 1   1   Jimi Thing                   
781980    Set 1   2   Word Up!                     
781981    Set 1   3   Pantala Naqa Pampa           
781982    Set 1   4   Pig                          
781983    Set 1   5   Fool To Think                
781984    Set 1   6   Only Takes a Moment (Cha Cha)
781985    Set 1   7   What Would You Say           
781986    Set 1   8   The Ocean and the Butterfly  
781987    Set 1   9   So Damn Lucky                
781988    Set 1   10  Break Free                   
...
782001    Encore  11  All That I Wanted            
782002    Encore  12  All Along the Watchtower     

Available formats: MP3, ALAC, ALAC-HD
```

### Get Audio Preview Clip URL
```bash
# Get a preview clip for a song by title or track number
nugs clip-url 48955 "Jimi Thing"
# Output: https://assets.nugs.net/clips2/dmb260725d1_01_Jimi_Thing_c.mp3
```

Title matching prefers an exact song title. If a partial title matches multiple tracks, the command asks you to use a track number instead of silently choosing the wrong song.

### Play an Audio Preview

```bash
# Plays 10 seconds by default
nugs play-clip 48955 "Jimi Thing"

# Choose the duration
nugs play-clip 48955 1 --seconds 5
```

Playback uses `afplay` on macOS, or `ffplay`/`mpv` when installed. The command exits unsuccessfully if no supported player is available or playback fails.

### Control Full Subscriber Playback

Full playback stays inside the official Nugs web player. Start Chrome with a dedicated profile and a loopback-only DevTools endpoint, then log into Nugs in that profile once:

```bash
google-chrome \
  --user-data-dir="$HOME/.local/share/nugs-cli/chrome-profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --no-first-run \
  about:blank
```

The CLI attaches to that existing session. It never asks for, reads, prints, or stores your Nugs password or access tokens.

```bash
# Check the browser and logged-in session without starting playback
nugs doctor
nugs doctor --target 48955

# Start the release, or start any exact track by number, ID, or title
nugs play 48955
nugs play 48955 --track 7
nugs play 48955 --track 781985
nugs play 48955 --track "What Would You Say"
nugs play-track --target 48955 --track-title "Jimi Thing"

# Inspect and control the same native player
nugs status
nugs pause
nugs resume --target 48955
nugs next --target 48955 --from-track-title "Jimi Thing" --to-track-title "Word Up!"
nugs previous --target 48955 --from-track-title "Word Up!" --to-track-title "Jimi Thing"
nugs stop
```

Use `--cdp-endpoint` or `NUGS_CDP_ENDPOINT` when Chrome listens somewhere other than `http://127.0.0.1:9222`. Keep the endpoint loopback-only: Chrome DevTools access is equivalent to access to the logged-in browser profile.

### Featured & Popular Shows
```bash
nugs featured
nugs popular --limit 10
```

### Livestreams & Webcasts
```bash
nugs livestreams
```

### JSON Output
Pass `--json` to any command for structured JSON output:
```bash
nugs show 48955 --json
nugs shows "Phish" --json
nugs search "Two Step" --artist 803 --year 2026 --json
nugs doctor --json
nugs play-clip 48955 1 --seconds 1 --json
```

Errors also use JSON when `--json` is present and always return a nonzero exit status.

---

## Python SDK

You can also use `nugs_cli` directly as a Python library:

```python
import nugs_cli

# Search artists
artists = nugs_cli.get_artists("Dave Matthews")
artist_id = artists[0]["id"]  # 803

# Search shows containing a song
matches = nugs_cli.search_catalog("Two Step", artist=artist_id, year=2026)

# List shows
shows = nugs_cli.get_shows_by_artist(artist_id, limit=5)
for s in shows["items"]:
    print(s["id"], s["performance_date"], s["venue"])

# Fetch full show & setlist
show = nugs_cli.get_show(48955)
print(f"Setlist for {show['title']}:")
for track in show["tracks"]:
    print(f"  {track['track_num']}. {track['title']} ({track['clip_url']})")

# Livestreams
streams = nugs_cli.get_livestreams()
```

## Development

The test suite has no third-party runner requirement:

```bash
python -m unittest discover -v
```

To verify the distributable package:

```bash
python -m pip wheel --no-deps .
```

## Responsible Use

This client is unofficial and relies on undocumented public catalog endpoints plus rendered first-party web-player controls. Use it only in ways permitted by the [nugs.net Terms of Use](https://www.nugs.net/terms.html) that apply to you and by applicable law.

The project intentionally does not contain Nugs client secrets, reproduce Nugs application code, bypass authentication or subscription access, defeat digital-rights controls, expose protected stream URLs, or download subscriber media. Full playback requires the user's own active subscription and logged-in official web session.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

*Disclaimer: This independent open-source project is not affiliated with, sponsored by, or endorsed by nugs.net or Live Nation. “nugs.net” is used only to identify the service this client works with.*
