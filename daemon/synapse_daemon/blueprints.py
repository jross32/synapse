"""Blueprints: verified recipes for building things, of any kind.

A blueprint is not a template. A template is text you paste; a blueprint carries the pieces
to build, the contracts they must satisfy, the checks that prove they work, and the evidence
that it produced something good last time it ran. That evidence is what makes it safe to hand
to a local model unattended.

**Kind is deliberately open.** The first one is a web app, because that is the shape with a
frozen spec and two prior builds to measure against - but nothing here assumes UI. A blueprint
can be a backend service, a data pipeline, a character animation rig, a string-handling
library, a CI workflow. What differs between kinds is which *checks* apply, and checks are
data, so a new kind needs no new code.

**Composition is the point of the taxonomy.** Each blueprint declares what it ``provides`` and
what it ``requires``. With a hundred of them, "which of these fit together" stops being
something a human remembers and becomes a query: an auth backend that provides ``http-api``
and ``user-identity`` satisfies a dashboard UI that requires them. ``compatible_with`` computes
that, so an AI can assemble a stack instead of being told one.

**Scores are per-blueprint and comparable.** Every run records what it achieved against that
kind's rubric, so a blueprint's quality is a measurement in its manifest rather than a claim
in its description.
"""

from __future__ import annotations

import json
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .runtime_paths import repo_root


class BlueprintKind(str, Enum):
    """What sort of thing this builds. Determines which checks apply, nothing else."""

    WEB_APP = "web-app"
    BACKEND = "backend"
    UI_COMPONENT = "ui-component"
    DATA = "data"
    ANIMATION = "animation"
    LIBRARY = "library"
    INTEGRATION = "integration"
    INFRA = "infra"
    AGENT = "agent"
    OTHER = "other"


class CheckKind(str, Enum):
    """How a piece is proven. Each maps to a runner; adding one is additive."""

    UNIT = "unit"                  # execute a test file
    CONTRACT = "contract"          # signatures match the declaration
    WEB = "web"                    # render it, attack it (scaffold.webcheck)
    HTTP = "http"                  # drive the API and assert status codes
    STATIC = "static"              # grep/AST assertions over the source
    DESKTOP = "desktop"            # Reflex: launch it, screenshot it, assert on the window
    PERF = "perf"                  # stay inside a time or size budget


class Piece(BaseModel):
    """One independently-generated, independently-verified unit of work."""

    name: str
    spec: str
    module: str = ""
    contract: dict[str, Any] = Field(default_factory=dict)
    tests: str = ""
    checks: list[CheckKind] = Field(default_factory=lambda: [CheckKind.UNIT])
    depends_on: list[str] = Field(default_factory=list)
    suggested_skill: str = "coding"
    """Which measured skill this piece needs, so the router picks a seat on evidence."""


class BlueprintScore(BaseModel):
    """What this blueprint achieved last time it was built and graded."""

    total: float = 0.0
    max: float = 0.0
    percent: float = 0.0
    categories: dict[str, float] = Field(default_factory=dict)
    measured_at: str = ""
    local_tokens: int = 0
    claude_tokens: int = 0
    seconds: float = 0.0
    escalations: list[str] = Field(default_factory=list)

    @property
    def grade(self) -> str:
        p = self.percent
        return ("A" if p >= 90 else "B" if p >= 80 else "C" if p >= 70
                else "D" if p >= 60 else "F")


class Blueprint(BaseModel):
    id: str
    name: str
    kind: BlueprintKind = BlueprintKind.OTHER
    summary: str = ""
    what_you_get: list[str] = Field(default_factory=list)
    guarantees: list[str] = Field(default_factory=list)
    """Promises the checks actually enforce. Not marketing - each maps to a check."""

    tags: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    est_minutes: int = 0

    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    """Capability names, e.g. 'http-api', 'user-identity', 'sqlite-store'. The vocabulary is
    intentionally loose: a shared string is enough to make composition queryable, and a rigid
    ontology would be wrong before the tenth blueprint."""

    vocabulary: dict[str, str] = Field(default_factory=dict)
    """Domain nouns the recipe is written in terms of, e.g. ``{"record": "trail"}``.

    A blueprint describes a *shape* - sign up, sign in, keep a list of things that belong to
    you. The things have names, and hardcoding them makes the recipe single-use. Written as
    ``{{record}}`` placeholders through the specs, contracts, scenarios and entrypoint, and
    substituted at build time, so one blueprint builds a trail log or an expense tracker
    without being edited.

    This was not a hypothetical: `webapp-auth-crud` was written around ``record``/``title``/
    ``amount`` while the benchmark it exists to be measured against froze a spec using
    ``trail``/``name``/``distance_km``. The two builds could not be compared, and the
    difference had nothing to do with the quality of either.
    """

    pieces: list[Piece] = Field(default_factory=list)
    entrypoint: dict[str, Any] = Field(default_factory=dict)
    """How to run the assembled result, so the web checks have something to attack.

    Data, not code, for the same reason everything else here is: a new blueprint should need
    no changes to the runner. Recognised keys:

    ``source``   literal text written to the workspace once the pieces are built
    ``path``     where to write it (default ``app.py``)
    ``port``     the port to serve on
    ``health``   a path that answers 200 when the app is up (default ``/``)
    ``pages``    paths to render and check
    ``flow``     the signup-then-create flow the hostile-input probe drives

    Without this the render-and-attack pass cannot run at all, which is how the first build
    of ``webapp-auth-crud`` reported `checks={}` on both of its web-facing pieces.
    """

    assets: dict[str, str] = Field(default_factory=dict)
    preview: list[str] = Field(default_factory=list)
    score: BlueprintScore | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    source: str = "builtin"
    draft: bool = False
    """Distilled blueprints start as drafts: machine-derived, not yet human-approved."""

    def instantiate(self, overrides: dict[str, str] | None = None) -> "Blueprint":
        """A copy of this recipe rewritten in a particular domain's nouns.

        Substitution is textual and total: every ``{{term}}`` anywhere in the pieces or the
        entrypoint is replaced, so the spec a model reads, the contract it is held to, the
        scenario that judges it and the flow that attacks the result all say the same word.
        Rewriting only some of them is how a module and its caller come to disagree, which
        is the failure this whole area exists to prevent.
        """
        terms = {**self.vocabulary, **(overrides or {})}
        if not terms:
            return self.model_copy(deep=True)

        def sub(value: Any) -> Any:
            if isinstance(value, str):
                for key, word in terms.items():
                    value = value.replace("{{" + key + "}}", word)
                return value
            if isinstance(value, list):
                return [sub(v) for v in value]
            if isinstance(value, dict):
                return {sub(k): sub(v) for k, v in value.items()}
            return value

        clone = self.model_copy(deep=True)
        clone.vocabulary = terms
        clone.entrypoint = sub(clone.entrypoint)
        for piece in clone.pieces:
            piece.spec = sub(piece.spec)
            piece.tests = sub(piece.tests)
            piece.contract = sub(piece.contract)
        return clone

    def satisfies(self, capability: str) -> bool:
        return capability in self.provides

    def missing_requirements(self, available: set[str]) -> list[str]:
        return [r for r in self.requires if r not in available]


# ---------------------------------------------------------------- catalog


def blueprints_dir() -> Path:
    return repo_root() / "blueprints"


def _load_file(path: Path) -> Blueprint | None:
    try:
        return Blueprint.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- one malformed manifest must not hide the rest
        return None


def load_catalog(extra_dirs: list[Path] | None = None) -> list[Blueprint]:
    """Every blueprint on disk. Built-ins plus anything registered later."""
    found: dict[str, Blueprint] = {}
    roots = [blueprints_dir()] + list(extra_dirs or [])
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/blueprint.json")):
            bp = _load_file(path)
            if bp:
                found[bp.id] = bp
    return sorted(found.values(), key=lambda b: (b.kind.value, b.name))


def get_blueprint(blueprint_id: str) -> Blueprint | None:
    return next((b for b in load_catalog() if b.id == blueprint_id), None)


def save_blueprint(bp: Blueprint, *, root: Path | None = None) -> Path:
    target = (root or blueprints_dir()) / bp.id
    target.mkdir(parents=True, exist_ok=True)
    path = target / "blueprint.json"
    path.write_text(bp.model_dump_json(indent=1), encoding="utf-8")
    return path


def record_score(blueprint_id: str, score: BlueprintScore) -> Blueprint | None:
    """Store what a build actually achieved, so quality is measured rather than claimed."""
    bp = get_blueprint(blueprint_id)
    if bp is None:
        return None
    bp.score = score
    bp.provenance = {**bp.provenance, "last_built": score.measured_at or time.strftime("%Y-%m-%dT%H:%M:%S")}
    save_blueprint(bp)
    return bp


# ---------------------------------------------------------------- composition


def compatible_with(blueprint_id: str, catalog: list[Blueprint] | None = None) -> dict[str, list[str]]:
    """Which blueprints fit with this one, and in which direction.

    The question a library of a hundred blueprints has to answer. Rather than a human
    remembering that the auth backend pairs with the dashboard UI, both declare capabilities
    and the pairing falls out.
    """
    catalog = catalog or load_catalog()
    me = next((b for b in catalog if b.id == blueprint_id), None)
    if me is None:
        return {"satisfies_my_needs": [], "i_satisfy": [], "universal": []}

    satisfies_mine = [b.id for b in catalog
                      if b.id != me.id and any(b.satisfies(r) for r in me.requires)]
    i_satisfy = [b.id for b in catalog
                 if b.id != me.id and any(me.satisfies(r) for r in b.requires)]
    # A blueprint that needs nothing composes with anything - worth surfacing, since those
    # are the safe building blocks in a large library.
    universal = [b.id for b in catalog if b.id != me.id and not b.requires]
    return {"satisfies_my_needs": sorted(satisfies_mine),
            "i_satisfy": sorted(i_satisfy),
            "universal": sorted(universal)}


def resolve_stack(wanted: list[str], catalog: list[Blueprint] | None = None) -> dict[str, Any]:
    """Assemble a set of blueprints whose requirements are all met.

    Returns what it selected and, honestly, what is still missing - an unmet requirement is
    reported rather than silently dropped, because a stack that looks complete and isn't is
    the expensive kind of wrong.
    """
    catalog = catalog or load_catalog()
    by_id = {b.id: b for b in catalog}
    selected: list[Blueprint] = [by_id[i] for i in wanted if i in by_id]
    unknown = [i for i in wanted if i not in by_id]

    available = {cap for b in selected for cap in b.provides}
    added = True
    while added:
        added = False
        for bp in selected[:]:
            for need in bp.missing_requirements(available):
                provider = next((b for b in catalog
                                 if b.satisfies(need) and b not in selected), None)
                if provider:
                    selected.append(provider)
                    available |= set(provider.provides)
                    added = True

    unmet = sorted({need for b in selected for need in b.missing_requirements(available)})
    return {"selected": [b.id for b in selected], "unknown": unknown,
            "provides": sorted(available), "unmet_requirements": unmet,
            "complete": not unmet and not unknown}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "blueprint"


def summarize_for_ai() -> dict[str, Any]:
    """The catalog as an AI needs it: what exists, what it guarantees, how good it is."""
    catalog = load_catalog()
    return {
        "count": len(catalog),
        "how_to_use": ("GET /api/v1/blueprints to list, POST /api/v1/blueprints/{id}/build to "
                       "run one. Each declares what it provides and requires, so "
                       "GET /api/v1/blueprints/{id}/compatible assembles a stack."),
        "kinds": sorted({b.kind.value for b in catalog}),
        "blueprints": [
            {"id": b.id, "name": b.name, "kind": b.kind.value, "summary": b.summary,
             "guarantees": b.guarantees, "provides": b.provides, "requires": b.requires,
             "score": (b.score.percent if b.score else None),
             "grade": (b.score.grade if b.score else None),
             "draft": b.draft}
            for b in catalog
        ],
    }
