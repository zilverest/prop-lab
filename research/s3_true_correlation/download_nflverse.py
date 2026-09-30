#!/usr/bin/env python3
"""Download nflverse weekly player stats for S3 research.

Run on a machine/GitHub runner with internet access. Uses only Python stdlib.
Documented URL pattern comes from nflreadr::load_player_stats().
"""
from pathlib import Path
from urllib.request import Request, urlopen
import argparse

URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"

def download(season:int, out:Path):
    url=URL.format(season=season)
    dest=out/f"stats_player_week_{season}.csv"
    if dest.exists() and dest.stat().st_size>1000:
        print("exists", dest); return
    print("downloading", url)
    req=Request(url, headers={"User-Agent":"prop-lab-s3-research/1.0"})
    with urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            f.write(chunk)
    print("saved", dest, dest.stat().st_size)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2021,2022,2023,2024,2025")
    ap.add_argument("--out", default="external_data")
    a=ap.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    for s in [int(x) for x in a.seasons.split(',') if x.strip()]: download(s,out)
if __name__=='__main__': main()
