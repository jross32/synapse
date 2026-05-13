"""Generate Synapse's tray + window icon.

Pure-stdlib PNG generator — no Pillow dependency. Produces a small neural
"nucleus + synapses" mark in two sizes:

  electron/icons/synapse.png      (32x32 — Tray default on Windows)
  electron/icons/synapse-256.png  (256x256 — installer + About dialog)

Run from the repo root:

    python scripts/gen-icon.py

Commit the generated PNGs; this script is the source of truth for the
placeholder mark, but the files are checked in so dev machines don't need to
re-run it.

The final designer-drawn icon replaces these files in Milestone J without
touching any code that consumes them.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = REPO_ROOT / "electron" / "icons"

# Brand palette — kept in sync with renderer/lib/theme-tokens.css.
BG_TOP = (15, 23, 50)        # #0F1732 — deep nucleus blue
BG_BOTTOM = (24, 13, 51)     # #180D33 — accent purple
ACCENT_RING = (124, 58, 237) # #7C3AED — synapse purple
ACCENT_GLOW = (34, 211, 238) # #22D3EE — synapse cyan
NUCLEUS = (241, 245, 249)    # #F1F5F9 — text-primary


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _write_png(path: Path, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    height = len(pixels)
    width = len(pixels[0])

    # PNG signature.
    out = b"\x89PNG\r\n\x1a\n"

    # IHDR — 8-bit RGBA.
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    out += _png_chunk(b"IHDR", ihdr)

    # IDAT — each scanline is preceded by a filter byte (0 = none).
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))
    out += _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))

    # IEND.
    out += _png_chunk(b"IEND", b"")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _blend(over: tuple[int, int, int, int], under: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    a_o = over[3] / 255
    a_u = under[3] / 255
    a_out = a_o + a_u * (1 - a_o)
    if a_out == 0:
        return (0, 0, 0, 0)
    r = int((over[0] * a_o + under[0] * a_u * (1 - a_o)) / a_out)
    g = int((over[1] * a_o + under[1] * a_u * (1 - a_o)) / a_out)
    b = int((over[2] * a_o + under[2] * a_u * (1 - a_o)) / a_out)
    return (r, g, b, int(a_out * 255))


def render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """Draw the icon at the given square size and return RGBA pixel rows."""

    half = size / 2
    radius_outer = half - 1
    radius_nucleus = size * 0.16
    radius_ring = size * 0.42
    ring_thickness = max(1.5, size * 0.06)

    pixels: list[list[tuple[int, int, int, int]]] = []
    for y in range(size):
        row: list[tuple[int, int, int, int]] = []
        for x in range(size):
            # Distance from centre (subpixel-friendly).
            dx = x + 0.5 - half
            dy = y + 0.5 - half
            d = math.hypot(dx, dy)

            if d > radius_outer + 0.5:
                # Outside the badge — fully transparent.
                row.append((0, 0, 0, 0))
                continue

            # Soft outer alpha (antialiased edge).
            outer_alpha = _antialias(radius_outer, d)

            # Vertical gradient background.
            t = y / max(size - 1, 1)
            bg_rgb = _mix(BG_TOP, BG_BOTTOM, t)
            base = (*bg_rgb, int(255 * outer_alpha))

            # Synapse ring.
            ring_alpha = _ring_alpha(d, radius_ring, ring_thickness)
            if ring_alpha > 0:
                base = _blend((*ACCENT_RING, int(255 * ring_alpha)), base)

            # Six diagonal "synapse" sparks around the ring.
            spark_alpha = _spark_alpha(dx, dy, radius_ring, ring_thickness)
            if spark_alpha > 0:
                base = _blend((*ACCENT_GLOW, int(255 * spark_alpha)), base)

            # Nucleus dot in the centre.
            nucleus_alpha = _antialias(radius_nucleus, d)
            if nucleus_alpha > 0:
                base = _blend((*NUCLEUS, int(255 * nucleus_alpha)), base)

            row.append(base)
        pixels.append(row)
    return pixels


def _antialias(target_radius: float, d: float) -> float:
    """1.0 inside, 0.0 outside, smooth 1-px edge."""

    if d <= target_radius - 0.5:
        return 1.0
    if d >= target_radius + 0.5:
        return 0.0
    return 1.0 - (d - (target_radius - 0.5))


def _ring_alpha(d: float, radius: float, thickness: float) -> float:
    inner = radius - thickness / 2
    outer = radius + thickness / 2
    if d < inner - 0.5 or d > outer + 0.5:
        return 0.0
    if inner - 0.5 <= d <= inner + 0.5:
        return d - (inner - 0.5)
    if outer - 0.5 <= d <= outer + 0.5:
        return (outer + 0.5) - d
    return 1.0


def _spark_alpha(dx: float, dy: float, ring_radius: float, ring_thickness: float) -> float:
    """Tiny glowing dots at six positions around the ring."""

    spark_radius = ring_thickness * 0.9
    sparks = 6
    glow_radius = ring_radius + ring_thickness * 0.6
    for i in range(sparks):
        theta = i * (math.tau / sparks) + math.tau / 12
        cx = math.cos(theta) * glow_radius
        cy = math.sin(theta) * glow_radius
        d = math.hypot(dx - cx, dy - cy)
        if d < spark_radius:
            return max(0.0, 1.0 - d / spark_radius)
    return 0.0


def main() -> int:
    sizes = [(32, "synapse.png"), (256, "synapse-256.png")]
    for size, filename in sizes:
        path = ICON_DIR / filename
        _write_png(path, render(size))
        print(f"wrote {path.relative_to(REPO_ROOT)}  ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
