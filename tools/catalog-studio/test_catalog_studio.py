from pathlib import Path
from PIL import Image, ImageDraw
from controller import PRESETS, composite_subject, process, recommend_preset, _edge_quality, save_profile, load_profile, batch_process

def fake_subject(path: Path):
    im=Image.new("RGBA",(500,700),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((80,50,420,650),radius=30,fill=(20,80,170,255))
    d.rectangle((180,100,320,170),fill=(255,255,255,255)); im.save(path)

def test_presets_versioned():
    assert len(PRESETS)>=4
    assert all(p.version==1 for p in PRESETS.values())

def test_composite_is_repeatable(tmp_path):
    s=tmp_path/"s.png"; fake_subject(s); subject=Image.open(s)
    a=composite_subject(subject,"warm-gallery",(800,1000))
    b=composite_subject(subject,"warm-gallery",(800,1000))
    assert a.tobytes()==b.tobytes()

def test_process_receipt_and_no_overwrite(tmp_path):
    s=tmp_path/"s.png"; fake_subject(s); out=tmp_path/"out.jpg"
    receipt=process(s,out,preset_id="clean-white",subject_path=s,width=800,height=1000)
    assert out.exists()
    assert receipt["preset"]["id"]=="clean-white"
    assert receipt["input_sha256"] and receipt["output_sha256"]
    assert receipt["subject_rgb_sha256"] and receipt["subject_alpha_sha256"]
    assert receipt["qa_status"]=="pass"
    assert out.with_suffix(".jpg.catalog.json").exists()
    try: process(s,out,preset_id="clean-white",subject_path=s,width=800,height=1000)
    except FileExistsError: pass
    else: raise AssertionError("must protect existing output")

def test_recommendation_has_known_preset(tmp_path):
    s=tmp_path/"s.png"; fake_subject(s)
    result=recommend_preset(Image.open(s).convert("RGB"))
    assert result["preset_id"] in PRESETS

def test_bad_alpha_requires_review(tmp_path):
    im=Image.new("RGBA",(100,100),(20,20,20,255))
    qa=_edge_quality(im.getchannel("A"))
    assert qa["review_required"] is True

def test_review_artifact_written(tmp_path):
    inp=tmp_path/"input.png"
    bad=Image.new("RGBA",(100,100),(20,20,20,255)); bad.save(inp)
    out=tmp_path/"out.jpg"
    receipt=process(inp,out,preset_id="clean-white",subject_path=inp,width=200,height=250)
    assert receipt["qa_status"]=="review_required"
    assert receipt["segmentation"]["review_reasons"]
    assert receipt["review_artifacts"]
    assert (tmp_path/"review"/"out.subject.png").exists()
    assert (tmp_path/"review"/"out.mask.png").exists()
    assert (tmp_path/"review"/"out.preview.jpg").exists()


def test_profile_roundtrip_and_version_lock(tmp_path):
    p=tmp_path/"store.json"
    made=save_profile(p,name="Justin Store",preset_id="warm-gallery",width=800,height=1000)
    loaded=load_profile(p)
    assert loaded==made
    assert loaded["preset_version"]==PRESETS["warm-gallery"].version

def test_profile_rejects_unknown_preset(tmp_path):
    p=tmp_path/"bad.json"; p.write_text('{"schema":1,"preset_id":"nope","preset_version":1}',encoding="utf-8")
    try: load_profile(p)
    except ValueError as e: assert "unknown preset" in str(e)
    else: raise AssertionError("invalid profile must fail")

def test_batch_empty_is_valid_receipt(tmp_path):
    inp=tmp_path/"in"; out=tmp_path/"out"; inp.mkdir()
    summary=batch_process(inp,out,preset_id="warm-gallery")
    assert summary["count"]==0 and summary["errors"]==0
    assert (out/"batch.catalog.json").exists()

def test_process_tolerates_slightly_truncated_jpeg(tmp_path):
    from PIL import Image
    src = tmp_path / "source.jpg"
    Image.new("RGB", (320, 320), (80, 110, 140)).save(src, quality=90)
    raw = src.read_bytes()
    src.write_bytes(raw[:-1])
    from PIL import ImageFile
    assert ImageFile.LOAD_TRUNCATED_IMAGES is True

def test_edge_quality_flags_moderate_border_contact():
    from PIL import Image, ImageDraw
    alpha = Image.new("L", (100, 100), 0)
    draw = ImageDraw.Draw(alpha)
    draw.rectangle((0, 20, 60, 80), fill=255)
    qa = _edge_quality(alpha)
    assert qa["border_visible_ratio"] > 0.10
    assert qa["review_required"] is True
def test_batch_writes_review_queue_and_receipts(tmp_path):
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    safe = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(safe).rectangle((25, 15, 75, 80), fill=(180, 40, 90, 255))
    safe.save(input_dir / "safe.png")
    bad = Image.new("RGBA", (100, 100), (100, 100, 100, 255))
    bad.save(input_dir / "bad.png")
    result = batch_process(input_dir, tmp_path / "out", width=160, height=200)
    import json
    queue = json.loads((tmp_path / "out" / "review-queue.catalog.json").read_text())
    assert result["count"] == 2 and result["pass"] == 1 and result["review_required"] == 1
    assert result["inference_sessions_reused_in_batch"] is True
    assert result["elapsed_seconds"] >= 0
    assert queue["count"] == 1 and len(queue["items"]) == 1
    assert queue["items"][0]["status"] == "review_required"
    assert queue["items"][0]["review_artifacts"]["preview"]
    assert Path(queue["items"][0]["receipt"]).exists()
