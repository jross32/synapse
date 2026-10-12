"""Validated ingestion of Synapse's own browser visual-audit report.

An HTTP 200 or arbitrary screenshot never becomes a PASS. All required
viewport reports must be present, clean, and backed by real screenshot files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field

from . import quality_os


class VisualAuditImport(BaseModel):
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    report_path: str = Field(min_length=1)


REQUIRED_DEVICES = frozenset({"desktop", "mobile", "small-mobile"})


def ingest_visual_report(conn, payload: VisualAuditImport) -> quality_os.QualityEvidence:
    report_path = Path(payload.report_path).resolve(strict=True)
    if not report_path.is_file() or report_path.name != "report.json":
        raise ValueError("Expected an existing visual-qa report.json")
    if report_path.stat().st_size > 2_000_000:
        raise ValueError("Visual report too large")
    import json
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    pages = report.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Visual report has no pages")
    devices = {p.get("device") for p in pages if isinstance(p, dict)}
    errors = []
    if devices != REQUIRED_DEVICES or len(pages) != len(REQUIRED_DEVICES):
        errors.append("Missing or duplicate required viewport")
    if not report.get("url") or not str(report["url"]).startswith(("http://", "https://")):
        errors.append("Missing audited URL")
    for page in pages:
        if not isinstance(page, dict):
            errors.append("Invalid viewport entry")
            continue
        if not isinstance(page.get("status"), int) or page["status"] >= 400 or page["status"] < 200:
            errors.append(f"{page.get('device')}: HTTP status not successful")
        for key in ("errors", "consoleErrors", "overflow", "contrast"):
            if not isinstance(page.get(key), list) or page[key]:
                errors.append(f"{page.get('device')}: {key} not clean")
        if page.get("horizontalOverflow"):
            errors.append(f"{page.get('device')}: horizontal overflow")
        screenshots = page.get("screenshots")
        if not isinstance(screenshots, list) or not screenshots:
            errors.append(f"{page.get('device')}: missing screenshot")
        else:
            for screenshot in screenshots:
                if not isinstance(screenshot, str):
                    errors.append("Invalid screenshot path")
                    continue
                image = Path(screenshot)
                if not image.is_absolute():
                    image = report_path.parent / image
                image = image.resolve()
                if not image.is_file() or image.stat().st_size == 0:
                    errors.append(f"{page.get('device')}: screenshot unavailable")
    passed = not errors and report.get("failureCount") == 0
    evidence = quality_os.QualityEvidence(
        id=str(uuid4()),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        evidence_kind="browser-proof",
        label="Synapse visual QA: " + ("PASS" if passed else "FAIL"),
        verdict=quality_os.QualityEvidenceVerdict.PASS if passed else quality_os.QualityEvidenceVerdict.FAIL,
        artifact_path=str(report_path),
        route=str(report.get("url", ""))[:1000],
        metadata={"visual_qa_passed": passed, "devices": sorted(devices), "errors": errors[:50], "source": "synapse-visual-qa"},
    )
    return quality_os.add_evidence(conn, evidence)
