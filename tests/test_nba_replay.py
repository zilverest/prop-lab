import datetime as dt
import unittest
import nba_replay

class NbaReplayTests(unittest.TestCase):
    def test_american_helpers(self):
        self.assertAlmostEqual(nba_replay.am_to_prob(-110),110/210,places=6)
        self.assertAlmostEqual(nba_replay.am_to_decimal(150),2.5,places=6)

    def test_no_vig_pair_sums_to_one(self):
        over=nba_replay.no_vig_prob(-115,-105,"over")
        under=nba_replay.no_vig_prob(-115,-105,"under")
        self.assertAlmostEqual(over+under,1.0,places=9)

    def test_latest_at_never_uses_future_snapshot(self):
        rows=[
            {"book":"a","market":"player_points","player":"P","side":"Over","outcome_id":"1","recorded_at":"2026-10-07T16:00:00Z"},
            {"book":"a","market":"player_points","player":"P","side":"Over","outcome_id":"1","recorded_at":"2026-10-07T18:00:00Z"},
        ]
        cutoff=dt.datetime(2026,10,7,17,0,tzinfo=dt.timezone.utc)
        got=nba_replay.latest_at(rows,cutoff)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]["recorded_at"],"2026-10-07T16:00:00Z")

    def test_candidate_pool_leave_one_out_excludes_candidate_book(self):
        rows=[]
        prices={
            "a":(-110,-110),
            "b":(-120,100),
            "c":(-125,105),
        }
        for book,(ov,un) in prices.items():
            rows += [
                {"book":book,"market":"player_points","line_type":"main","player":"P","side":"Over","point":20.5,"price":ov,"outcome_id":book+"o","player_id":"p","recorded_at":"2026-10-07T16:00:00Z"},
                {"book":book,"market":"player_points","line_type":"main","player":"P","side":"Under","point":20.5,"price":un,"outcome_id":book+"u","player_id":"p","recorded_at":"2026-10-07T16:00:00Z"},
            ]
        pool=nba_replay.candidate_pool(rows,"LOO_CONSENSUS")
        for cand in pool:
            self.assertNotIn(cand["book"],cand["reference_books"])

    def test_deterministic_random_control(self):
        pool=[{"x":1},{"x":2},{"x":3}]
        a=nba_replay.deterministic_pick(pool,"seed")
        b=nba_replay.deterministic_pick(pool,"seed")
        self.assertEqual(a,b)

if __name__=="__main__":
    unittest.main()
