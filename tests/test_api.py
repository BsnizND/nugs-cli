import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from nugs_cli import api


class TestNugsAPI(unittest.TestCase):
    def test_extract_show_id(self):
        self.assertEqual(api.extract_show_id(48955), 48955)
        self.assertEqual(api.extract_show_id("48955"), 48955)
        self.assertEqual(
            api.extract_show_id(
                "https://www.nugs.net/live-download-of-dave-matthews-band-the-meadows-hartford-ct-07-25-2026-mp3-flac-or-online-music-streaming/48955.html"
            ),
            48955,
        )
        self.assertEqual(
            api.extract_show_id("https://play.nugs.net/release/48955"),
            48955,
        )
        with self.assertRaises(ValueError):
            api.extract_show_id("invalid-target-no-digits")

    @patch("nugs_cli.api._http_get")
    def test_get_artists_and_filter(self, mock_get):
        mock_get.return_value = {
            "Response": {
                "artists": [
                    {"artistID": 803, "artistName": "Dave Matthews Band", "artistNameNoThe": "dave matthews band", "numShows": 128, "numAlbums": 0},
                    {"artistID": 1246, "artistName": "Dave Alvin", "artistNameNoThe": "dave alvin", "numShows": 1, "numAlbums": 0},
                    {"artistID": 1054, "artistName": "Dead & Company", "artistNameNoThe": "dead & company", "numShows": 200, "numAlbums": 0},
                ]
            }
        }
        all_artists = api.get_artists()
        self.assertEqual(len(all_artists), 3)

        dmb = api.get_artists(query="Dave Matthews")
        self.assertEqual(len(dmb), 1)
        self.assertEqual(dmb[0]["id"], 803)

        dave = api.get_artists(query="Dave")
        self.assertEqual(len(dave), 2)

    @patch("nugs_cli.api._http_get")
    def test_resolve_artist(self, mock_get):
        mock_get.return_value = {
            "Response": {
                "artists": [
                    {"artistID": 803, "artistName": "Dave Matthews Band", "artistNameNoThe": "dave matthews band", "numShows": 128, "numAlbums": 0},
                ]
            }
        }
        artist = api.resolve_artist(803)
        self.assertEqual(artist["id"], 803)
        self.assertEqual(artist["name"], "Dave Matthews Band")

        artist_by_name = api.resolve_artist("Dave Matthews Band")
        self.assertEqual(artist_by_name["id"], 803)

    @patch("nugs_cli.api._http_get")
    def test_get_shows_by_artist(self, mock_get):
        def side_effect(url, params=None, headers=None):
            if "catalog.artists" in str(params):
                return {
                    "Response": {
                        "artists": [{"artistID": 803, "artistName": "Dave Matthews Band", "numShows": 128}]
                    }
                }
            return {
                "items": [
                    {
                        "id": "48955",
                        "title": "07/25/26 The Meadows",
                        "performanceDate": "2026-07-25T00:00:00",
                        "venue": {"name": "The Meadows", "city": "Hartford", "state": "CT"},
                        "hasVideoOnDemand": False,
                        "audioFormatTypes": ["mp3", "flac"],
                    }
                ],
                "total": 128,
            }

        mock_get.side_effect = side_effect
        res = api.get_shows_by_artist(803, limit=1)
        self.assertEqual(res["total"], 128)
        self.assertEqual(len(res["items"]), 1)
        self.assertEqual(res["items"][0]["id"], 48955)

    @patch("nugs_cli.api._http_get")
    def test_get_show(self, mock_get):
        mock_get.return_value = {
            "Response": {
                "containerID": 48955,
                "containerInfo": "07/25/26 The Meadows Music Theatre, Hartford, CT",
                "artistID": 803,
                "artistName": "Dave Matthews Band",
                "venueName": "The Meadows Music Theatre",
                "venueCity": "Hartford",
                "venueState": "CT",
                "performanceDate": "7/25/2026",
                "hhmmssTotalRunningTime": "02:28:50",
                "totalContainerRunningTime": 8930,
                "songs": [
                    {
                        "trackID": 781979,
                        "songID": 49561,
                        "songTitle": "Jimi Thing",
                        "setNum": 1,
                        "trackNum": 1,
                        "clipURL": "https://assets.nugs.net/clips2/dmb260725d1_01_Jimi_Thing_c.mp3",
                    }
                ],
                "productFormatList": [{"skuID": 917964, "formatStr": "MP3", "cost": 1499}],
            }
        }
        show = api.get_show(48955)
        self.assertEqual(show["show_id"], 48955)
        self.assertEqual(show["artist_name"], "Dave Matthews Band")
        self.assertEqual(show["track_count"], 1)
        self.assertEqual(show["tracks"][0]["title"], "Jimi Thing")
        self.assertEqual(show["tracks"][0]["clip_url"], "https://assets.nugs.net/clips2/dmb260725d1_01_Jimi_Thing_c.mp3")

    @patch("nugs_cli.api._http_get")
    def test_featured_releases_are_normalized_and_limited(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "10",
                    "title": "First Show",
                    "performanceDate": "2026-08-24T00:00:00",
                    "artist": {"id": "1205", "name": "Goose"},
                    "venue": {"name": "The Venue", "city": "Bend", "state": "OR"},
                },
                {
                    "id": "11",
                    "title": "Second Show",
                    "artist": {"id": "803", "name": "Dave Matthews Band"},
                },
            ]
        }

        result = api.get_featured_releases(limit=1)

        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["artist_name"], "Goose")
        self.assertEqual(result["items"][0]["venue"], "The Venue (Bend, OR)")

    @patch("nugs_cli.api._http_get")
    def test_popular_releases_normalize_nested_show_details(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "46884",
                    "availabilityType": "available",
                    "releaseType": "show",
                    "artist": {"id": "1205", "name": "Goose"},
                    "showDetails": {
                        "performanceDate": "2026-08-13T07:00:00Z",
                        "venue": {
                            "title": "Cal Coast Credit Union Open Air Theatre, San Diego, CA",
                            "name": "Cal Coast Credit Union Open Air Theatre",
                            "city": "San Diego",
                            "state": "CA",
                        },
                    },
                }
            ],
            "total": 100,
        }

        result = api.get_popular_releases(limit=1)
        item = result["items"][0]

        self.assertEqual(item["artist_name"], "Goose")
        self.assertEqual(item["performance_date"], "2026-08-13T07:00:00Z")
        self.assertEqual(item["title"], "Cal Coast Credit Union Open Air Theatre, San Diego, CA")

    @patch("nugs_cli.api._http_get")
    def test_livestreams_exclude_expired_events_and_sort_upcoming(self, mock_get):
        now = datetime.now(timezone.utc)
        past = (now - timedelta(days=2)).isoformat()
        future_later = (now + timedelta(days=2)).isoformat()
        future_sooner = (now + timedelta(days=1)).isoformat()
        mock_get.return_value = {
            "items": [
                {
                    "skuId": 1,
                    "startDate": past,
                    "endDate": past,
                    "release": {"id": "1", "title": "Expired", "artist": {"name": "Old Artist"}},
                },
                {
                    "skuId": 2,
                    "startDate": future_later,
                    "endDate": future_later,
                    "release": {"id": "2", "title": "Later", "artist": {"name": "Artist Two"}},
                },
                {
                    "skuId": 3,
                    "startDate": future_sooner,
                    "endDate": future_sooner,
                    "release": {"id": "3", "title": "Sooner", "artist": {"name": "Artist Three"}},
                },
            ]
        }

        result = api.get_livestreams(limit=10)

        self.assertEqual(result["total"], 2)
        self.assertEqual([item["title"] for item in result["items"]], ["Sooner", "Later"])
        self.assertEqual(result["items"][0]["artist_name"], "Artist Three")
        mock_get.assert_called_once_with(
            f"{api.CATALOG_API_BASE}/livestreams",
            params={"limit": 100, "offset": 0},
        )


if __name__ == "__main__":
    unittest.main()
