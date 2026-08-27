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


if __name__ == "__main__":
    unittest.main()
