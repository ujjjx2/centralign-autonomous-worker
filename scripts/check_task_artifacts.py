#!/usr/bin/env python3
"""Verify a real task produced a browser video/trace and readback evidence."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import Store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('task_id',help='UUID from Agent execution trace')
    args=parser.parse_args()
    settings=Settings()
    task=Store(settings.database_path).task(args.task_id)
    if task is None:
        print('No such task in this SQLite database; check DATABASE_PATH')
        return 2
    folder=settings.artifacts_dir/args.task_id
    result={
      'task_status':task['status'],
      'verified':bool((task.get('report') or {}).get('verification',{}).get('matched')),
      'browser_video':str(folder/'browser-recording.webm') if (folder/'browser-recording.webm').is_file() else None,
      'playwright_trace':str(folder/'playwright-trace-0.zip') if (folder/'playwright-trace-0.zip').is_file() else None,
      'verification_screenshot':str(folder/'verification.png') if (folder/'verification.png').is_file() else None,
      'verification_readback':str(folder/'verification.json') if (folder/'verification.json').is_file() else None,
    }
    print(json.dumps(result,indent=2))
    return 0 if result['verified'] and result['browser_video'] else 1

if __name__=='__main__':raise SystemExit(main())
