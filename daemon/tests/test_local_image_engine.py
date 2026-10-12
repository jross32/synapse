from pathlib import Path
from unittest.mock import patch
import pytest
from synapse_daemon import image_assets


def test_local_provider_status_has_no_key_requirement(monkeypatch):
    monkeypatch.setenv('SYNAPSE_IMAGE_PROVIDER', 'local')
    monkeypatch.delenv('SYNAPSE_COMFYUI_CHECKPOINT', raising=False)
    state = image_assets.image_generation_status()
    assert state['provider'] == 'local'
    assert state['requires_api_key'] is False
    assert state['configured'] is False


def test_local_provider_preserves_project_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNAPSE_IMAGE_PROVIDER', 'local')
    def fake_generate(prompt, target, **kwargs):
        target.write_bytes(b'fake-test-png')
        return {'model': 'test-checkpoint', 'request_id': 'unit-test'}
    with patch('synapse_daemon.local_image_engine.generate', fake_generate):
        result = image_assets.generate_image(project_root=tmp_path, prompt='simple image', relative_path='art/icon.png')
    assert result['provider'] == 'local'
    assert (tmp_path / 'art/icon.png').read_bytes() == b'fake-test-png'
    assert (tmp_path / '.synapse/image-assets.jsonl').exists()


def test_local_provider_rejects_absent_backend(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNAPSE_IMAGE_PROVIDER', 'local')
    monkeypatch.delenv('SYNAPSE_COMFYUI_CHECKPOINT', raising=False)
    with pytest.raises(image_assets.ImageGenerationError, match='SYNAPSE_COMFYUI_CHECKPOINT'):
        image_assets.generate_image(project_root=tmp_path, prompt='image', relative_path='image.png')
