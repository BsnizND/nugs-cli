import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

from nugs_cli import api, cli, player


class TestNugsCLI(unittest.TestCase):
    @patch("nugs_cli.api.get_artists")
    def test_cli_artists_json(self, mock_get_artists):
        mock_get_artists.return_value = [
            {"id": 803, "name": "Dave Matthews Band", "num_shows": 128, "num_albums": 0}
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--json", "artists", "Dave"])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], 803)

    @patch("nugs_cli.api.get_artists")
    def test_cli_artists_json_honors_limit(self, mock_get_artists):
        mock_get_artists.return_value = [
            {"id": index, "name": f"Artist {index}", "num_shows": 1, "num_albums": 0}
            for index in range(3)
        ]
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["artists", "--limit", "1", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(buf.getvalue())), 1)

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["artists", "--limit", "0", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(buf.getvalue())), 3)

    @patch("nugs_cli.api.get_show")
    def test_cli_show_text(self, mock_get_show):
        mock_get_show.return_value = {
            "show_id": 48955,
            "title": "07/25/26 The Meadows",
            "artist_id": 803,
            "artist_name": "Dave Matthews Band",
            "venue_name": "The Meadows",
            "venue_city": "Hartford",
            "venue_state": "CT",
            "performance_date": "7/25/2026",
            "duration": "02:28:50",
            "track_count": 1,
            "tracks": [{"track_id": 781979, "set_num": 1, "track_num": 1, "title": "Jimi Thing"}],
            "products": [{"format": "MP3"}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["show", "48955"])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("Dave Matthews Band", output)
        self.assertIn("Jimi Thing", output)
        self.assertIn("781979", output)

    @patch("nugs_cli.api.search_catalog")
    def test_cli_search_json(self, mock_search):
        mock_search.return_value = {
            "query": "Two Step",
            "filters": {},
            "artists": [],
            "shows": [{"show_id": 48951, "matched_tracks": [{"title": "Two Step"}]}],
            "total_before_local_filters": 1,
            "limit": 20,
            "offset": 0,
        }
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["search", "Two Step", "--artist", "Dave Matthews Band", "--year", "2026", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["shows"][0]["show_id"], 48951)
        mock_search.assert_called_once_with(
            "Two Step",
            artist="Dave Matthews Band",
            year=2026,
            venue=None,
            date_from=None,
            date_to=None,
            limit=20,
            offset=0,
        )

    @patch("nugs_cli.api.get_show")
    def test_cli_clip_url(self, mock_get_show):
        mock_get_show.return_value = {
            "show_id": 48955,
            "tracks": [
                {"track_id": 781979, "track_num": 1, "title": "Jimi Thing", "clip_url": "https://example.com/clip1.mp3"},
                {"track_id": 781980, "track_num": 2, "title": "Word Up!", "clip_url": "https://example.com/clip2.mp3"},
            ],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["clip-url", "48955", "Word Up!"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), "https://example.com/clip2.mp3")

    def test_track_resolution_prefers_exact_title(self):
        show = {
            "tracks": [
                {"track_num": 5, "title": "The Empress of Organos"},
                {"track_num": 8, "title": "Empress of Organos"},
            ]
        }

        selected = cli._resolve_track_from_show(show, "Empress of Organos")

        self.assertEqual(selected["track_num"], 8)

    def test_track_resolution_rejects_ambiguous_partial_title(self):
        show = {
            "tracks": [
                {"track_num": 5, "title": "The Empress of Organos"},
                {"track_num": 8, "title": "Empress of Organos"},
            ]
        }

        with self.assertRaisesRegex(cli.CLIError, "ambiguous"):
            cli._resolve_track_from_show(show, "Empress")

    @patch("nugs_cli.cli.subprocess.run")
    @patch("nugs_cli.cli.urllib.request.urlopen")
    @patch("nugs_cli.cli.shutil.which", return_value="/usr/bin/afplay")
    @patch("nugs_cli.api.get_show")
    def test_play_clip_json_reports_success(self, mock_get_show, _mock_which, mock_urlopen, mock_run):
        mock_get_show.return_value = {
            "show_id": 46891,
            "artist_name": "Goose",
            "title": "08/22/26 Hayden Homes Amphitheater",
            "tracks": [
                {
                    "track_id": 788423,
                    "track_num": 1,
                    "title": "Drive",
                    "clip_url": "https://example.com/drive.mp3",
                }
            ],
        }
        mock_urlopen.return_value = io.BytesIO(b"preview")
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["play-clip", "46891", "1", "--seconds", "1", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["status"], "played")
        mock_run.assert_called_once()

    @patch("nugs_cli.cli.shutil.which", return_value=None)
    @patch("nugs_cli.api.get_show")
    def test_play_clip_without_player_returns_json_error(self, mock_get_show, _mock_which):
        mock_get_show.return_value = {
            "show_id": 1,
            "artist_name": "Artist",
            "title": "Show",
            "tracks": [
                {"track_id": 11, "track_num": 1, "title": "Song", "clip_url": "https://example.com/song.mp3"}
            ],
        }
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["play-clip", "1", "--json"])

        self.assertEqual(code, 1)
        self.assertIn("No local audio player", json.loads(buf.getvalue())["error"])

    @patch("nugs_cli.api.get_artists", side_effect=api.NugsAPIError("network unavailable"))
    def test_api_failure_returns_json_error_without_traceback(self, _mock_get_artists):
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["artists", "Goose", "--json"])

        self.assertEqual(code, 1)
        self.assertEqual(json.loads(buf.getvalue()), {"error": "network unavailable"})

    @patch("nugs_cli.player.run_command", new_callable=AsyncMock)
    def test_player_status_json(self, mock_run_command):
        mock_run_command.return_value = {
            "command": "status",
            "player_present": True,
            "state": "playing",
            "release_id": "48955",
            "track_title": "Jimi Thing",
        }
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["status", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["track_title"], "Jimi Thing")
        self.assertEqual(len(buf.getvalue().splitlines()), 1)
        mock_run_command.assert_awaited_once()

    @patch("nugs_cli.player.run_command", new_callable=AsyncMock)
    def test_play_track_passes_exact_identity(self, mock_run_command):
        mock_run_command.return_value = {
            "command": "play-track",
            "player_present": True,
            "state": "playing",
            "release_id": "48955",
            "track_title": "Jimi Thing",
        }
        source_url = "https://www.nugs.net/show/48955.html"
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(
                [
                    "play-track",
                    "--target",
                    "48955",
                    "--track-title",
                    "Jimi Thing",
                    "--url",
                    source_url,
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        kwargs = mock_run_command.await_args.kwargs
        self.assertEqual(kwargs["target"], "48955")
        self.assertEqual(kwargs["track_title"], "Jimi Thing")
        self.assertEqual(kwargs["source_url"], source_url)

    @patch("nugs_cli.player.run_command", new_callable=AsyncMock)
    @patch("nugs_cli.api.get_show")
    def test_play_resolves_arbitrary_track_identity(self, mock_get_show, mock_run_command):
        mock_get_show.return_value = {
            "show_id": 48955,
            "tracks": [
                {"track_id": 781979, "track_num": 1, "title": "Jimi Thing"},
                {"track_id": 781985, "track_num": 7, "title": "What Would You Say"},
            ],
        }
        mock_run_command.return_value = {
            "command": "play-track",
            "player_present": True,
            "state": "playing",
            "release_id": "48955",
            "track_title": "What Would You Say",
        }
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["play", "48955", "--track", "7", "--json"])

        self.assertEqual(code, 0)
        kwargs = mock_run_command.await_args.kwargs
        self.assertEqual(kwargs["track_title"], "What Would You Say")
        self.assertEqual(kwargs["track_id"], 781985)

    @patch("nugs_cli.player.diagnose", new_callable=AsyncMock)
    def test_doctor_returns_failed_exit_with_structured_report(self, mock_diagnose):
        mock_diagnose.return_value = {
            "ok": False,
            "version": "1.2.0",
            "python": "3.12.0",
            "endpoint": "http://127.0.0.1:9222",
            "checks": [{"name": "browser", "ok": False, "detail": "not running"}],
        }
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["doctor", "--json"])

        self.assertEqual(code, 1)
        self.assertFalse(json.loads(buf.getvalue())["ok"])

    @patch("nugs_cli.player.run_command", new_callable=AsyncMock)
    def test_player_error_is_bounded_json(self, mock_run_command):
        mock_run_command.side_effect = player.PlayerError("not logged in")
        buf = io.StringIO()

        with redirect_stdout(buf):
            code = cli.main(["status", "--json"])

        self.assertEqual(code, 1)
        self.assertEqual(json.loads(buf.getvalue()), {"error": "not logged in"})


if __name__ == "__main__":
    unittest.main()
