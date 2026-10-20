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

if __name__=="__main__":
    unittest.main()
