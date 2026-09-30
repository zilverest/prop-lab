import pandas as pd, numpy as np, math, os
files=[f'/mnt/data/s3_user_data/stats_player_week_{y}.csv' for y in range(2021,2026)]
df=pd.concat([pd.read_csv(f) for f in files],ignore_index=True)
df=df[df.season_type.eq('REG')].copy()
# sort and prior rolling means per player for relevant stats + targets
df=df.sort_values(['player_id','season','week']).reset_index(drop=True)
stats=['attempts','completions','passing_yards','passing_tds','receptions','receiving_yards','receiving_tds','targets']
for col in stats:
    # trailing 6 games across seasons by player (shifted)
    df[f'prior_{col}']=df.groupby('player_id')[col].transform(lambda s:s.shift(1).rolling(6,min_periods=3).mean())
# eligibility primary QB per team-game: max attempts
qbs=df[(df.position=='QB') & (df.attempts>0)].copy()
qbs=qbs.sort_values(['game_id','team','attempts'],ascending=[True,True,False]).drop_duplicates(['game_id','team'])
# catchers same team-game positions WR TE RB, prior targets avg >=3
catch=df[df.position.isin(['WR','TE','RB'])].copy()
catch=catch[(catch.prior_targets>=3) & catch.prior_targets.notna()]
# join on game/team
pairs=qbs.merge(catch,on=['game_id','team','season','week','season_type','opponent_team'],suffixes=('_qb','_ca'))
# residuals
pairs['r_pass_yards']=pairs.passing_yards_qb-pairs.prior_passing_yards_qb
pairs['r_completions']=pairs.completions_qb-pairs.prior_completions_qb
pairs['r_attempts']=pairs.attempts_qb-pairs.prior_attempts_qb
pairs['r_pass_tds']=pairs.passing_tds_qb-pairs.prior_passing_tds_qb
pairs['r_rec_yards']=pairs.receiving_yards_ca-pairs.prior_receiving_yards_ca
pairs['r_receptions']=pairs.receptions_ca-pairs.prior_receptions_ca
pairs['r_rec_tds']=pairs.receiving_tds_ca-pairs.prior_receiving_tds_ca
archs=[
 ('PASS_YDS__REC_YDS','r_pass_yards','r_rec_yards'),
 ('PASS_YDS__RECEPTIONS','r_pass_yards','r_receptions'),
 ('COMPLETIONS__RECEPTIONS','r_completions','r_receptions'),
 ('ATTEMPTS__RECEPTIONS','r_attempts','r_receptions'),
 ('PASS_TD__REC_TD','r_pass_tds','r_rec_tds'),
 ('PASS_TD__RECEPTIONS','r_pass_tds','r_receptions'),
]
rows=[]
for pos in ['WR','TE','RB']:
 p0=pairs[pairs.position_ca==pos]
 for name,x,y in archs:
  for label,years in [('train',[2021,2022,2023,2024]),('val',[2025])]:
   z=p0[p0.season.isin(years)][[x,y]].dropna()
   n=len(z)
   corr=z[x].corr(z[y]) if n>2 else np.nan
   p1=(z[x]>0).mean();p2=(z[y]>0).mean();pj=((z[x]>0)&(z[y]>0)).mean();lift=pj/(p1*p2) if p1*p2 else np.nan
   pu1=(z[x]<0).mean();pu2=(z[y]<0).mean();puj=((z[x]<0)&(z[y]<0)).mean();ulift=puj/(pu1*pu2) if pu1*pu2 else np.nan
   rows.append([name,pos,label,n,corr,p1,p2,pj,lift,ulift])
r=pd.DataFrame(rows,columns=['archetype','pos','split','n','corr','pA_over','pB_over','joint_over','oo_lift','uu_lift'])
piv=r.pivot(index=['archetype','pos'],columns='split')
out=[]
for idx in piv.index:
 a={'archetype':idx[0],'pos':idx[1]}
 for met in ['n','corr','oo_lift','uu_lift']:
  a['train_'+met]=piv.loc[idx,(met,'train')];a['val_'+met]=piv.loc[idx,(met,'val')]
 # conservative rho: min positive corr train/val * .85 ; 0 if either nonpositive
 mn=min(a['train_corr'],a['val_corr']) if pd.notna(a['train_corr']) and pd.notna(a['val_corr']) else np.nan
 a['rho_cons']=max(0,mn*0.85) if pd.notna(mn) else np.nan
 out.append(a)
out=pd.DataFrame(out).sort_values(['archetype','pos'])
out.to_csv('/mnt/data/s3_priors_recomputed.csv',index=False)
print('pairs',len(pairs))
print(out.to_string(index=False,formatters={c:(lambda x:f'{x:.3f}') for c in out.columns if c not in ['archetype','pos','train_n','val_n']}))
