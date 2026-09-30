#!/usr/bin/env python3
"""Audit legacy prop-lab stack slips before treating them as correlated.

This script never guesses team membership. It writes the game teams and marks the
pair as NEEDS_TEAM_JOIN until a player/team source confirms both players are on the
same team as the QB for that week.
"""
import csv, json, argparse
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo', required=True); ap.add_argument('--out', default='legacy_stack_audit.csv')
    a=ap.parse_args(); base=Path(a.repo)/'data'
    events={r['event_id']:r for r in csv.DictReader((base/'events.csv').open(encoding='utf-8'))}
    rows=[]
    with (base/'slips.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r.get('kind')!='sgp' or 'construct=stack' not in (r.get('note') or ''): continue
            legs=json.loads(r['legs'])
            e=events.get(str(r['event_id']),{})
            rows.append({
                'ts':r['ts'],'event_id':r['event_id'],'home':e.get('home',''),'away':e.get('away',''),
                'book':r['book'],'price':r['price'],'resolution':r['resolution'],'pnl':r['pnl_units'],
                'leg1_player':legs[0].get('player',''),'leg1_market':legs[0].get('market',''),'leg1_side':legs[0].get('side',''),'leg1_point':legs[0].get('point',''),
                'leg2_player':legs[1].get('player',''),'leg2_market':legs[1].get('market',''),'leg2_side':legs[1].get('side',''),'leg2_point':legs[1].get('point',''),
                'team_verification':'NEEDS_TEAM_JOIN','true_same_team_stack':'UNKNOWN'
            })
    fields=list(rows[0]) if rows else []
    with open(a.out,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f'wrote {len(rows)} legacy stack rows -> {a.out}')
if __name__=='__main__': main()
