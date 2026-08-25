# nugs-cli

An unofficial, lightweight CLI and Python client for exploring the public [nugs.net](https://www.nugs.net) live-music catalog, concert metadata, setlists, preview clips, and webcasts.

It uses Python's standard library only: no browser automation and no runtime package dependencies.

---

## Features

- **Artist Directory:** Search and resolve artist IDs and catalog counts (Dave Matthews Band, Phish, Dead & Company, Goose, Billy Strings, Pearl Jam, Bruce Springsteen, Metallica, etc.).
- **Concert & Show Catalogs:** List recent and historical shows by artist with venue, date, city, state, and container ID.
- **Setlist & Track Inspection:** Show set breakdown, track numbers, track IDs, and available durations.
- **Preview Clips:** Resolve and play the public audio preview when nugs provides one for a track.
- **Webcasts & Livestreams:** Active, upcoming, and exclusive livestream schedule discovery.
- **Text or JSON:** Readable console tables for humans and structured `--json` output for automation.

---

## Endpoint Reference

The client uses undocumented JSON endpoints also used by nugs.net's public catalog experience. No account credentials are read or stored. Because these are not a supported public developer API, their response formats can change without notice.

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `https://streamapi.nugs.net/api.aspx?method=catalog.artists&availType=1` | `GET` | Complete directory of 640+ artists with IDs, show counts, and avatars |
| `https://catalog.nugs.net/api/v1/releases?artistIds={artistId}&limit=20` | `GET` | Paginated show list for any artist ID |
| `https://catalog.nugs.net/api/v1/shows/{showId}` | `GET` | Complete show details, venue, date, full setlist, track IDs, clip URLs, SKUs |
| `https://catalog.nugs.net/api/v1/releases/featured` | `GET` | Currently featured releases |
| `https://catalog.nugs.net/api/v1/releases/popular` | `GET` | Most popular releases |
| `https://catalog.nugs.net/api/v1/livestreams` | `GET` | Upcoming and active live webcasts |

---

## Installation

### With pip
```bash
pip install git+https://github.com/BsnizND/nugs-cli.git@v1.0.0
```

### With pipx (Recommended for standalone CLI)
```bash
pipx install git+https://github.com/BsnizND/nugs-cli.git@v1.0.0
```

### From Source
```bash
git clone https://github.com/BsnizND/nugs-cli.git
cd nugs-cli
pip install -e .
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

This client is unofficial and relies on undocumented endpoints. Use it only in ways permitted by the [nugs.net Terms of Use](https://www.nugs.net/terms.html) that apply to you and by applicable law. It does not bypass authentication, subscription access, or digital-rights controls, and it intentionally does not resolve full subscriber streams.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

*Disclaimer: This independent open-source project is not affiliated with, sponsored by, or endorsed by nugs.net or Live Nation. “nugs.net” is used only to identify the service this client works with.*
