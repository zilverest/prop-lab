import datetime as dt
import unittest

import nba_audit


class NbaAuditTests(unittest.TestCase):
    def test_outcome_rows_extracts_market(self):
        payload = {
            "bookmakers": [{
                "key": "draftkings",
                "markets": [{
                    "key": "player_points",
                    "outcomes": [
                        {"name": "Over", "description": "Player A", "point": 20.5},
                        {"name": "Under", "description": "Player A", "point": 20.5},
                    ],
                }],
            }]
        }
        rows = nba_audit.outcome_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["_market"], "player_points")

    def test_history_window_presence(self):
        tip = "2026-10-20T00:00:00Z"
        payload = {
            "snapshots": [
                {"recorded_at": "2026-10-19T20:02:00Z"},
                {"recorded_at": "2026-10-19T23:31:00Z"},
            ]
        }
        result = nba_audit.history_window_presence(payload, tip)
        self.assertTrue(result["T-4h"])
        self.assertTrue(result["T-0.5h"])
        self.assertFalse(result["T-8h"])

    def test_classify_verdict_requires_some_real_access(self):
        self.assertEqual(
            nba_audit.classify_verdict(2, True, True, True),
            "CONDITIONAL PASS",
        )
        self.assertEqual(
            nba_audit.classify_verdict(0, False, False, False),
            "BLOCKED",
        )

    def test_id_coverage(self):
        rows = [
            {"outcome_id": "1", "player_id": "p1", "book_outcome_id": "b1"},
            {"outcome_id": "2", "player_id": "", "book_outcome_id": None},
        ]
        coverage = nba_audit.id_coverage(rows)
        self.assertEqual(coverage["outcome_id"]["present"], 2)
        self.assertEqual(coverage["player_id"]["present"], 1)


if __name__ == "__main__":
    unittest.main()
