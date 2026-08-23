# nugs-cli 🎸

Fast, lightweight, reverse-engineered CLI and Python client for [nugs.net](https://www.nugs.net) live music catalog, concert recordings, setlists, and webcasts.

Zero headless browser dependencies, zero scraping, zero heavy dependencies. Pure Python 3 standard library with sub-100ms response times.

---

## Features

- **640+ Artists Directory:** Search and resolve artist IDs and catalog counts (Dave Matthews Band, Phish, Dead & Company, Goose, Billy Strings, Pearl Jam, Bruce Springsteen, Metallica, etc.).
- **Concert & Show Catalogs:** List recent and historical shows by artist with venue, date, city, state, and container ID.
- **Complete Setlist & Track Inspection:** Instant setlist breakdown, track numbers, track IDs, set separations, and durations.
- **30-Second Preview Clips:** Direct URL extraction for audio preview clips (`.mp3`) for every track.
- **Webcasts & Livestreams:** Active, upcoming, and exclusive livestream schedule discovery.
- **Dual Mode:** Beautifully formatted console tables for humans, clean structured `--json` for automation and LLM agents.

---

## Reverse-Engineered API Reference

The nugs.net web player (`play.nugs.net`) uses modern REST/JSON microservices behind the scenes. No authentication is needed for catalog discovery and metadata:

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `https://streamapi.nugs.net/api.aspx?method=catalog.artists&availType=1` | `GET` | Complete directory of 640+ artists with IDs, show counts, and avatars |
| `https://catalog.nugs.net/api/v1/releases?artistIds={artistId}&limit=20` | `GET` | Paginated show list for any artist ID |
| `https://catalog.nugs.net/api/v1/shows/{showId}` | `GET` | Complete show details, venue, date, full setlist, track IDs, clip URLs, SKUs |
| `https://catalog.nugs.net/api/v1/releases/featured` | `GET` | Currently featured releases |
| `https://catalog.nugs.net/api/v1/releases/popular` | `GET` | Most popular releases |
| `https://catalog.nugs.net/api/v1/livestreams` | `GET` | Upcoming and active live webcasts |
| `https://playback.nugs.net/v1/tracks/{trackId}/url` | `GET` | Full track stream resolution (Requires Bearer Auth) |

---

## Installation

### With pip
```bash
pip install git+https://github.com/BsnizND/nugs-cli.git
```

### With pipx (Recommended for standalone CLI)
```bash
pipx install git+https://github.com/BsnizND/nugs-cli.git
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
Shows for: Goose (ID: 1205) — Total: 491

Show ID  Date        Venue                                                    Title                                                          
-------  ----------  -------------------------------------------------------  ---------------------------------------------------------------
46889    2026-08-19  WaMu Theater (Seattle, WA)                               8-19-2026 WaMu Theater Seattle, WA                             
46887    2026-08-16  Grand Theatre at Grand Sierra Resort (Reno, NV)          8-16-2026 Grand Theatre at Grand Sierra Resort Reno, NV        
46884    2026-08-13  Cal Coast Credit Union Open Air Theatre (San Diego, CA)  8-13-2026 Cal Coast Credit Union Open Air Theatre San Diego, CA
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
# Get 30s preview clip for song by title or track number
nugs clip-url 48955 "Jimi Thing"
# Output: https://assets.nugs.net/clips2/dmb260725d1_01_Jimi_Thing_c.mp3
```

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
```

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

---

## License

MIT License. See [LICENSE](LICENSE) for details.

*Disclaimer: This project is an independent open-source reverse-engineering tool and is not affiliated with, sponsored by, or endorsed by nugs.net or Live Nation.*
