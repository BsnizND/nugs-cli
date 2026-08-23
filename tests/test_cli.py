import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from nugs_cli import cli


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


if __name__ == "__main__":
    unittest.main()
