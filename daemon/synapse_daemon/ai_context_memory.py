"""Shared project AI memory + squad prompt synthesis helpers.

The Sessions-centric squads feature reuses ADR-0006's per-project memory file:

    <data_dir>/projects/<project_id>/.synapse-ai-context.md

Work-item handoffs append structured notes into that file, and every squad
launch gets a synthesized prompt file plus env vars pointing back to it.
"""

from __future__ import annotations

from pathlib import Path

from .time_utils import to_iso, utc_now

AI_CONTEXT_FILENAME = ".synapse-ai-context.md"
AI_CONTEXT_ARCHIVE_PREFIX = ".synapse-ai-context.archive"
ROLE_PROMPTS_DIRNAME = "agent-prompts"
AI_CONTEXT_ROTATE_BYTES = 64 * 1024
AI_CONTEXT_DIRECTION_PROMPT = (
    "There's a shared Synapse project memory file at $SYNAPSE_AI_CONTEXT. "
    "Read it before you begin, and update it through a handoff when you finish."
)


def project_root(data_dir: Path, project_id: str) -> Path:
    return data_dir / "projects" / project_id


def ai_context_path(data_dir: Path, project_id: str) -> Path:
    return project_root(data_dir, project_id) / AI_CONTEXT_FILENAME


def role_prompt_dir(data_dir: Path, project_id: str) -> Path:
    return project_root(data_dir, project_id) / ROLE_PROMPTS_DIRNAME


def ensure_ai_context_file(data_dir: Path, project_id: str, project_name: str) -> Path:
    path = ai_context_path(data_dir, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    f"# Project: {project_name}",
                    "",
                    "## Direction",
                    "Shared context for Synapse AI squads and workbench sessions.",
                    "",
                    "## Active objectives",
                    "- [ ] Add the next objective or handoff here",
                    "",
                    "## Session log (newest first)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return path


def ai_context_metadata(data_dir: Path, project_id: str) -> dict[str, object]:
    path = ai_context_path(data_dir, project_id)
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "last_modified": None,
        }
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "last_modified": to_iso(utc_now() if stat.st_mtime_ns <= 0 else _from_timestamp(stat.st_mtime)),
    }


def append_work_item_handoff(
    *,
    data_dir: Path,
    project_id: str,
    project_name: str,
    squad_name: str,
    work_item_title: str,
    role_name: str | None,
    summary_md: str,
    blockers_md: str | None,
    files_touched: list[str],
    suggested_next_role: str | None,
) -> Path:
    path = ensure_ai_context_file(data_dir, project_id, project_name)
    _rotate_if_needed(path)

    heading = f"### {utc_now().date().isoformat()} · {role_name or 'agent'} · {squad_name}"
    lines = [
        "",
        heading,
        f"**Work item:** {work_item_title}",
        "",
        summary_md.strip() or "_No summary supplied._",
    ]
    if blockers_md and blockers_md.strip():
        lines.extend(["", "**Blockers**", blockers_md.strip()])
    if files_touched:
        lines.extend(["", "**Files touched**", *[f"- {item}" for item in files_touched]])
    if suggested_next_role:
        lines.extend(["", f"**Suggested next role:** {suggested_next_role}"])
    _append_text(path, "\n".join(lines) + "\n")
    return path


def append_capture_note(
    *,
    data_dir: Path,
    project_id: str,
    project_name: str,
    note: str,
    source: str = "mobile",
) -> Path:
    """Append a free-form captured note (e.g. from the mobile Capture button)
    into the project's shared AI memory so the next agent run sees it."""
    path = ensure_ai_context_file(data_dir, project_id, project_name)
    _rotate_if_needed(path)
    heading = f"### {utc_now().date().isoformat()} · captured ({source})"
    body = note.strip() or "_Empty note._"
    _append_text(path, "\n".join(["", heading, "", body]) + "\n")
    return path


def write_role_prompt(
    *,
    data_dir: Path,
    project_id: str,
    project_name: str,
    squad_name: str,
    squad_goal_md: str,
    work_item_title: str,
    instructions_md: str,
    role_name: str,
    role_description: str,
    prompt_preamble_md: str,
    context_mode: str,
    handoff_summary_md: str | None,
    handoff_blockers_md: str | None,
    files_touched: list[str],
) -> Path:
    context_file = ensure_ai_context_file(data_dir, project_id, project_name)
    prompt_dir = role_prompt_dir(data_dir, project_id)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f"{work_item_title_slug(work_item_title)}-{utc_now().strftime('%Y%m%d%H%M%S')}.md"

    prompt = "\n".join(
        [
            f"# Synapse Squad Prompt · {role_name}",
            "",
            f"Project: {project_name}",
            f"Squad: {squad_name}",
            f"Context mode: {context_mode}",
            "",
            "## Role",
            role_description or role_name,
            "",
            "## Role guidance",
            prompt_preamble_md.strip() or "_No extra role preamble._",
            "",
            "## Squad goal",
            squad_goal_md.strip() or "_No squad goal provided yet._",
            "",
            "## Current work item",
            f"Title: {work_item_title}",
            "",
            instructions_md.strip() or "_No additional instructions provided._",
            "",
            "## Latest handoff",
            handoff_summary_md.strip() if handoff_summary_md and handoff_summary_md.strip() else "_No prior handoff summary._",
            "",
            "## Known blockers",
            handoff_blockers_md.strip() if handoff_blockers_md and handoff_blockers_md.strip() else "_No blockers recorded._",
            "",
            "## Files touched recently",
            "\n".join(f"- {item}" for item in files_touched) if files_touched else "_No files recorded yet._",
            "",
            "## Shared project memory file",
            f"Path: {context_file}",
            "",
            AI_CONTEXT_DIRECTION_PROMPT,
            "",
            "## AI context excerpt",
            _context_excerpt(context_file, context_mode),
            "",
        ]
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(existing + text, encoding="utf-8")
    tmp.replace(path)


def _rotate_if_needed(path: Path) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= AI_CONTEXT_ROTATE_BYTES:
        return
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    archive = path.with_name(f"{AI_CONTEXT_ARCHIVE_PREFIX}-{stamp}.md")
    path.replace(archive)
    path.write_text(
        "\n".join(
            [
                "# Project memory archive rotated",
                "",
                f"Previous content moved to {archive.name}.",
                "",
                "## Session log (newest first)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _context_excerpt(path: Path, context_mode: str) -> str:
    if not path.exists():
        return "_No project AI context file exists yet._"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "_Project AI context file could not be read._"
    if not text:
        return "_Project AI context file is empty._"
    caps = {
        "minimal": 1200,
        "standard": 3000,
        "full": 7000,
    }
    cap = caps.get(context_mode, 3000)
    if len(text) <= cap:
        return text
    return text[-cap:]


def work_item_title_slug(title: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "work-item"


def _from_timestamp(value: float):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, tz=timezone.utc)
