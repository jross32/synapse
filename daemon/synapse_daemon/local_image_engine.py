"""Local image generation via an operator-managed ComfyUI server, no cloud API key.

ComfyUI must be installed separately with an appropriate open-weights checkpoint.
Never auto-download untrusted models or silently fall back to a paid provider.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_URL = 'http://127.0.0.1:8188'


def _base() -> str:
    from urllib.parse import urlsplit
    url = os.getenv('SYNAPSE_COMFYUI_URL', DEFAULT_URL).strip().rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError('Local image engine URL must be loopback HTTP')
    return url


def _json(path: str, payload: dict | None = None, *, timeout: float = 8) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(_base() + path, data=data, headers={'Content-Type': 'application/json'} if data else {}, method='POST' if data else 'GET')
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read())


def status() -> dict:
    checkpoint = os.getenv('SYNAPSE_COMFYUI_CHECKPOINT', '').strip()
    try:
        _json('/system_stats')
        online = True
    except (OSError, ValueError, RuntimeError):
        online = False
    return {'provider': 'local', 'backend': 'comfyui', 'configured': bool(online and checkpoint), 'server_up': online, 'model': checkpoint or None, 'requires_api_key': False, 'reason': None if online and checkpoint else 'Start ComfyUI and set SYNAPSE_COMFYUI_CHECKPOINT to an installed checkpoint filename.'}


def generate(prompt: str, target: Path, *, width: int, height: int, output_format: str, quality: str, background: str) -> dict:
    if background == 'transparent':
        raise RuntimeError('Local ComfyUI basic workflow does not support transparent backgrounds')
    checkpoint = os.getenv('SYNAPSE_COMFYUI_CHECKPOINT', '').strip()
    if not checkpoint or '/' in checkpoint or '\\' in checkpoint:
        raise RuntimeError('Set SYNAPSE_COMFYUI_CHECKPOINT to an installed checkpoint filename')
    # The standard SD1.5 ComfyUI node pipeline; checkpoints and checkpoints licensing are user-controlled.
    workflow = {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': checkpoint}},
        '2': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['1', 1]}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'blurry, distorted, low quality', 'clip': ['1', 1]}},
        '4': {'class_type': 'EmptyLatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '5': {'class_type': 'KSampler', 'inputs': {'seed': int.from_bytes(os.urandom(8), 'big') % (2**63), 'steps': 15 if quality == 'low' else 24, 'cfg': 7, 'sampler_name': 'euler', 'scheduler': 'normal', 'denoise': 1.0, 'model': ['1', 0], 'positive': ['2', 0], 'negative': ['3', 0], 'latent_image': ['4', 0]}},
        '6': {'class_type': 'VAEDecode', 'inputs': {'samples': ['5', 0], 'vae': ['1', 2]}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['6', 0], 'filename_prefix': 'synapse'}},
    }
    client_id = str(uuid.uuid4())
    job = _json('/prompt', {'prompt': workflow, 'client_id': client_id}, timeout=30)
    prompt_id = str(job.get('prompt_id') or '')
    if not prompt_id:
        raise RuntimeError('ComfyUI rejected image job: no prompt_id returned')
    deadline = time.monotonic() + float(os.getenv('SYNAPSE_LOCAL_IMAGE_TIMEOUT', '900'))
    outputs = None
    while time.monotonic() < deadline:
        history = _json('/history/' + urllib.parse.quote(prompt_id, safe=''), timeout=15)
        entry = history.get(prompt_id, {})
        status_info = entry.get('status', {})
        if status_info.get('status_str') == 'error':
            raise RuntimeError('ComfyUI image job failed')
        outputs = entry.get('outputs', {}).get('7', {}).get('images', [])
        if outputs:
            break
        time.sleep(2)
    if not outputs:
        raise RuntimeError('Timed out waiting for ComfyUI image')
    item = outputs[0]
    params = urllib.parse.urlencode({'filename': item['filename'], 'subfolder': item.get('subfolder', ''), 'type': item.get('type', 'output')})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(_base() + '/view?' + params, timeout=60) as response:
        data = response.read(40 * 1024 * 1024 + 1)
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > 40 * 1024 * 1024:
        raise RuntimeError('ComfyUI returned invalid or oversized image')
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(data)); img.load()
    if img.size != (width, height):
        raise RuntimeError('ComfyUI returned unexpected image dimensions')
    if output_format == 'jpeg':
        img.convert('RGB').save(target, format='JPEG', quality=93)
    elif output_format == 'webp':
        img.save(target, format='WEBP', quality=95)
    else:
        target.write_bytes(data)
    return {'model': checkpoint, 'request_id': prompt_id}


