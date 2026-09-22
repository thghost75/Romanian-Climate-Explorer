"""Vercel build: verified data -> current dashboard snapshot -> production assets."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.fetch_snapshot import fetch
from scripts.export_dashboard import export
from scripts.prepare_runtime import prepare

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--local',action='store_true',help='Use existing local data without fetching the published snapshot')
    args=parser.parse_args()
    if not args.local:fetch()
    export()
    prepare()
    subprocess.run(['npm.cmd' if os.name=='nt' else 'npm','--prefix','frontend','run','build'],cwd=PROJECT,check=True)

if __name__=='__main__':main()
