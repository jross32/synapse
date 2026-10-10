"""Compare an approved UI reference with a real browser screenshot.

Never resize either capture silently: both must show the same viewport/engine,
stable data, and user-approved visual state. This checks visual *difference*,
not design quality, accessibility, or end-to-end functionality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare(
    reference: Path,
    actual: Path,
    output_dir: Path,
    *,
    tolerance: int = 24,
    max_bad_fraction: float = 0.10,
    max_mae: float = 15.0,
    ignore_mask: Path | None = None,
) -> dict[str, Any]:
    """Return a durable evidence record. White mask pixels are ignored.

    A FAIL or BLOCKED result is not a release pass. The approved reference
    and candidate are never altered.
    """
    if not 0 <= tolerance <= 255:
        raise ValueError("tolerance must be 0..255")
    if not 0 <= max_bad_fraction <= 1:
        raise ValueError("max_bad_fraction must be 0..1")
    if not 0 <= max_mae <= 255:
        raise ValueError("max_mae must be 0..255")
    reference = Path(reference)
    actual = Path(actual)
    output_dir = Path(output_dir)
    for path in (reference, actual):
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")

    record: dict[str, Any] = {
        "schema_version": 1,
        "reference": str(reference.resolve()),
        "actual": str(actual.resolve()),
        "reference_sha256": _sha256(reference),
        "actual_sha256": _sha256(actual),
        "thresholds": {
            "channel_tolerance": tolerance,
            "max_bad_fraction": max_bad_fraction,
            "max_mean_absolute_error": max_mae,
        },
        "note": "Pixel-level QA only; requires matched browser engine, viewport, test data and state.",
    }
    with Image.open(reference) as ref_src, Image.open(actual) as act_src:
        ref = ref_src.convert("RGB")
        act = act_src.convert("RGB")
    record["reference_size"] = list(ref.size)
    record["actual_size"] = list(act.size)
    if ref.size != act.size:
        record.update(
            status="BLOCKED",
            reason="Capture dimensions differ. Recapture the exact same viewport; no silent resize.",
        )
    else:
        mask: Image.Image | None = None
        if ignore_mask is not None:
            mask_path = Path(ignore_mask)
            with Image.open(mask_path) as mask_src:
                mask = mask_src.convert("L")
            if mask.size != ref.size:
                record.update(status="BLOCKED", reason="Ignore-mask dimensions do not match.")
            else:
                # Binary mask: white/255 is excluded, black/0 is compared.
                mask = mask.point(lambda value: 255 if value >= 128 else 0)
                record["ignore_mask_sha256"] = _sha256(mask_path)
        if "status" not in record:
            diff = ImageChops.difference(ref, act)
            valid_count = ref.width * ref.height
            if mask is not None:
                ignored = mask.histogram()[255]
                valid_count -= ignored
                diff = Image.composite(Image.new("RGB", ref.size, (0, 0, 0)), diff, mask)
            if valid_count == 0:
                record.update(status="BLOCKED", reason="All pixels were masked; no comparison is possible.")
            else:
                channels = diff.split()
                max_channel = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
                hist = max_channel.histogram()
                bad = sum(hist[tolerance + 1 :])
                channel_sums = [sum(i * n for i, n in enumerate(c.histogram())) for c in channels]
                mae = sum(channel_sums) / (3 * valid_count)
                frac = bad / valid_count
                passed = frac <= max_bad_fraction and mae <= max_mae
                record.update(
                    status="PASS" if passed else "FAIL",
                    compared_pixels=valid_count,
                    differing_pixels=bad,
                    bad_fraction=round(frac, 6),
                    mean_absolute_rgb_error=round(mae, 6),
                    reason="Within configured pixel thresholds." if passed else "Visual mismatch exceeds configured thresholds.",
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                heatmap = ImageOps.colorize(max_channel, black="#111111", white="#ff4545")
                overlay = Image.blend(ref, act, 0.5)
                heatmap.save(output_dir / "difference.png")
                overlay.save(output_dir / "overlay.png")
                record["difference_image"] = str((output_dir / "difference.png").resolve())
                record["overlay_image"] = str((output_dir / "overlay.png").resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    record["report"] = str((output_dir / "report.json").resolve())
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Approved reference screenshot PNG/JPEG/WebP.")
    parser.add_argument("actual", type=Path, help="Real application screenshot at same viewport/state.")
    parser.add_argument("--output", required=True, type=Path, help="Directory for report and difference previews.")
    parser.add_argument("--tolerance", type=int, default=24)
    parser.add_argument("--max-bad-fraction", type=float, default=0.10)
    parser.add_argument("--max-mae", type=float, default=15.0)
    parser.add_argument("--ignore-mask", type=Path, default=None, help="Optional grayscale mask: white=ignore.")
    args = parser.parse_args()
    try:
        report = compare(
            args.reference, args.actual, args.output,
            tolerance=args.tolerance,
            max_bad_fraction=args.max_bad_fraction,
            max_mae=args.max_mae,
            ignore_mask=args.ignore_mask,
        )
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
