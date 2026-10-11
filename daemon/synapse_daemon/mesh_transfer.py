"""Bounded, preview-first project copy primitives for Synapse Mesh."""
from __future__ import annotations
import hashlib
import os
import shutil
from pathlib import Path
from uuid import uuid4

EXCLUDED = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
MAX_FILES = 10000
MAX_BYTES = 512 * 1024 * 1024

def _files(root: Path) -> list[tuple[Path, Path]]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project directory required")
    entries=[]
    total=0
    for parent, dirs, names in os.walk(root, followlinks=False):
        current=Path(parent)
        if current.is_symlink():
            raise ValueError("Symlink directories are not supported")
        for item in tuple(dirs):
            if item in EXCLUDED:
                dirs.remove(item)
                continue
            if (current / item).is_symlink():
                raise ValueError("Symlink directories are not supported")
        for name in names:
            item=current/name
            if item.is_symlink():
                raise ValueError("Symlink files are not supported")
            if not item.is_file():
                continue
            rel=item.relative_to(root)
            total+=item.stat().st_size
            entries.append((item,rel))
            if len(entries)>MAX_FILES or total>MAX_BYTES:
                raise ValueError("Project exceeds transfer limits")
    return sorted(entries, key=lambda x:x[1].as_posix())

def preview_project_copy(source: Path) -> dict:
    files=_files(source)
    return {"files":len(files),"bytes":sum(p.stat().st_size for p,_ in files),
            "excluded_directories":sorted(EXCLUDED),
            "entries":[{"path":str(rel).replace("\\","/"),"bytes":p.stat().st_size}
                       for p,rel in files]}

def copy_project(source: Path, destination: Path, allowed_root: Path) -> dict:
    source=Path(source).resolve(strict=True)
    allowed_root=Path(allowed_root).resolve(strict=True)
    destination=Path(destination)
    # Resolve even for non-existent destinations; catches traversal and
    # symlinked parent directories before any write occurs.
    resolved=destination.resolve(strict=False)
    if resolved==allowed_root or allowed_root not in resolved.parents:
        raise ValueError("Destination must be inside the authorized home directory")
    if resolved.exists():
        raise FileExistsError("Destination already exists; choose a new directory")
    files=_files(source)
    stage=resolved.with_name(resolved.name + ".synapse-partial-" + uuid4().hex)
    if not stage.parent.exists():
        raise ValueError("Destination parent directory must already exist")
    copied=0
    bytes_written=0
    try:
        stage.mkdir()
        for original,rel in files:
            if original.is_symlink():
                raise ValueError("Source file changed to a symlink during transfer")
            output=stage/rel
            output.parent.mkdir(parents=True,exist_ok=True)
            h1=hashlib.sha256()
            with original.open("rb") as reader, output.open("xb") as writer:
                while chunk:=reader.read(1024*1024):
                    h1.update(chunk)
                    writer.write(chunk)
                    bytes_written+=len(chunk)
                    if bytes_written > MAX_BYTES:
                        raise ValueError("Project grew beyond transfer limits")
            h2=hashlib.sha256()
            with output.open("rb") as reader:
                while chunk:=reader.read(1024*1024):
                    h2.update(chunk)
            if h1.digest()!=h2.digest():
                raise IOError("Transferred file checksum mismatch")
            copied+=1
        stage.rename(resolved)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    return {"destination":str(resolved),"files":copied,"bytes":bytes_written,"verified":True}
