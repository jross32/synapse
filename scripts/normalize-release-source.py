"""Prepare release source normalization. Default is read-only; --apply after all writers freeze."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (".github", "daemon", "electron", "renderer", "scripts", "installer", "tools",
                "templates", "mobile", "ai_os", "assets", "cloud", "docs", "download-site")
ROOT_FILES = {".gitattributes", ".gitignore", ".editorconfig", "AGENTS.md", "README.md",
              "CHANGELOG.md", "PROGRESS.md", "package.json", "package-lock.json", "pyproject.toml",
              "vite.config.ts", "tsconfig.json", "tailwind.config.ts", "postcss.config.js", "synapse.cmd"}
TEXT_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx", ".json", ".jsonl",
                 ".yaml", ".yml", ".toml", ".md", ".txt", ".html", ".css", ".svg", ".xml", ".ps1",
                 ".sh", ".nsh", ".nsi", ".bat", ".cmd"}
SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", ".tmp", "data", "dist", "dist-electron",
             "release", "release-premium-shell", "build", "build-temp", "daemon-dist", "payload",
             "screenshots", "logs", "test-results", "coverage", "__pycache__", ".pytest_cache",
             ".ruff_cache", ".mypy_cache", ".cache"}
SKIP_NAMES = {"build-source.json", "build-source-start.json", "publication-receipt.json", "payload-manifest.json", "auth-token", "index-screenshot.png", "preview-chatgpt-screenshot.png"}
def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode("utf-8")
def allowed(relative):
    p=Path(relative); parts=p.parts
    if any(part in SKIP_DIRS or part.startswith(".tmp") or part.startswith("release-") for part in parts[:-1]):
        return False
    if p.name in SKIP_NAMES or p.name.startswith(".env") or p.name.endswith(".local.json"):
        return False
    if any(part.lower() in {"secrets", "publisher"} for part in parts): return False
    return relative in ROOT_FILES or (parts[0] in SOURCE_ROOTS and not p.name.startswith(".synapse-brief"))
def paths():
    result=set(ROOT_FILES)
    for folder in SOURCE_ROOTS:
        base=ROOT/folder
        if not base.exists() or base.is_symlink() or os.path.isjunction(base): continue
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:]=[name for name in dirs if name not in SKIP_DIRS and not name.startswith(".tmp")
                     and not name.startswith("release-") and not os.path.isjunction(Path(current)/name)
                     and not (Path(current)/name).is_symlink()]
            for name in files:
                file=Path(current)/name; rel=file.relative_to(ROOT).as_posix()
                if allowed(rel): result.add(rel)
    return sorted(result)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Explicitly normalize after writers stop")
    parser.add_argument("--output", default=".tmp/release-source-plan.json")
    options=parser.parse_args()
    changes=[]
    for rel in paths():
        file=ROOT/rel
        if not file.is_file() or file.is_symlink(): continue
        if file.suffix.lower() not in TEXT_SUFFIXES and file.name not in ROOT_FILES|{"Dockerfile"}: continue
        original=file.read_bytes()
        if b"\0" in original: continue
        try: original.decode("utf-8-sig")
        except UnicodeDecodeError: continue
        normalized=original.replace(b"\r\n",b"\n")
        if file.suffix.lower() in {".bat",".cmd"}: normalized=normalized.replace(b"\n",b"\r\n")
        if normalized != original:
            changes.append({"path":rel,"before_sha256":hashlib.sha256(original).hexdigest(),
                            "after_sha256":hashlib.sha256(normalized).hexdigest()})
            if options.apply: file.write_bytes(normalized)
    # Propose a deliberate source set; never stage or commit automatically.
    tracked=git("diff","--ignore-space-at-eol","--name-only","-z").split("\0")
    untracked=git("ls-files","--others","--exclude-standard","-z").split("\0")
    generated_site={"premium-desktop.png","premium-mobile.png","premium-tablet.png","safari-iphone.png",
                    "test-desktop.png","test-iphone.png","test-small-iphone.png","test-tablet.png",
                    "premium-rebuild-report.md","premium-brief.txt"}
    commit=sorted({rel for rel in tracked+untracked if rel and allowed(rel)
                  and not (rel.startswith("download-site/") and Path(rel).name in generated_site)})
    output=ROOT/options.output; output.parent.mkdir(parents=True,exist_ok=True)
    report={"schema":"synapse.source-normalization-plan/v1","applied":options.apply,
            "source_root":str(ROOT),"normalization_count":len(changes),"normalization":changes,
            "meaningful_tracked_count":len([rel for rel in tracked if rel]),
            "proposed_commit_paths":commit,"excluded_untracked":[rel for rel in untracked if rel and rel not in commit]}
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (output.parent/"release-source-commit-paths.txt").write_text("\n".join(commit)+"\n",encoding="utf-8")
    print(json.dumps({"applied":options.apply,"normalization_count":len(changes),
                      "meaningful_tracked_count":report["meaningful_tracked_count"],
                      "proposed_commit_count":len(commit),"report":str(output)}))
if __name__=="__main__": main()
