from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFile, ImageFilter, ImageOps, ImageStat

ImageFile.LOAD_TRUNCATED_IMAGES = True

VERSION = "0.10.0"
PRESET_SCHEMA = 1
_ORT_SESSION_CACHE: dict[str, Any] = {}

@dataclass(frozen=True)
class StudioPreset:
    id: str
    name: str
    version: int
    background_top: str
    background_bottom: str
    vignette: float
    subject_fill: float
    vertical_anchor: float
    shadow_opacity: float
    shadow_blur: int
    shadow_offset_y: int
    description: str
    best_for: tuple[str, ...]

PRESETS: dict[str, StudioPreset] = {
    "warm-gallery": StudioPreset(
        "warm-gallery", "Warm Gallery", 1, "#F3EFE7", "#E7DED1", .10, .80, .49, .17, 24, 18,
        "Soft warm plaster-style studio. Natural and resale-friendly without competing with garment color.",
        ("blue", "green", "purple", "black", "denim", "multicolor"),
    ),
    "clean-white": StudioPreset(
        "clean-white", "Clean White", 1, "#FAFAF8", "#EEEEEA", .06, .82, .49, .14, 22, 16,
        "Bright neutral catalog background with a restrained floor falloff.",
        ("black", "navy", "red", "green", "multicolor"),
    ),
    "cool-concrete": StudioPreset(
        "cool-concrete", "Cool Concrete", 1, "#E4E8E8", "#C9D0D1", .11, .80, .49, .18, 25, 18,
        "Cool gray studio surface for warm, cream, red and earth-tone garments.",
        ("white", "cream", "red", "orange", "brown", "tan"),
    ),
    "charcoal": StudioPreset(
        "charcoal", "Charcoal", 1, "#34383D", "#1F2327", .14, .79, .49, .22, 27, 19,
        "Dark premium backdrop intended for pale or bright garments.",
        ("white", "cream", "yellow", "pink", "pastel"),
    ),
}

def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

def _image_channel_sha256(image: Image.Image, mode: str) -> str:
    return hashlib.sha256(image.convert(mode).tobytes()).hexdigest()

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _gradient(size: tuple[int, int], preset: StudioPreset) -> Image.Image:
    # Pillow-native deterministic gradient, with no NumPy startup.
    # NumPy is intentionally kept out of the lightweight import path.
    w, h = size
    top = _hex_rgb(preset.background_top)
    bottom = _hex_rgb(preset.background_bottom)
    if h <= 1:
        rows = [top]
    else:
        rows = [tuple(round(top[c] * (1-t) + bottom[c] * t) for c in range(3)) for t in (y/(h-1) for y in range(h))]
    strip = Image.new('RGB', (1, h))
    strip.putdata(rows)
    base = strip.resize((w, h))

    # Apply a subtle radial vignette, generating the
    # factor field with Pillow so importing controller does not import NumPy.
    radial = Image.radial_gradient('L').resize(size)
    # Keep the vignette intentionally subtle; exact output is regression-tested
    # by the accepted real-garment batch rather than relying on implementation internals.
    keep = radial.point(lambda p: round(255 - p * preset.vignette))
    return Image.composite(base, Image.new('RGB', size, (0, 0, 0)), keep)

def _bbox_from_alpha(alpha: Image.Image, threshold: int = 8) -> tuple[int, int, int, int] | None:
    return alpha.point(lambda p: 255 if p > threshold else 0).getbbox()

def _trim_subject(subject: Image.Image) -> Image.Image:
    if subject.mode != "RGBA":
        subject = subject.convert("RGBA")
    bbox = _bbox_from_alpha(subject.getchannel("A"))
    if not bbox:
        raise ValueError("subject has no visible pixels")
    return subject.crop(bbox)

def _dominant_color(image: Image.Image) -> str:
    im = ImageOps.exif_transpose(image).convert("RGB")
    im.thumbnail((96, 96))
    r, g, b = ImageStat.Stat(im).mean
    mx, mn = max(r,g,b), min(r,g,b)
    if mx < 65: return "black"
    if mn > 205: return "white"
    if mx - mn < 22: return "gray"
    if r > g*1.25 and r > b*1.25: return "red"
    if g > r*1.18 and g > b*1.10: return "green"
    if b > r*1.20 and b > g*1.08: return "blue"
    if r > 150 and g > 120 and b < 110: return "tan"
    if r > 150 and b > 130 and g < 145: return "pink"
    return "multicolor"

def recommend_preset(image: Image.Image) -> dict[str, Any]:
    color = _dominant_color(image)
    scores: dict[str, int] = {}
    for key, preset in PRESETS.items():
        scores[key] = 3 if color in preset.best_for else 1
    if color in {"white", "cream", "pastel"}:
        scores["charcoal"] += 3
    if color in {"black", "navy"}:
        scores["clean-white"] += 2
    if color in {"red", "orange", "brown", "tan"}:
        scores["cool-concrete"] += 2
    if color in {"green", "blue", "purple", "multicolor"}:
        scores["warm-gallery"] += 2
    chosen = max(scores, key=scores.get)
    return {"dominant_color": color, "preset_id": chosen, "scores": scores}

def _edge_quality(alpha: Image.Image) -> dict[str, Any]:
    alpha = alpha.convert("L")
    w, h = alpha.size
    total = max(w*h, 1)
    hist = alpha.histogram()
    visible_count = sum(hist[9:])
    soft_count = sum(hist[9:247])
    bbox = _bbox_from_alpha(alpha)
    bbox_coverage = 0.0 if not bbox else ((bbox[2]-bbox[0])*(bbox[3]-bbox[1]))/total
    visible_ratio = visible_count/total
    soft_ratio = soft_count/visible_count if visible_count else 1.0

    border_total = max(2*w + 2*h, 1)
    border_visible_count = 0
    if w and h:
        border_visible_count += sum(1 for v in alpha.crop((0,0,w,1)).get_flattened_data() if v > 8)
        border_visible_count += sum(1 for v in alpha.crop((0,h-1,w,h)).get_flattened_data() if v > 8)
        border_visible_count += sum(1 for v in alpha.crop((0,0,1,h)).get_flattened_data() if v > 8)
        border_visible_count += sum(1 for v in alpha.crop((w-1,0,w,h)).get_flattened_data() if v > 8)
    border_visible = border_visible_count / border_total
    reasons: list[str] = []
    if visible_ratio < .02:
        reasons.append("subject_too_small")
    if visible_ratio > .90:
        reasons.append("subject_fills_frame")
    if bbox_coverage < .06:
        reasons.append("subject_bbox_too_small")
    if bbox_coverage > .96:
        reasons.append("subject_bbox_touches_frame")
    if soft_ratio > .50:
        reasons.append("mask_too_soft")
    if border_visible > .10:
        reasons.append("subject_touches_border")
    return {
        "visible_ratio": round(float(visible_ratio), 4),
        "bbox_coverage": round(float(bbox_coverage), 4),
        "soft_edge_ratio": round(float(soft_ratio), 4),
        "border_visible_ratio": round(border_visible, 4),
        "review_reasons": reasons,
        "review_required": bool(reasons),
    }

def _save_review_artifacts(source: Image.Image, subject: Image.Image, review_dir: Path, stem: str) -> dict[str, str]:
    review_dir.mkdir(parents=True, exist_ok=True)
    subject_path = review_dir / f"{stem}.subject.png"
    mask_path = review_dir / f"{stem}.mask.png"
    preview_path = review_dir / f"{stem}.preview.jpg"
    subject.save(subject_path)
    subject.getchannel("A").save(mask_path)

    preview = Image.new("RGB", (1200, 700), "#F2F2F2")
    left = ImageOps.contain(source.convert("RGB"), (560, 620))
    right_rgba = ImageOps.contain(subject, (560, 620))
    left_x = (600-left.width)//2
    right_x = 600 + (600-right_rgba.width)//2
    y_left = 50 + (620-left.height)//2
    y_right = 50 + (620-right_rgba.height)//2
    preview.paste(left, (left_x, y_left))
    checker = Image.new("RGB", right_rgba.size, "#E6E6E6")
    checker.paste(right_rgba.convert("RGB"), (0, 0), right_rgba.getchannel("A"))
    preview.paste(checker, (right_x, y_right))
    preview.save(preview_path, quality=90)
    return {"subject": str(subject_path), "mask": str(mask_path), "preview": str(preview_path)}

def composite_subject(subject: Image.Image, preset_id: str, output_size=(1600, 2000)) -> Image.Image:
    preset = PRESETS[preset_id]
    subject = _trim_subject(subject)
    canvas = _gradient(output_size, preset).convert("RGBA")
    cw, ch = output_size
    sw, sh = subject.size
    scale = min(cw * preset.subject_fill / sw, ch * .80 / sh)
    size = (max(1, round(sw*scale)), max(1, round(sh*scale)))
    subject = subject.resize(size, Image.Resampling.LANCZOS)
    x = round((cw-size[0])/2)
    center_y = ch*preset.vertical_anchor
    y = round(center_y-size[1]/2)

    alpha = subject.getchannel("A")
    shadow = Image.new("RGBA", output_size, (0,0,0,0))
    mask = Image.new("L", output_size, 0)
    mask.paste(alpha, (x, y+preset.shadow_offset_y))
    mask = mask.filter(ImageFilter.GaussianBlur(preset.shadow_blur))
    shadow.putalpha(mask.point(lambda p: round(p*preset.shadow_opacity)))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(subject, (x,y))
    return canvas.convert("RGB")

def segment_with_onnx(source: Image.Image, model: str = "u2netp") -> tuple[Image.Image, dict[str, Any]]:
    import numpy as np
    if model != "u2netp":
        raise ValueError("direct ONNX backend currently supports u2netp only")
    try:
        import onnxruntime as ort
    except Exception as exc:
        raise RuntimeError("onnxruntime is required for automatic segmentation") from exc
    model_path = Path.home() / ".u2net" / "u2netp.onnx"
    if not model_path.exists():
        raise RuntimeError(f"segmentation model missing: {model_path}")
    original = source.convert("RGB")
    resized = original.resize((320, 320), Image.Resampling.LANCZOS)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    tensor = np.transpose(arr, (2, 0, 1))[None].astype(np.float32)
    cache_key = str(model_path.resolve())
    session = _ORT_SESSION_CACHE.get(cache_key)
    if session is None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
        _ORT_SESSION_CACHE[cache_key] = session
    pred = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    pmin, pmax = float(pred.min()), float(pred.max())
    if pmax - pmin < 1e-8:
        mask = np.zeros_like(pred, dtype=np.uint8)
    else:
        mask = np.uint8(np.clip((pred-pmin)/(pmax-pmin)*255.0, 0, 255))
    alpha = Image.fromarray(mask, "L").resize(original.size, Image.Resampling.LANCZOS)
    subject = original.convert("RGBA")
    subject.putalpha(alpha)
    return subject, {"method":"onnx-direct","model":model,"model_sha256":_sha256(model_path),**_edge_quality(alpha)}

def segment_with_rembg(source: Image.Image, model: str = "u2netp") -> tuple[Image.Image, dict[str, Any]]:
    # Compatibility alias. Direct ONNX avoids rembg's heavyweight import/warmup path.
    return segment_with_onnx(source, model=model)

def process(input_path: Path, output_path: Path, *, preset_id: str = "auto", subject_path: Path | None = None,
            width: int = 1600, height: int = 2000, force: bool = False, model: str = "u2netp") -> dict[str, Any]:
    if output_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {output_path}")
    source = ImageOps.exif_transpose(Image.open(input_path)).convert("RGB")
    recommendation = recommend_preset(source)
    if preset_id == "auto":
        preset_id = recommendation["preset_id"]
    if preset_id not in PRESETS:
        raise ValueError(f"unknown preset: {preset_id}")
    if subject_path:
        subject = ImageOps.exif_transpose(Image.open(subject_path)).convert("RGBA")
        segmentation = {"method": "provided-alpha", **_edge_quality(subject.getchannel("A"))}
    elif input_path.suffix.lower() == ".png" and "A" in Image.open(input_path).getbands():
        subject = ImageOps.exif_transpose(Image.open(input_path)).convert("RGBA")
        segmentation = {"method": "source-alpha", **_edge_quality(subject.getchannel("A"))}
    else:
        subject, segmentation = segment_with_rembg(source, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    review_artifacts = None
    if segmentation.get("review_required"):
        review_dir = output_path.parent / "review"
        review_artifacts = _save_review_artifacts(source, subject, review_dir, output_path.stem)

    result = composite_subject(subject, preset_id, (width, height))
    result.save(output_path, quality=94, subsampling=0)
    receipt = {
        "catalog_studio_version": VERSION,
        "preset_schema": PRESET_SCHEMA,
        "preset": asdict(PRESETS[preset_id]),
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "output": str(output_path),
        "output_sha256": _sha256(output_path),
        "output_size": [width, height],
        "recommendation": recommendation,
        "segmentation": segmentation,
        "subject_rgb_sha256": _image_channel_sha256(subject, "RGB"),
        "subject_alpha_sha256": _image_channel_sha256(subject.getchannel("A"), "L"),
        "qa_status": "review_required" if segmentation.get("review_required") else "pass",
        "review_artifacts": review_artifacts,
        "pixel_preservation_contract": "Garment appearance is sourced from the segmented original image; Catalog Studio does not generatively redraw the garment.",
    }
    receipt_path = output_path.with_suffix(output_path.suffix + ".catalog.json")
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt

def save_profile(profile_path: Path, *, name: str, preset_id: str, model: str = "u2netp", width: int = 1600, height: int = 2000) -> dict[str, Any]:
    if preset_id not in PRESETS:
        raise ValueError(f"unknown preset: {preset_id}")
    profile={"schema":1,"name":name,"preset_id":preset_id,"preset_version":PRESETS[preset_id].version,"model":model,"width":width,"height":height}
    profile_path.parent.mkdir(parents=True,exist_ok=True)
    profile_path.write_text(json.dumps(profile,indent=2),encoding="utf-8")
    return profile

def load_profile(profile_path: Path) -> dict[str, Any]:
    profile=json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("schema") != 1: raise ValueError("unsupported profile schema")
    preset_id=profile.get("preset_id")
    if preset_id not in PRESETS: raise ValueError(f"profile references unknown preset: {preset_id}")
    if profile.get("preset_version") != PRESETS[preset_id].version: raise ValueError("profile preset version mismatch")
    return profile

def batch_process(input_dir: Path, output_dir: Path, *, preset_id: str = "warm-gallery", model: str = "u2netp", force: bool = False, width: int = 1600, height: int = 2000) -> dict[str, Any]:
    supported={".jpg",".jpeg",".png",".webp"}
    files=sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in supported)
    results=[]
    batch_started = time.perf_counter()
    for src in files:
        out=output_dir / f"{src.stem}.jpg"
        try:
            receipt=process(src,out,preset_id=preset_id,force=force,model=model,width=width,height=height)
            results.append({"input":str(src),"output":str(out),"status":receipt["qa_status"],"preset":receipt["preset"]["id"],"receipt":str(out.with_suffix(out.suffix + ".catalog.json")),"review_artifacts":receipt.get("review_artifacts"),"review_reasons":receipt["segmentation"].get("review_reasons",[])})
        except Exception as exc:
            results.append({"input":str(src),"status":"error","error":str(exc)})
    summary={"catalog_studio_version":VERSION,"preset_locked":preset_id,"count":len(files),"pass":sum(r.get("status")=="pass" for r in results),"review_required":sum(r.get("status")=="review_required" for r in results),"errors":sum(r.get("status")=="error" for r in results),"elapsed_seconds":round(time.perf_counter()-batch_started,3),"inference_sessions_reused_in_batch":True,"results":results}
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"batch.catalog.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    review_queue={"schema":1,"catalog_studio_version":VERSION,"batch_summary":str(output_dir/"batch.catalog.json"),"count":summary["review_required"]+summary["errors"],"items":[r for r in results if r.get("status") != "pass"]}
    (output_dir/"review-queue.catalog.json").write_text(json.dumps(review_queue,indent=2),encoding="utf-8")
    return summary

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deterministic resale product-photo compositor")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("presets")
    c = sub.add_parser("recommend"); c.add_argument("input")
    c = sub.add_parser("process")
    c.add_argument("input"); c.add_argument("output"); c.add_argument("--preset", default="auto")
    c.add_argument("--subject"); c.add_argument("--width", type=int, default=1600); c.add_argument("--height", type=int, default=2000)
    c.add_argument("--force", action="store_true"); c.add_argument("--model", default="u2netp")
    b = sub.add_parser("batch"); b.add_argument("input_dir"); b.add_argument("output_dir"); b.add_argument("--preset", default="warm-gallery"); b.add_argument("--model", default="u2netp"); b.add_argument("--profile"); b.add_argument("--force", action="store_true")
    sp=sub.add_parser("save-profile"); sp.add_argument("path"); sp.add_argument("name"); sp.add_argument("--preset",default="warm-gallery"); sp.add_argument("--model",default="u2netp"); sp.add_argument("--width",type=int,default=1600); sp.add_argument("--height",type=int,default=2000)
    lp=sub.add_parser("show-profile"); lp.add_argument("path")
    return p

def main() -> int:
    args = _parser().parse_args()
    if args.cmd == "presets":
        print(json.dumps({k: asdict(v) for k,v in PRESETS.items()}, indent=2)); return 0
    if args.cmd == "recommend":
        image = ImageOps.exif_transpose(Image.open(args.input)).convert("RGB")
        print(json.dumps(recommend_preset(image), indent=2)); return 0
    if args.cmd == "save-profile":
        print(json.dumps(save_profile(Path(args.path),name=args.name,preset_id=args.preset,model=args.model,width=args.width,height=args.height),indent=2)); return 0
    if args.cmd == "show-profile":
        print(json.dumps(load_profile(Path(args.path)),indent=2)); return 0
    if args.cmd == "batch":
        cfg=load_profile(Path(args.profile)) if args.profile else {"preset_id":args.preset,"model":args.model,"width":1600,"height":2000}
        print(json.dumps(batch_process(Path(args.input_dir),Path(args.output_dir),preset_id=cfg["preset_id"],model=cfg["model"],width=cfg["width"],height=cfg["height"],force=args.force),indent=2)); return 0
    if args.cmd == "process":
        receipt = process(Path(args.input), Path(args.output), preset_id=args.preset,
                          subject_path=Path(args.subject) if args.subject else None,
                          width=args.width, height=args.height, force=args.force, model=args.model)
        print(json.dumps(receipt, indent=2)); return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())



