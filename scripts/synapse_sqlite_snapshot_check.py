"""Check that a live SQLite database can be backed up and validated in memory.

This produces no persistent file and prints no rows or credentials.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sqlite3
import json
import time

def snapshot_check(path:Path)->dict:
    if not path.is_file(): raise FileNotFoundError(path)
    start=time.monotonic()
    src=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    dst=sqlite3.connect(":memory:")
    try:
        src.backup(dst,pages=1000,sleep=0.05)
        result=dst.execute("PRAGMA quick_check(1)").fetchone()[0]
        if result!="ok":raise RuntimeError("Snapshot failed SQLite quick_check")
        objects=dst.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        return {"status":"validated_in_memory","source_size_bytes":path.stat().st_size,
          "sqlite_quick_check":result,"schema_object_count":objects,
          "seconds":round(time.monotonic()-start,2),
          "disk_backup_created":False,"data_modified":False}
    finally:
        dst.close()
        src.close()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    args=p.parse_args()
    print(json.dumps(snapshot_check(args.source),indent=2))

