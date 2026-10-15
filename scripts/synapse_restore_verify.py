"""Offline, non-destructive integrity check and isolated restore of a backup bundle.

A bundle contains manifest.json and payload/<relative path>. No credential
material is printed. Keep real bundles encrypted at rest outside this tool.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import zipfile
MAX_ARCHIVE_BYTES=4*1024**3
MAX_EXTRACTED_BYTES=8*1024**3
MAX_FILE_BYTES=2*1024**3
MAX_FILES=20000
MAX_MANIFEST_BYTES=8*1024**2
MAX_RATIO=200

def checked_relative(name:str):
    p=PurePosixPath(name)
    if name in ('.','..') or not name or "\\" in name or ":" in name or p.is_absolute() or any(x in ("","..",".") for x in p.parts):
        raise ValueError("Unsafe archive path")
    return p

def validate_and_restore(bundle:Path,destination:Path,*,apply:bool=False):
    bundle=Path(bundle)
    destination=Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Restore target must not exist (never overwrite existing data).")
    if bundle.stat().st_size>MAX_ARCHIVE_BYTES: raise ValueError("Archive size limit exceeded")
    with zipfile.ZipFile(bundle) as z:
        infos=z.infolist()
        if len(infos)>MAX_FILES+1: raise ValueError("Archive entry count limit exceeded")
        if sum(i.file_size for i in infos)>MAX_EXTRACTED_BYTES+MAX_MANIFEST_BYTES: raise ValueError("Archive extraction size limit exceeded")
        for i in infos:
            if i.is_dir(): raise ValueError("Directory entries unsupported")
            if i.file_size>(MAX_MANIFEST_BYTES if i.filename=="manifest.json" else MAX_FILE_BYTES):
                raise ValueError("Archive member size limit exceeded")
            if i.file_size>MAX_RATIO*max(1,i.compress_size):
                raise ValueError("Compression ratio limit exceeded")
            if (i.external_attr>>16)&0o170000==0o120000:
                raise ValueError("Symlink entry unsupported")
        names=z.namelist()
        if len(names)!=len(set(names)) or "manifest.json" not in names:
            raise ValueError("Duplicate entries or missing manifest")
        for name in names:checked_relative(name)
        manifest=json.loads(z.read("manifest.json"))
        if manifest.get("schema")!=1 or not isinstance(manifest.get("files"),list):
            raise ValueError("Unsupported manifest")
        if len(manifest["files"])>MAX_FILES: raise ValueError("Manifest file count limit exceeded")
        seen=set()
        cumulative=0
        verified=[]
        for item in manifest["files"]:
            rel=checked_relative(item["path"])
            if rel.as_posix() in seen:raise ValueError("Duplicate source path")
            seen.add(rel.as_posix())
            member="payload/"+rel.as_posix()
            size=item.get("bytes")
            if type(size) is not int or size<0 or size>MAX_FILE_BYTES: raise ValueError("Manifest file size limit exceeded")
            cumulative+=size
            if cumulative>MAX_EXTRACTED_BYTES: raise ValueError("Manifest extraction size limit exceeded")
            if member not in names:raise ValueError("Missing content")
            if z.getinfo(member).file_size!=size: raise ValueError("Archive size disagrees with manifest")
            digest=hashlib.sha256()
            length=0
            with z.open(member) as stream:
                for block in iter(lambda:stream.read(1024*1024),b""):
                    digest.update(block);length+=len(block)
            if digest.hexdigest()!=item["sha256"] or length!=item["bytes"]:
                raise ValueError("Backup checksum or byte count mismatch")
            verified.append((rel,member))
        if set(names)!={"manifest.json",*(member for _,member in verified)}: raise ValueError("Unexpected archive entries")
        if apply:
            destination.mkdir(parents=True,exist_ok=False)
            for rel,member in verified:
                target=destination.joinpath(*rel.parts)
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(member) as stream,target.open("xb") as out:
                    for block in iter(lambda:stream.read(1024*1024),b""):
                        out.write(block)
            for rel,member in verified:
                if rel.suffix.lower() not in {".sqlite",".sqlite3",".db"}:continue
                restored=destination.joinpath(*rel.parts)
                try:
                    conn=sqlite3.connect("file:"+restored.as_posix()+"?mode=ro",uri=True)
                    try:
                        integrity=conn.execute("PRAGMA integrity_check").fetchone()[0]
                        if integrity!="ok":raise RuntimeError("SQLite integrity check failed")
                    finally:conn.close()
                except sqlite3.DatabaseError as exc:
                    raise RuntimeError("SQLite restore failed validation") from exc
    return {"files_verified":len(verified),"restored":apply,"target":str(destination)}

def make_test_bundle(files:dict[str,bytes],bundle:Path):
    """Only for test fixtures, not for live secret-bearing backups."""
    records=[]
    with zipfile.ZipFile(bundle,"x",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():
            checked_relative(name)
            z.writestr("payload/"+name,data)
            records.append({"path":name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
        z.writestr("manifest.json",json.dumps({"schema":1,"files":records}))
    return bundle

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: python synapse_restore_verify.py BUNDLE DESTINATION (verification only)")
    print(json.dumps(validate_and_restore(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))

