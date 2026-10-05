import csv, datetime as dt, os, tempfile, unittest

import common, shadow_lab


def write_csv(path, fields, rows):
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)


class ShadowLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old_data=common.DATA
        common.DATA=self.tmp.name;os.makedirs(common.DATA,exist_ok=True)

    def tearDown(self):
        common.DATA=self.old_data;self.tmp.cleanup()

    def _board(self,n_books=5):
        now=dt.datetime(2026,10,11,14,0,tzinfo=dt.timezone.utc)
        kick1=now+dt.timedelta(hours=3);kick2=now+dt.timedelta(hours=4)
        fields=["ts","sport","event_id","commence_time","home","away","market","player","point","side","book","price","ev_pct","fair_prob","fair_source","n_books","hours_to_kick"]
        books=["pinnacle","bovada","draftkings","fanduel","hardrock"][:n_books]
        rows=[]
        for eid,kick,player in (("E1",kick1,"Player One"),("E2",kick2,"Player Two")):
            for book in books:
                rows.append(dict(ts=common.iso(now),sport="football_nfl",event_id=eid,commence_time=common.iso(kick),
                    home="A",away="B",market="player_receptions",player=player,point="3.5",side="Over",
                    book=book,price=120 if book!="pinnacle" else -110,ev_pct="5.0",fair_prob=".55",
                    fair_source="pinnacle",n_books=str(n_books),hours_to_kick="3"))
        write_csv(common.csv_path("current_lines"),fields,rows)
        cfields=fields+["bettable","gate_note"]
        write_csv(common.csv_path("candidates"),cfields,[dict(r,bettable="False",gate_note="test") for r in rows])
        return now,rows

    def test_min4_ablation_can_play_when_official_v2_cannot(self):
        now,_=self._board(n_books=4)
        n=shadow_lab.observe(now)
        self.assertGreater(n,0)
        rows=common.read_rows("shadow_snapshots")
        a=next(r for r in rows if r["variant"]=="A_MIN4")
        off=next(r for r in rows if r["variant"]=="OFF_V2")
        self.assertEqual(a["decision"],"play")
        self.assertEqual(off["decision"],"no_play")

    def test_shadow_settlement_writes_brier(self):
        now,board=self._board(n_books=5)
        shadow_lab.observe(now)
        result_fields=["graded_ts","event_id","market","player","point","side","book","price","resolution","actual_value"]
        results=[]
        for eid,player in (("E1","Player One"),("E2","Player Two")):
            results.append(dict(graded_ts=common.iso(now+dt.timedelta(hours=6)),event_id=eid,market="player_receptions",
                                player=player,point="3.5",side="Over",book="bovada",price="120",resolution="won",actual_value="5"))
        write_csv(common.csv_path("results"),result_fields,results)
        settled=shadow_lab.settle(now+dt.timedelta(hours=7))
        self.assertGreater(settled,0)
        plays=[r for r in common.read_rows("shadow_snapshots") if r["decision"]=="play" and r["resolution"]=="won"]
        self.assertTrue(plays)
        self.assertTrue(all(r["brier"]!="" for r in plays))


if __name__=="__main__":
    unittest.main()
