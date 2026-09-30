import math, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from s3_true_correlation import hit, shrink_lift, pearson, build_pair_observations, threshold_lift

def test_hit():
    assert hit(251,250.5,'Over') and not hit(250,250.5,'Over')
    assert hit(3,3.5,'Under') and not hit(4,3.5,'Under')

def test_shrink():
    assert 1 < shrink_lift(1.4,50,200) < 1.4
    assert abs(shrink_lift(1.0,500,200)-1)<1e-12

def test_pearson():
    assert pearson([1,2,3],[2,4,6]) > .999

def test_same_team_pairing_and_primary_qb():
    rows=[
      {'season':'2024','week':'1','season_type':'REG','team':'AAA','opponent_team':'BBB','position':'QB','player_id':'q1','player_display_name':'Q1','attempts':'35','passing_yards':'300','passing_tds':'2','completions':'25'},
      {'season':'2024','week':'1','season_type':'REG','team':'AAA','opponent_team':'BBB','position':'QB','player_id':'q2','player_display_name':'Q2','attempts':'2','passing_yards':'10','passing_tds':'0','completions':'1'},
      {'season':'2024','week':'1','season_type':'REG','team':'AAA','opponent_team':'BBB','position':'WR','player_id':'w1','player_display_name':'W1','targets':'8','receptions':'6','receiving_yards':'90','receiving_tds':'1'},
      {'season':'2024','week':'1','season_type':'REG','team':'BBB','opponent_team':'AAA','position':'WR','player_id':'w2','player_display_name':'W2','targets':'8','receptions':'7','receiving_yards':'100','receiving_tds':'1'},
    ]
    obs=build_pair_observations(rows)
    assert len(obs)==1
    assert obs[0].qb_id=='q1' and obs[0].catcher_id=='w1' and obs[0].team=='AAA'
