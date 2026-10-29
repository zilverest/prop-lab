import datetime as dt
import json
import unittest
from unittest.mock import patch

import parlay_lab


def play_row(date_s, model, player_a, player_b, fair, edge, price=150, resolution="open", pnl="", board_ts="2026-10-25T12:00:00Z"):
    legs = [
        {
            "event_id": f"{player_a}-event",
            "market": "player_receptions",
            "player": player_a,
            "point": "3.5",
            "side": "Over",
            "fair_prob": 0.55,
            "n_books": 7,
            "confirm_books": ["draftkings"],
            "price": -110,
            "book": "draftkings",
            "home": "Home A",
            "away": "Away A",
        },
        {
            "event_id": f"{player_b}-event",
            "market": "player_receptions",
            "player": player_b,
            "point": "4.5",
            "side": "Under",
            "fair_prob": 0.52,
            "n_books": 8,
            "confirm_books": ["draftkings"],
            "price": -105,
            "book": "draftkings",
            "home": "Home B",
            "away": "Away B",
        },
    ]
    return {
        "phase": "forward",
        "board_date": date_s,
        "board_ts": board_ts,
        "week_key": parlay_lab._week_key(date_s),
        "model": model,
        "decision": "play",
        "legs": json.dumps(legs, separators=(",", ":")),
        "book": "draftkings",
        "price": str(price),
        "fair_joint_prob": str(fair),
        "model_edge_pct": str(edge),
        "stake": "5",
        "resolution": resolution,
        "pnl": str(pnl),
    }


class TestEeveeTelegram(unittest.TestCase):
    def test_final_slip_uses_highest_frozen_joint_probability(self):
        rows = [
            play_row("2026-10-25", "V2", "Consensus A", "Consensus B", 0.30, 12.0, price=220),
            play_row("2026-10-25", "V3", "Consensus A", "Consensus B", 0.30, 12.0, price=220),
            play_row("2026-10-25", "V4", "Highest A", "Highest B", 0.34, 6.0, price=180),
        ]
        with patch.object(parlay_lab, "read_rows", return_value=rows):
            msg = parlay_lab.final_slip_telegram("2026-10-25")

        self.assertIn("🔥 EEVEE FINAL SLIP", msg)
        self.assertIn("Highest A", msg)
        self.assertIn("Highest B", msg)
        self.assertNotIn("Consensus A", msg)
        self.assertIn("Frozen fair hit: 34.0%", msg)
        self.assertIn("Model agreement: V4", msg)
        self.assertIn("highest frozen joint fair probability", msg)

    def test_final_slip_uses_model_agreement_as_tiebreak(self):
        rows = [
            play_row("2026-10-25", "V2", "Consensus A", "Consensus B", 0.30, 7.0, price=180),
            play_row("2026-10-25", "V3", "Consensus A", "Consensus B", 0.30, 7.0, price=180),
            play_row("2026-10-25", "V4", "Solo A", "Solo B", 0.30, 15.0, price=260),
        ]
        with patch.object(parlay_lab, "read_rows", return_value=rows):
            msg = parlay_lab.final_slip_telegram("2026-10-25")

        self.assertIn("Consensus A", msg)
        self.assertNotIn("Solo A", msg)
        self.assertIn("Model agreement: V2 · V3", msg)

    def test_tuesday_weekly_summary_uses_completed_tue_mon_window(self):
        rows = [
            play_row("2026-10-18", "V4", "Old A", "Old B", 0.31, 7.0, resolution="won", pnl="8.50"),
            play_row("2026-10-25", "V4", "In A", "In B", 0.32, 7.5, resolution="won", pnl="4.59"),
            play_row("2026-10-29", "V4", "Future A", "Future B", 0.33, 8.0, resolution="open", pnl=""),
        ]
        now = dt.datetime(2026, 10, 27, 12, 0, tzinfo=dt.timezone.utc)
        with patch.object(parlay_lab, "read_rows", return_value=rows):
            msg = parlay_lab.weekly_telegram(now)

        self.assertIn("Oct 20–Oct 26", msg)
        self.assertIn("Unique frozen lineups: 1", msg)
        self.assertIn("V4 DraftKings: 1–0 · 1 slips · +$4.59", msg)
        self.assertNotIn("+$8.50", msg)
        self.assertNotIn("open · 1 slips", msg)


if __name__ == "__main__":
    unittest.main()
