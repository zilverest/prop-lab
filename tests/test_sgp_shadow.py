import csv, datetime as dt, json, os, tempfile, unittest
from pathlib import Path

import common, sgp_shadow


def write_csv(path, fields, rows):
    with open(path, 'w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)


class StubApi:
    def __init__(self): self.calls=0
    def post(self,path,body,**params):
        self.calls+=1
        book=body.get('bookmaker')
        return {'quoted':True,'sgp_price':250 if book=='draftkings' else 240,'independent_price':220,'correlation_factor':0.94}


class SgpShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_data=common.DATA
        common.DATA=self.tmp.name
        os.makedirs(common.DATA,exist_ok=True)
    def tearDown(self):
        common.DATA=self.old_data
        self.tmp.cleanup()

    def test_positive_correlation_increases_same_direction_joint(self):
        p=sgp_shadow.correlated_joint_prob(.55,.55,.30,'Over','Over')
        self.assertGreater(p,.55*.55)
        self.assertLess(p,.55)
        mixed=sgp_shadow.correlated_joint_prob(.55,.55,.30,'Over','Under')
        self.assertLess(mixed,.55*.55)

    def test_roster_resolver_requires_event_team(self):
        idx={'john doe':[{'full_name':'John Doe','team':'PIT','position':'WR','week':'4'}, {'full_name':'John Doe','team':'CLE','position':'DB','week':'2'}]}
        r=sgp_shadow._resolve_player('John Doe',{'PIT','BAL'},idx)
        self.assertEqual(r['team'],'PIT')
        self.assertIsNone(sgp_shadow._resolve_player('John Doe',{'NYJ','BUF'},idx))

    def test_variant_gates(self):
        p=dict(relation='same_team',core_quality=True,dual_confirm=True,archetype='PASS_YDS__REC_YDS',tier='A',rho_cons=.30,independent_prob=.30,model_prob=.36)
        q={'best':{'book':'draftkings','sgp_price':250,'break_even':common.am_to_p(250)}}
        self.assertTrue(sgp_shadow._model_eval('S3-A',p,q)[0])
        p2=dict(p,dual_confirm=False)
        self.assertFalse(sgp_shadow._model_eval('S3-A',p2,q)[0])
        self.assertTrue(sgp_shadow._model_eval('S3-C',p2,q)[0])
        q_bad={'best':{'book':'draftkings','sgp_price':150,'break_even':common.am_to_p(150)}}
        self.assertFalse(sgp_shadow._model_eval('S3-C',p2,q_bad)[0])
        self.assertTrue(sgp_shadow._model_eval('S3-D',p2,q_bad)[0])

    def test_freeze_is_idempotent_and_settles(self):
        now=dt.datetime(2026,10,1,18,0,tzinfo=dt.timezone.utc)  # 2pm ET
        kick=now+dt.timedelta(hours=5)
        common.state_set('sgp_roster_cache',{'season':2026,'downloaded_at':common.iso(now),'rows':2,'source':'fixture'})
        write_csv(common.csv_path('sgp_roster_cache'),sgp_shadow.ROSTER_FIELDS,[
            {'season':2026,'week':4,'team':'PIT','position':'QB','full_name':'Test Quarterback','football_name':'Test','status':'ACT'},
            {'season':2026,'week':4,'team':'PIT','position':'WR','full_name':'Test Receiver','football_name':'Test','status':'ACT'},
        ])
        write_csv(common.csv_path('events'),['event_id','sport','home','away','commence_time','first_seen'],[
            {'event_id':'E1','sport':'football_nfl','home':'PIT Steelers','away':'CLE Browns','commence_time':common.iso(kick),'first_seen':common.iso(now-dt.timedelta(days=1))}
        ])
        fields=['ts','sport','event_id','commence_time','home','away','market','player','point','side','book','price','ev_pct','fair_prob','fair_source','n_books','hours_to_kick']
        rows=[]
        for book,price in [('pinnacle',-110),('bovada',105),('draftkings',102),('fanduel',100),('hardrock',-105)]:
            rows.append(dict(ts=common.iso(now),sport='football_nfl',event_id='E1',commence_time=common.iso(kick),home='PIT Steelers',away='CLE Browns',market='player_pass_yds',player='Test Quarterback',point='249.5',side='Over',book=book,price=price,ev_pct='4.0' if book in ('bovada','draftkings') else '0.5',fair_prob='.55',fair_source='pinnacle',n_books='5',hours_to_kick='5'))
            rows.append(dict(ts=common.iso(now),sport='football_nfl',event_id='E1',commence_time=common.iso(kick),home='PIT Steelers',away='CLE Browns',market='player_reception_yds',player='Test Receiver',point='54.5',side='Over',book=book,price=price,ev_pct='4.0' if book in ('bovada','draftkings') else '0.5',fair_prob='.55',fair_source='pinnacle',n_books='5',hours_to_kick='5'))
        write_csv(common.csv_path('current_lines'),fields,rows)
        # persistence source can be empty but needs no file
        api=StubApi()
        first=sgp_shadow.freeze(api,now)
        self.assertEqual(first['events'],1)
        self.assertGreater(first['decisions'],0)
        second=sgp_shadow.freeze(api,now)
        self.assertEqual(second['events'],0)
        decisions=common.read_rows('sgp_shadow_decisions')
        self.assertEqual(len({r['model'] for r in decisions}),len(sgp_shadow.SHADOW_MODELS))
        self.assertTrue(any(r['model']=='S3-A' and r['decision']=='play' for r in decisions))

        result_fields=['graded_ts','event_id','market','player','point','side','book','price','resolution','actual_value']
        result_rows=[]
        for book in ('draftkings','fanduel'):
            result_rows += [
                {'graded_ts':common.iso(kick+dt.timedelta(hours=4)),'event_id':'E1','market':'player_pass_yds','player':'Test Quarterback','point':'249.5','side':'Over','book':book,'price':'-110','resolution':'won','actual_value':'300'},
                {'graded_ts':common.iso(kick+dt.timedelta(hours=4)),'event_id':'E1','market':'player_reception_yds','player':'Test Receiver','point':'54.5','side':'Over','book':book,'price':'-110','resolution':'won','actual_value':'80'},
            ]
        write_csv(common.csv_path('results'),result_fields,result_rows)
        st=sgp_shadow.settle(kick+dt.timedelta(hours=5))
        self.assertGreater(st['decisions'],0)
        settled=common.read_rows('sgp_shadow_decisions')
        self.assertTrue(any(r['model']=='S3-A' and r['resolution']=='won' for r in settled))


if __name__=='__main__': unittest.main()
