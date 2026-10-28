import csv, datetime as dt, os, tempfile, unittest

import common, early_edge

def write_csv(path, fields, rows):
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

class EarlyEdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=common.DATA
        common.DATA=self.tmp.name;os.makedirs(common.DATA,exist_ok=True)

    def tearDown(self):
        common.DATA=self.old;self.tmp.cleanup()

    def _rows(self,ts):
        kick=common.parse_iso(ts)+dt.timedelta(hours=20)
        base=dict(ts=ts,sport="football_nfl",event_id="E1",commence_time=common.iso(kick),
                  home="A",away="B",market="player_receptions",player="Player One",
                  point="3.5",side="Over",fair_prob=".50",fair_source="pinnacle",
                  n_books="6",hours_to_kick="20")
        return [dict(base,book="draftkings",price="120",ev_pct="5.0"),
                dict(base,book="fanduel",price="130",ev_pct="7.0")]

    def test_first_signal_freezes_best_offer_once(self):
        ts="2026-10-20T12:00:00Z";rows=self._rows(ts);fields=list(rows[0])
        write_csv(common.csv_path("current_lines"),fields,rows)
        write_csv(common.csv_path("candidates"),fields,rows)
        self.assertEqual(early_edge.observe(common.parse_iso(ts)),1)
        sig=common.read_rows("e1_early_edge_signals")
        self.assertEqual(len(sig),1)
        self.assertEqual(sig[0]["book"],"fanduel")
        self.assertEqual(sig[0]["ev_pct"],"7.0")
        self.assertEqual(sig[0]["line_type_at_entry"],"unknown")
        ts2="2026-10-20T13:00:00Z";rows2=self._rows(ts2)
        write_csv(common.csv_path("current_lines"),fields,rows2)
        self.assertEqual(early_edge.observe(common.parse_iso(ts2)),0)

    def test_known_alternate_is_rejected(self):
        ts="2026-10-20T12:00:00Z";rows=self._rows(ts);fields=list(rows[0])
        write_csv(common.csv_path("current_lines"),fields,rows)
        write_csv(common.csv_path("candidates"),fields,rows)
        mfields=["event_id","market","player","point","side","book","line_type"]
        meta=[dict(event_id="E1",market="player_receptions",player="Player One",point="3.5",
                   side="Over",book=r["book"],line_type="alternate") for r in rows]
        write_csv(common.csv_path("current_line_meta"),mfields,meta)
        self.assertEqual(early_edge.observe(common.parse_iso(ts)),0)

    def test_preexisting_signal_is_not_backfilled(self):
        old="2026-10-20T11:00:00Z";ts="2026-10-20T12:00:00Z";rows=self._rows(ts);fields=list(rows[0])
        write_csv(common.csv_path("current_lines"),fields,rows)
        write_csv(common.csv_path("candidates"),fields,self._rows(old)+rows)
        self.assertEqual(early_edge.observe(common.parse_iso(ts)),0)


    def test_poc_filter_requires_edge_and_early_timing(self):
        base=dict(ev_pct="5.0",hours_to_kick="12.0")
        self.assertTrue(early_edge._is_poc(base))
        self.assertFalse(early_edge._is_poc(dict(base,ev_pct="4.99")))
        self.assertFalse(early_edge._is_poc(dict(base,hours_to_kick="11.99")))

    def test_dashboard_surfaces_poc_scoreboard(self):
        fields=early_edge.FIELDS
        rows=[
            dict(
                ts="2026-10-20T12:00:00Z",snapshot_ts="2026-10-20T12:00:00Z",
                event_id="E1",commence_time="2026-10-21T20:00:00Z",target_date="2026-10-21",
                week_key="2026-10-19",hours_to_kick="32",timing_bucket="T-24h+",
                market="player_receptions",player="Player One",point="3.5",side="Over",
                book="draftkings",price="120",ev_pct="6.0",fair_prob=".50",fair_source="pinnacle",
                n_books="6",line_type_at_entry="main",meta_available="True",signal_key="E1|x",
                persistence_final="1",persistence_class="D1",edge_bucket="5-8",
                resolution="won",pnl="6.0",brier=".25",calibration_error=".5",
                closing_price="-105",closing_point="3.5",closing_at="2026-10-21T19:00:00Z",
                same_point="True",clv_implied_pp="2.1",beat_close_price="True",
                beat_close_point="False",closing_line_type="main",settled_ts="2026-10-22T01:00:00Z",
                note="test",
            ),
            dict(
                ts="2026-10-20T13:00:00Z",snapshot_ts="2026-10-20T13:00:00Z",
                event_id="E2",commence_time="2026-10-20T19:00:00Z",target_date="2026-10-20",
                week_key="2026-10-19",hours_to_kick="6",timing_bucket="T-8_to_4h",
                market="player_receptions",player="Player Two",point="2.5",side="Under",
                book="fanduel",price="-110",ev_pct="4.0",fair_prob=".52",fair_source="pinnacle",
                n_books="6",line_type_at_entry="main",meta_available="True",signal_key="E2|x",
                persistence_final="1",persistence_class="D1",edge_bucket="3-5",
                resolution="lost",pnl="-5.0",brier=".27",calibration_error="-.52",
                closing_price="-112",closing_point="2.5",closing_at="2026-10-20T18:00:00Z",
                same_point="True",clv_implied_pp=".4",beat_close_price="True",
                beat_close_point="False",closing_line_type="main",settled_ts="2026-10-21T01:00:00Z",
                note="test",
            ),
        ]
        write_csv(common.csv_path("e1_early_edge_signals"),fields,rows)
        s=early_edge.poc_summary()
        self.assertEqual(s["poc"]["signals"],1)
        self.assertEqual(s["poc"]["wins"],1)
        self.assertEqual(s["broad"]["signals"],2)
        page=early_edge.dashboard_html()
        self.assertIn("POC · Early price dislocation",page)
        self.assertIn("1–0",page)
        self.assertIn("+$6.00",page)
        self.assertIn("2.10%",page)

if __name__=="__main__":
    unittest.main()
