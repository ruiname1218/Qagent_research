"""Restore the published common initial records for fresh repair generation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qagent.core import ROOT,dump

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--run',default='published_initial'); a=p.parse_args()
    if not a.run or Path(a.run).name!=a.run or a.run in ('.','..'):p.error('run must be a simple name')
    dest=ROOT/'runs'/a.run
    if dest.exists():p.error('run already exists')
    rows=json.loads((ROOT/'results/oneshot.json').read_text())
    for row in rows:
        dump(dest/row['key']/'attempt_1/record.json',row['records'][0]);dump(dest/row['key']/'result.json',row)
    dump(dest/'config.json',{'source':'results/oneshot.json','kind':'restored published initial'})
    print(f'Restored {len(rows)} initial records to runs/{a.run}')

if __name__=='__main__':main()
