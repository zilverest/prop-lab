import unittest

import v1_v8_bridge as bridge


class V1V8BridgeTests(unittest.TestCase):
    def hist(self, variant="OFF_V2", date="2026-09-20", legs=None, price="293", resolution="won", pnl="14.64"):
        legs = legs or [
            {"event_id":"E1","market":"player_receptions","player":"A","point":"3.5","side":"Under"},
            {"event_id":"E2","market":"player_pass_interceptions","player":"B","point":"0.5","side":"Under"},
        ]
        return dict(
            variant=variant,date=date,benchmark_reason="development-aligned",
            cutoff="2026-09-20T10:00:00Z",decision="play",
            selection_key="",legs=__import__("json").dumps(legs),book="draftkings",
            price=price,fair_joint_prob=".28",model_edge_pct="8.0",
            resolution=resolution,pnl=pnl,qualified_legs="4",valid_pairs="5",
        )

    def fwd(self, model="V2", date="2026-10-11", legs=None, price="300", resolution="won", pnl="15.0"):
        legs = legs or [
            {"event_id":"F1","market":"player_receptions","player":"C","point":"3.5","side":"Over"},
            {"event_id":"F2","market":"player_reception_yds","player":"D","point":"25.5","side":"Over"},
        ]
        return dict(
            phase="forward",board_date=date,board_ts="2026-10-11T13:00:00Z",
            week_key="2026-10-05",model=model,model_name=model,slip_no="1",
            decision="play",qualified_legs="3",valid_pairs="2",
            legs=__import__("json").dumps(legs),book="draftkings",price=price,
            price_source="independent_product",fair_joint_prob=".25",
            model_edge_pct="7.0",stake="5",resolution=resolution,pnl=pnl,note="frozen",
        )

    def test_forward_date_supersedes_historical_date(self):
        hist=[self.hist(date="2026-10-11")]
        fwd=[self.fwd(date="2026-10-11")]
        rows=bridge.build_ledger(hist,fwd)
        self.assertTrue(rows)
        self.assertTrue(all(r["source_phase"]=="forward_frozen" for r in rows))

    def test_identical_model_tickets_dedupe_once(self):
        legs=[
            {"event_id":"F1","market":"player_receptions","player":"C","point":"3.5","side":"Over"},
            {"event_id":"F2","market":"player_reception_yds","player":"D","point":"25.5","side":"Over"},
        ]
        fwd=[self.fwd(model=m,legs=legs) for m in ("V2","V3","V5","V8")]
        rows=bridge.build_ledger([],fwd)
        unique=bridge.dedupe_tickets(rows)
        self.assertEqual(len(unique),1)
        self.assertEqual(unique[0]["models"],"V2,V3,V5,V8")
        self.assertEqual(unique[0]["model_count"],4)
        self.assertEqual(unique[0]["conflict"],"False")

    def test_v8_second_slip_remains_separate_ticket(self):
        h1=self.hist("OFF_V8")
        h2=self.hist("OFF_V8_2",legs=[
            {"event_id":"E3","market":"player_receptions","player":"X","point":"2.5","side":"Over"},
            {"event_id":"E4","market":"player_rush_yds","player":"Y","point":"40.5","side":"Under"},
        ],price="350")
        rows=bridge.build_ledger([h1,h2],[])
        unique=bridge.dedupe_tickets(rows)
        self.assertEqual(len(unique),2)
        slips=sorted(r["slip_no"] for r in rows if r["model"]=="V8" and r["decision"]=="play")
        self.assertEqual(slips,[1,2])

    def test_reconstructed_price_is_never_labeled_actual(self):
        rows=bridge.build_ledger([self.hist()],[self.fwd()])
        played=[r for r in rows if r["decision"]=="play"]
        self.assertTrue(played)
        self.assertTrue(all(r["pricing_status"]=="reconstructed_independent_product" for r in played))
        self.assertTrue(all(r["pnl_status"]=="hypothetical_from_reconstructed_price" for r in played))

    def test_historical_v7_blocked_row_is_explicit(self):
        rows=bridge.build_ledger([self.hist()],[])
        v7=[r for r in rows if r["model"]=="V7"]
        self.assertEqual(len(v7),1)
        self.assertEqual(v7[0]["decision"],"no_play")
        self.assertIn("blocked",v7[0]["note"])

    def test_unique_summary_does_not_multiply_same_ticket_by_models(self):
        fwd=[self.fwd(model=m) for m in ("V2","V3","V5","V8")]
        payload=bridge.build_payload([],fwd)
        self.assertEqual(payload["unique_summary"]["plays"],1)
        self.assertEqual(payload["unique_summary"]["wins"],1)
        self.assertEqual(payload["unique_summary"]["hypothetical_pnl"],15.0)


if __name__=="__main__":
    unittest.main()
