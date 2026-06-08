"""Project auto-discovery -- a multi-stack project detector.

Given any folder, ``detect_project()`` figures out:

  * Is this a project at all?
  * What stack is it (Node, Python, Rust, Go, .NET, Java, Ruby, PHP,
    Docker, static site, Make-driven, or a bare git repo)?
  * What command should launch it?

``scan_directory()`` walks a workspace root and returns every importable
project it finds, skipping the obvious noise (node_modules, venv, build
output, hidden + system folders).

Design goals (the user's brief: "make it work with legit any folder type"):
  * Marker-file driven -- each detector keys off concrete files.
  * Honest confidence -- a detector that read a real run-script reports high
    confidence; a bare git repo reports low and leaves the command blank.
  * Always offers candidates so the user can pick a different launch command.
  * Never executes anything -- pure filesystem reads.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

# ── data shapes ────────────────────────────────────────────────────────────


class LaunchCandidate(BaseModel):
    """One possible way to launch a project."""

    label: str                 # human label, e.g. "npm run dev"
    command: str               # the actual launch command
    note: str | None = None    # why this candidate / what it does


class DetectedProject(BaseModel):
    """A project discovery found on disk -- not yet registered."""

    path: str
    suggested_id: str          # kebab-case, from the folder name
    name: str                  # humanised folder name
    stack: str                 # 'node' | 'python' | 'python-django' | 'rust' | …
    framework: str | None = None
    suggested_launch_cmd: str | None = None
    suggested_port: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: list[LaunchCandidate] = Field(default_factory=list)
    icon: str | None = None
    description: str | None = None
    markers: list[str] = Field(default_factory=list)   # files that triggered detection
    # Classification (v0.1.19) -- string to stay compatible with the
    # ProjectKind enum without an import cycle. 'app' = default.
    kind: str = "app"
    already_registered: bool = False                   # set by the scan route, not the detector


# ── directory names we never descend into / never treat as projects ──────────

SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "venv", ".venv", "env", ".env", "__pycache__", ".git",
    ".hg", ".svn", "dist", "build", "out", "target", ".next", ".nuxt",
    ".cache", ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    "vendor", "bin", "obj", ".gradle", ".terraform", "site-packages",
    "AppData", "Application Data", "Local Settings", "$Recycle.Bin",
})

# Common dev-server ports per framework -- a guess the user can correct.
FRAMEWORK_PORTS: dict[str, int] = {
    "vite": 5173,
    "next": 3000,
    "react-scripts": 3000,
    "angular": 4200,
    "vue-cli": 8080,
    "nuxt": 3000,
    "astro": 4321,
    "svelte": 5173,
    "express": 3000,
    "nest": 3000,
    "django": 8000,
    "flask": 5000,
    "fastapi": 8000,
    "rails": 3000,
}


# ── helpers ────────────────────────────────────────────────────────────────


def _kebab(name: str) -> str:
    """Turn a folder name into a kebab-case id."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "project"


def _humanize(name: str) -> str:
    """Folder name -> a friendly display name."""

    cleaned = re.sub(r"[-_]+", " ", name).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else name


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_toml(path: Path) -> dict | None:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


# ── per-stack detectors ─────────────────────────────────────────────────────
# Each returns a DetectedProject or None. The first non-None wins as the
# "primary" detection; detectors are ordered most-specific first.


def _detect_node(path: Path, names: set[str]) -> DetectedProject | None:
    if "package.json" not in names:
        return None
    pkg = _read_json(path / "package.json") or {}
    scripts: dict[str, str] = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    framework = _node_framework(deps)
    candidates: list[LaunchCandidate] = []
    for script in scripts:
        cmd = "npm start" if script == "start" else f"npm run {script}"
        candidates.append(LaunchCandidate(label=cmd, command=cmd, note=f'package.json script "{script}"'))

    # Primary launch: prefer a dev/serve script, then start.
    primary = None
    for preferred in ("dev", "develop", "serve", "start"):
        if preferred in scripts:
            primary = "npm start" if preferred == "start" else f"npm run {preferred}"
            break

    confidence = 0.95 if primary else (0.7 if scripts else 0.55)
    return DetectedProject(
        path=str(path),
        suggested_id=_kebab(path.name),
        name=pkg.get("name") and _humanize(str(pkg["name"])) or _humanize(path.name),
        stack="node",
        framework=framework,
        suggested_launch_cmd=primary,
        suggested_port=FRAMEWORK_PORTS.get(framework or ""),
        confidence=confidence,
        candidates=candidates,
        icon="package",
        description=pkg.get("description") or (f"{framework} app" if framework else "Node.js project"),
        markers=["package.json"],
    )


def _node_framework(deps: dict) -> str | None:
    keys = {k.lower() for k in deps}
    if "next" in keys:
        return "next"
    if "vite" in keys:
        return "vite"
    if "react-scripts" in keys:
        return "react-scripts"
    if "@angular/core" in keys:
        return "angular"
    if "nuxt" in keys or "nuxt3" in keys:
        return "nuxt"
    if "astro" in keys:
        return "astro"
    if "svelte" in keys or "@sveltejs/kit" in keys:
        return "svelte"
    if "@nestjs/core" in keys:
        return "nest"
    if "express" in keys:
        return "express"
    if "electron" in keys:
        return "electron"
    if "vue" in keys:
        return "vue-cli"
    return None


_PY_ENTRY_FILES = ("main.py", "app.py", "run.py", "server.py", "__main__.py", "start.py", "bot.py")


def _detect_python(path: Path, names: set[str]) -> DetectedProject | None:
    py_markers = {"pyproject.toml", "requirements.txt", "setup.py", "pipfile", "manage.py"}
    has_py_marker = bool(names & py_markers)
    has_entry_file = any(entry in names for entry in _PY_ENTRY_FILES)
    # A folder with only loose .py library files (no marker, no entry point)
    # is not a launchable project -- don't flag it as discovery noise.
    if not has_py_marker and not has_entry_file:
        return None

    markers = sorted(names & py_markers) or ["entry .py file"]
    candidates: list[LaunchCandidate] = []
    framework: str | None = None
    primary: str | None = None
    stack = "python"

    # Django -- manage.py is unambiguous.
    if "manage.py" in names:
        framework = "django"
        stack = "python-django"
        primary = "python manage.py runserver"
        candidates.append(LaunchCandidate(label=primary, command=primary, note="Django dev server"))

    # pyproject.toml -- console scripts or framework deps.
    pyproject = _read_toml(path / "pyproject.toml") if "pyproject.toml" in names else None
    if pyproject:
        proj = pyproject.get("project", {})
        scripts = proj.get("scripts", {})
        if isinstance(scripts, dict):
            for script_name in scripts:
                cmd = script_name
                candidates.append(LaunchCandidate(label=cmd, command=cmd, note="pyproject console script"))
                primary = primary or cmd
        all_deps = " ".join(proj.get("dependencies", []) or []).lower()
        if "fastapi" in all_deps:
            framework = framework or "fastapi"
        elif "flask" in all_deps:
            framework = framework or "flask"

    # Common entry-point files.
    for entry in _PY_ENTRY_FILES:
        if entry in names:
            cmd = f"python {entry}"
            candidates.append(LaunchCandidate(label=cmd, command=cmd, note=f"runs {entry}"))
            primary = primary or cmd

    # A package with __main__.py -> python -m <pkg>.
    if "__main__.py" not in names:
        for child in path.iterdir() if path.is_dir() else []:
            if child.is_dir() and (child / "__main__.py").exists() and child.name not in SKIP_DIRS:
                cmd = f"python -m {child.name}"
                candidates.append(LaunchCandidate(label=cmd, command=cmd, note=f"runs the {child.name} package"))
                primary = primary or cmd
                break

    confidence = 0.95 if (framework or primary) else (0.6 if has_py_marker else 0.45)
    return DetectedProject(
        path=str(path),
        suggested_id=_kebab(path.name),
        name=_humanize(path.name),
        stack=stack,
        framework=framework,
        suggested_launch_cmd=primary,
        suggested_port=FRAMEWORK_PORTS.get(framework or ""),
        confidence=confidence,
        candidates=_dedupe(candidates),
        icon="python",
        description=f"{framework.capitalize()} app" if framework else "Python project",
        markers=markers,
    )


def _detect_rust(path: Path, names: set[str]) -> DetectedProject | None:
    if "cargo.toml" not in names:
        return None
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="rust", suggested_launch_cmd="cargo run", confidence=0.92,
        candidates=[
            LaunchCandidate(label="cargo run", command="cargo run", note="debug build"),
            LaunchCandidate(label="cargo run --release", command="cargo run --release", note="optimised build"),
        ],
        icon="cog", description="Rust project (Cargo)", markers=["Cargo.toml"],
    )


def _detect_go(path: Path, names: set[str]) -> DetectedProject | None:
    if "go.mod" not in names:
        return None
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="go", suggested_launch_cmd="go run .", confidence=0.9,
        candidates=[LaunchCandidate(label="go run .", command="go run .", note="run the module")],
        icon="cog", description="Go module", markers=["go.mod"],
    )


def _detect_dotnet(path: Path, names: set[str]) -> DetectedProject | None:
    has = any(n.endswith((".csproj", ".fsproj", ".sln")) for n in names)
    if not has:
        return None
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="dotnet", suggested_launch_cmd="dotnet run", confidence=0.88,
        candidates=[LaunchCandidate(label="dotnet run", command="dotnet run", note=".NET project")],
        icon="cog", description=".NET project", markers=["*.csproj / *.sln"],
    )


def _detect_java(path: Path, names: set[str]) -> DetectedProject | None:
    if "pom.xml" in names:
        cmd = "mvn spring-boot:run"
        return DetectedProject(
            path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
            stack="java-maven", suggested_launch_cmd=cmd, confidence=0.8,
            candidates=[
                LaunchCandidate(label=cmd, command=cmd, note="Spring Boot"),
                LaunchCandidate(label="mvn exec:java", command="mvn exec:java", note="generic main"),
            ],
            icon="cog", description="Java project (Maven)", markers=["pom.xml"],
        )
    if "build.gradle" in names or "build.gradle.kts" in names:
        cmd = "gradlew run" if "gradlew" in names else "gradle run"
        return DetectedProject(
            path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
            stack="java-gradle", suggested_launch_cmd=cmd, confidence=0.8,
            candidates=[LaunchCandidate(label=cmd, command=cmd, note="Gradle run task")],
            icon="cog", description="Java project (Gradle)", markers=["build.gradle"],
        )
    return None


def _detect_ruby(path: Path, names: set[str]) -> DetectedProject | None:
    if "gemfile" not in names:
        return None
    rails = (path / "config" / "application.rb").exists()
    cmd = "rails server" if rails else "bundle exec ruby main.rb"
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="ruby", framework="rails" if rails else None,
        suggested_launch_cmd=cmd, suggested_port=3000 if rails else None, confidence=0.8,
        candidates=[LaunchCandidate(label=cmd, command=cmd, note="Rails" if rails else "Ruby + Bundler")],
        icon="cog", description="Ruby on Rails app" if rails else "Ruby project", markers=["Gemfile"],
    )


def _detect_php(path: Path, names: set[str]) -> DetectedProject | None:
    if "composer.json" not in names and not any(n.endswith(".php") for n in names):
        return None
    cmd = "php -S localhost:8000"
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="php", suggested_launch_cmd=cmd, suggested_port=8000, confidence=0.7,
        candidates=[LaunchCandidate(label=cmd, command=cmd, note="PHP built-in server")],
        icon="cog", description="PHP project", markers=["composer.json"],
    )


def _detect_deno(path: Path, names: set[str]) -> DetectedProject | None:
    if "deno.json" not in names and "deno.jsonc" not in names:
        return None
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="deno", suggested_launch_cmd="deno task start", confidence=0.78,
        candidates=[
            LaunchCandidate(label="deno task start", command="deno task start", note="deno.json task"),
            LaunchCandidate(label="deno run -A main.ts", command="deno run -A main.ts", note="run main.ts"),
        ],
        icon="cog", description="Deno project", markers=["deno.json"],
    )


def _detect_docker(path: Path, names: set[str]) -> DetectedProject | None:
    compose = next((n for n in names if n in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}), None)
    if compose:
        return DetectedProject(
            path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
            stack="docker-compose", suggested_launch_cmd="docker compose up", confidence=0.82,
            candidates=[
                LaunchCandidate(label="docker compose up", command="docker compose up", note="foreground"),
                LaunchCandidate(label="docker compose up -d", command="docker compose up -d", note="detached"),
            ],
            icon="boxes", description="Docker Compose stack", markers=[compose],
        )
    return None


def _detect_make(path: Path, names: set[str]) -> DetectedProject | None:
    if "makefile" not in names:
        return None
    try:
        text = (path / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    targets = set(re.findall(r"(?m)^([a-zA-Z0-9_-]+):", text))
    runnable = [t for t in ("run", "dev", "start", "serve") if t in targets]
    if not runnable:
        return None
    primary = f"make {runnable[0]}"
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="make", suggested_launch_cmd=primary, confidence=0.65,
        candidates=[LaunchCandidate(label=f"make {t}", command=f"make {t}", note=f'Makefile "{t}" target') for t in runnable],
        icon="terminal", description="Makefile-driven project", markers=["Makefile"],
    )


def _detect_static(path: Path, names: set[str]) -> DetectedProject | None:
    if "index.html" not in names:
        return None
    cmd = "python -m http.server 8080"
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="static", suggested_launch_cmd=cmd, suggested_port=8080, confidence=0.55,
        candidates=[
            LaunchCandidate(label=cmd, command=cmd, note="serve with Python"),
            LaunchCandidate(label="npx serve", command="npx serve", note="serve with Node"),
        ],
        icon="globe", description="Static site", markers=["index.html"],
    )


def _detect_git_repo(path: Path, names: set[str]) -> DetectedProject | None:
    if ".git" not in names:
        return None
    return DetectedProject(
        path=str(path), suggested_id=_kebab(path.name), name=_humanize(path.name),
        stack="unknown", suggested_launch_cmd=None, confidence=0.3,
        candidates=[], icon="folder",
        description="Git repository — stack not recognised, set a launch command after importing.",
        markers=[".git"],
    )


# Order matters: most-specific first; the bare-git-repo catch-all is last.
_DETECTORS = (
    _detect_node,
    _detect_python,
    _detect_rust,
    _detect_go,
    _detect_dotnet,
    _detect_java,
    _detect_ruby,
    _detect_deno,
    _detect_docker,
    _detect_php,
    _detect_make,
    _detect_static,
    _detect_git_repo,
)


def _dedupe(candidates: list[LaunchCandidate]) -> list[LaunchCandidate]:
    seen: set[str] = set()
    out: list[LaunchCandidate] = []
    for c in candidates:
        if c.command not in seen:
            seen.add(c.command)
            out.append(c)
    return out


# ── public API ─────────────────────────────────────────────────────────────


def detect_project(path: Path) -> DetectedProject | None:
    """Inspect a single folder. Returns a DetectedProject, or None if the
    folder shows no sign of being a project."""

    if not path.is_dir():
        return None
    try:
        entries = list(path.iterdir())
    except OSError:
        return None

    # Lower-cased name set for case-insensitive marker matching (Windows).
    names = {e.name.lower() for e in entries}

    for detector in _DETECTORS:
        result = detector(path, names)
        if result is not None:
            result.kind = _classify(result, path, names)
            return result
    return None


# ── classification ─────────────────────────────────────────────────────────
# Maps a detection onto a `ProjectKind`-string so the Apps page can filter
# the grid (v0.1.19). The post-detection pass keeps the per-stack detectors
# small and lets the rules evolve without touching every detector.


_NODE_UI_FRAMEWORKS = {
    "vite", "next", "react-scripts", "angular", "nuxt", "astro", "svelte", "vue-cli",
}
_NODE_SERVICE_FRAMEWORKS = {"express", "nest"}
_PY_SERVICE_FRAMEWORKS = {"django", "flask", "fastapi"}


def _classify(detected: DetectedProject, path: Path, names: set[str]) -> str:
    stack = detected.stack
    framework = detected.framework

    if stack == "node":
        if _looks_like_node_mcp(path, names):
            return "mcp-server"
        if framework in _NODE_UI_FRAMEWORKS:
            return "ui"
        if framework in _NODE_SERVICE_FRAMEWORKS:
            return "service"
        return "app"

    if stack.startswith("python"):
        if _looks_like_python_mcp(path, names):
            return "mcp-server"
        if framework in _PY_SERVICE_FRAMEWORKS:
            return "service"
        cmd = detected.suggested_launch_cmd or ""
        # `python foo.py` with no framework = a one-shot script.
        if re.match(r"^python\s+\w+\.py$", cmd) and not framework:
            return "script"
        return "app"

    if stack == "static":
        return "ui"
    if stack == "docker-compose":
        return "service"
    if stack == "make":
        return "other"
    if stack == "unknown":
        return "library"  # bare git repo with no recognised stack

    # rust / go / dotnet / java-* / ruby / php / deno -> a generic launchable app.
    return "app"


def _looks_like_node_mcp(path: Path, names: set[str]) -> bool:
    """Detect a Node-based MCP server (file conventions + package.json hints)."""

    # File-based signal -- `mcp-server.js`, `mcp_server.ts`, `mcp.mjs`, …
    if any(re.fullmatch(r"mcp[-_]?server\.(js|ts|mjs|cjs)", n) for n in names):
        return True

    pkg = _read_json(path / "package.json") or {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if any("modelcontextprotocol" in k.lower() for k in deps):
        return True
    keywords = pkg.get("keywords") or []
    if any(
        isinstance(k, str) and ("mcp" == k.lower() or "model-context-protocol" in k.lower())
        for k in keywords
    ):
        return True
    scripts = pkg.get("scripts") or {}
    if isinstance(scripts, dict) and any("mcp" in name.lower() for name in scripts):
        return True
    bin_field = pkg.get("bin")
    if isinstance(bin_field, dict) and any("mcp" in name.lower() for name in bin_field):
        return True
    if isinstance(bin_field, str) and "mcp" in bin_field.lower():
        return True
    return False


def _looks_like_python_mcp(path: Path, names: set[str]) -> bool:
    """Detect a Python-based MCP server."""

    if any(re.fullmatch(r"mcp[-_]?server\.py", n) for n in names):
        return True
    for sub in ("mcp_server", "mcp"):
        if (path / sub / "__main__.py").exists():
            return True

    if "pyproject.toml" in names:
        pp = _read_toml(path / "pyproject.toml") or {}
        proj = pp.get("project", {}) if isinstance(pp.get("project"), dict) else {}
        deps_str = " ".join(proj.get("dependencies", []) or []).lower()
        if re.search(r"(?:^|[\s>=<])mcp(?:[\s>=<\[,]|$)", deps_str):
            return True
        if "modelcontextprotocol" in deps_str:
            return True
        name = str(proj.get("name", ""))
        if "mcp" in name.lower():
            return True
    return False


def scan_directory(root: Path, max_depth: int = 2) -> list[DetectedProject]:
    """Walk ``root`` looking for projects.

    Scans up to ``max_depth`` levels deep (1 = direct children only). Skips
    SKIP_DIRS and hidden folders. The root itself is also checked.
    """

    found: list[DetectedProject] = []
    seen_paths: set[str] = set()

    def _walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        # The root (depth 0) is a workspace container, not a project itself --
        # only fingerprint folders at depth >= 1.
        if depth >= 1:
            detected = detect_project(directory)
            if detected and detected.path not in seen_paths:
                seen_paths.add(detected.path)
                found.append(detected)
                # A recognised project is a leaf -- don't descend into it.
                if detected.stack != "unknown":
                    return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir())
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            _walk(child, depth + 1)

    _walk(root, 0)
    # Highest confidence first so the UI surfaces the best matches on top.
    found.sort(key=lambda d: (-d.confidence, d.name.lower()))
    return found
