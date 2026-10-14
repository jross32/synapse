"""Public updater metadata validation against publisher signatures."""
import importlib.util
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("publisher_config", ROOT/"scripts"/"configure_desktop_update_publisher.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

def test_public_config_accepts_only_ed25519_https_and_no_secrets():
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    result=config.configured_public_feed("https://download.whatapc.com/updates/stable.json",public)
    assert result["schema"]==1
    assert result["public_key"]==public.decode("ascii")
    assert "PRIVATE KEY" not in str(result)
    with pytest.raises(ValueError, match="HTTPS"):
        config.configured_public_feed("http://download.whatapc.com/updates/stable.json",public)
    with pytest.raises(ValueError, match="query or fragment"):
        config.configured_public_feed("https://download.whatapc.com/updates/stable.json?bad=1",public)
    rsa=generate_private_key(public_exponent=65537,key_size=2048)
    bad=rsa.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(ValueError,match="Ed25519"):
        config.configured_public_feed("https://download.whatapc.com/updates/stable.json",bad)
