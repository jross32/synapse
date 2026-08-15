from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json

@dataclass
class Entry:
    at: str = ""          # ISO-8601 UTC, e.g. "2026-08-15T04:20:00Z"
    runtime: str = ""
    model: str = ""
    ok: bool = False
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    credits: float = 0.0
    requests: int = 0
    exhausted: str = ""   # non-empty if the runtime reported being out of room

@dataclass
class Rollup:
    runtime: str = ""
    calls: int = 0
    failures: int = 0
    seconds: float = 0.0
    total_tokens: int = 0
    cost_usd: float = 0.0
    credits: float = 0.0
    requests: int = 0
    last_exhausted_at: str = ""   # "" if never

def record(entry: Entry, *, path: Path) -> None:
    # Ensure parent directories exist
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Serialize entry to a single line JSON
    line = json.dumps(asdict(entry)) + "\n"
    
    # Open in append mode and write a single line ending in "\n"
    # Append mode ensures concurrent appends on modern OSes are handled gracefully.
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)

def read_entries(path: Path, *, since: str = "") -> list[Entry]:
    if not path.is_file():
        return []
    
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if not isinstance(d, dict):
                        continue
                    
                    # Robust type conversion and defaults to tolerate malformed lines
                    entry = Entry(
                        at=str(d.get("at", "")),
                        runtime=str(d.get("runtime", "")),
                        model=str(d.get("model", "")),
                        ok=bool(d.get("ok", False)),
                        seconds=float(d.get("seconds", 0.0)),
                        input_tokens=int(d.get("input_tokens", 0)),
                        output_tokens=int(d.get("output_tokens", 0)),
                        total_tokens=int(d.get("total_tokens", 0)),
                        cost_usd=float(d.get("cost_usd", 0.0)),
                        credits=float(d.get("credits", 0.0)),
                        requests=int(d.get("requests", 0)),
                        exhausted=str(d.get("exhausted", ""))
                    )
                    
                    if since and entry.at < since:
                        continue
                        
                    entries.append(entry)
                except Exception:
                    # Skip malformed/truncated lines
                    continue
    except Exception:
        # A missing file or error opening file should return what we got or []
        pass
    return entries

def rollup(path: Path, *, since: str = "") -> dict[str, Rollup]:
    entries = read_entries(path, since=since)
    results = {}
    for entry in entries:
        rt = entry.runtime
        if rt not in results:
            results[rt] = Rollup(runtime=rt)
        
        r = results[rt]
        r.calls += 1
        if not entry.ok:
            r.failures += 1
        r.seconds += entry.seconds
        r.total_tokens += entry.total_tokens
        r.cost_usd += entry.cost_usd
        r.credits += entry.credits
        r.requests += entry.requests
        
        if entry.exhausted:
            if not r.last_exhausted_at or entry.at > r.last_exhausted_at:
                r.last_exhausted_at = entry.at
                
    return results

def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

if __name__ == '__main__':
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "test_ledger.jsonl"
        
        # Test 1: Write entries
        e1 = Entry(
            at="2026-08-15T04:20:00Z",
            runtime="gemini",
            model="gemini-1.5-pro",
            ok=True,
            seconds=2.5,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            requests=1
        )
        e2 = Entry(
            at="2026-08-15T04:25:00Z",
            runtime="gemini",
            model="gemini-1.5-pro",
            ok=False,
            seconds=1.2,
            input_tokens=50,
            output_tokens=0,
            total_tokens=50,
            cost_usd=0.0002,
            requests=1,
            exhausted="rate_limit"
        )
        e3 = Entry(
            at="2026-08-14T23:59:00Z",
            runtime="claude",
            model="claude-3-5-sonnet",
            ok=True,
            seconds=3.0,
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            cost_usd=0.0045,
            requests=1
        )
        
        # record them
        record(e1, path=tmp_path)
        record(e2, path=tmp_path)
        record(e3, path=tmp_path)
        
        # Test 2: read_entries
        entries = read_entries(tmp_path)
        assert len(entries) == 3
        assert entries[0].runtime == "gemini"
        assert entries[1].ok is False
        assert entries[2].runtime == "claude"
        
        # Test 3: read_entries with since filter
        # Since "2026-08-15T00:00:00Z"
        since_entries = read_entries(tmp_path, since="2026-08-15T00:00:00Z")
        assert len(since_entries) == 2
        assert all(e.at >= "2026-08-15T00:00:00Z" for e in since_entries)
        
        # Test 4: robust handling of malformed/truncated lines
        # Let's append a valid line, a malformed line, and another valid line
        with open(tmp_path, "a", encoding="utf-8") as f:
            f.write("{invalid json\n")
            f.write(json.dumps({"at": "2026-08-15T04:30:00Z", "runtime": "gemini", "ok": True}) + "\n")
            
        entries_after_malformed = read_entries(tmp_path)
        # Should be 3 + 1 = 4 entries (skipping the "{invalid json" line)
        assert len(entries_after_malformed) == 4
        assert entries_after_malformed[3].at == "2026-08-15T04:30:00Z"
        
        # Test 5: rollup
        rollups = rollup(tmp_path, since="2026-08-15T00:00:00Z")
        assert len(rollups) == 1  # Only "gemini" entries are >= 2026-08-15T00:00:00Z
        gemini_rollup = rollups["gemini"]
        assert gemini_rollup.calls == 3  # e1, e2, and the manual one
        assert gemini_rollup.failures == 1  # e2 is False
        assert gemini_rollup.last_exhausted_at == "2026-08-15T04:25:00Z"
        
        # Rollup everything
        all_rollups = rollup(tmp_path)
        assert len(all_rollups) == 2  # claude and gemini
        assert all_rollups["claude"].calls == 1
        assert all_rollups["claude"].failures == 0
        
        # Test 6: today_utc
        t = today_utc()
        assert len(t) == 10
        assert t[4] == '-' and t[7] == '-'
        
        print("All runtime_ledger tests passed successfully!")
