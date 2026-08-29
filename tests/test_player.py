import unittest

from nugs_cli import player


class TestPlayerContract(unittest.TestCase):
    def test_target_for_accepts_id_and_release_url(self):
        expected = player.PlayerTarget("48955", "https://play.nugs.net/release/48955")

        self.assertEqual(player.target_for("48955"), expected)
        self.assertEqual(player.target_for("https://play.nugs.net/release/48955"), expected)

    def test_release_play_requires_one_exact_button(self):
        self.assertEqual(
            player.select_release_play([{"index": 4, "tag": "button", "text": "PLAY"}]),
            4,
        )
        with self.assertRaisesRegex(player.PlayerError, "found 2"):
            player.select_release_play(
                [
                    {"index": 1, "tag": "button", "text": "PLAY"},
                    {"index": 2, "tag": "button", "text": "PLAY"},
                ]
            )

    def test_transport_requires_one_exact_native_cluster(self):
        selected = player.select_transport_cluster(
            [
                {
                    "titles": ["Previous Track", "Play/Pause", "Next Track"],
                    "indexes": [3, 4, 5],
                }
            ]
        )

        self.assertEqual(selected["Play/Pause"], 4)
        with self.assertRaisesRegex(player.PlayerError, "found 0"):
            player.select_transport_cluster([])

    def test_track_selection_uses_exact_catalog_identity(self):
        rows = [
            {"index": 0, "data_id": "781979", "lines": ["1", "Jimi Thing"]},
            {"index": 6, "data_id": "781985", "lines": ["7", "What Would You Say"]},
        ]

        self.assertEqual(
            player.select_track_row(rows, title="What Would You Say", track_id=781985),
            6,
        )
        with self.assertRaisesRegex(player.PlayerError, "found 0"):
            player.select_track_row(rows, title="What Would You Say", track_id=999999)

    def test_player_endpoint_must_be_loopback(self):
        player.validate_endpoint("http://127.0.0.1:9222")
        player.validate_endpoint("http://localhost:9222")
        with self.assertRaisesRegex(player.PlayerError, "loopback"):
            player.validate_endpoint("http://192.168.1.20:9222")

    def test_signed_in_signal_uses_visible_navigation(self):
        self.assertTrue(player.signed_in_from_visible_text("Home\nMy Library\nSearch"))
        self.assertFalse(player.signed_in_from_visible_text("Home\nMy Library\nLog In"))

    def test_rendered_player_state_fills_missing_browser_media_state(self):
        self.assertEqual(player.reconcile_player_state("unknown", "playing", 1), "playing")
        self.assertEqual(player.reconcile_player_state("unknown", "unknown", 1), "playing")
        self.assertEqual(player.reconcile_player_state("unknown", "paused", 0), "paused")
        self.assertEqual(player.reconcile_player_state("paused", "playing", 1), "unknown")
        with self.assertRaisesRegex(player.PlayerError, "active track rows"):
            player.reconcile_player_state("unknown", "playing", 2)


if __name__ == "__main__":
    unittest.main()
