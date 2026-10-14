"""Exercise the real publisher signature contract with test-only keys."""
import base64
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sign_desktop_update", ROOT/"scripts"/"sign_desktop_update.py")
import sys
sys.path.insert(0, str(ROOT/"scripts"))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
COMMIT = "b"*40

@pytest.fixture
def files(tmp_path):
    artifact=tmp_path/"Synapse Setup 0.2.220.exe"
    artifact.write_bytes(b"release-gate-test-only"*64000)
    sha512=base64.b64encode(hashlib.sha512(artifact.read_bytes()).digest()).decode()
    latest=tmp_path/"latest.yml"
    latest.write_text(f"version: 0.2.220\nfiles:\n  - url: {artifact.name}\n    sha512: {sha512}\n    size: {artifact.stat().st_size}\npath: {artifact.name}\nsha512: {sha512}\n")
    proof=tmp_path/"proof.json"
    proof.write_text(json.dumps({"status":"verified","version":"0.2.220","source_commit":COMMIT,
       "artifact_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),
       "account_preserved":True,"device_identity_preserved":True,
       "mcp_connector_url_preserved":True}))
    key=Ed25519PrivateKey.generate()
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())
    return artifact,latest,proof,key,pem

def test_signed_manifest_matches_electron_node_crypto(files,tmp_path):
    artifact,latest,proof,key,pem=files
    url="https://downloads.example.test/releases/"+artifact.name.replace(" ","%20")
    # Manifest URL filename is URL encoded, unlike on-disk file.
    with pytest.raises(ValueError, match="does not match"):
        publisher.signed_feed(artifact,latest,proof,"0.2.220",COMMIT,url,"Ready",pem)
    url="https://downloads.example.test/releases/"+artifact.name
    manifest=publisher.signed_feed(artifact,latest,proof,"0.2.220",COMMIT,url,"Ready",pem)
    unsigned={k:manifest[k] for k in ("version","notes","windows")}
    payload=json.dumps(unsigned,separators=(",",":"),ensure_ascii=False).encode()
    key.public_key().verify(base64.b64decode(manifest["signature"]),payload)
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    m=tmp_path/"feed.json";m.write_text(json.dumps(manifest))
    pub=tmp_path/"test-public.pem";pub.write_bytes(public)
    js="""const fs=require('node:fs'),crypto=require('node:crypto');
const feed=JSON.parse(fs.readFileSync(process.argv[1]));const key=fs.readFileSync(process.argv[2]);
const payload=JSON.stringify({version:feed.version,notes:feed.notes,windows:feed.windows});
if(!crypto.verify(null,Buffer.from(payload),key,Buffer.from(feed.signature,'base64')))process.exit(1);
"""
    run=subprocess.run(["node","-e",js,str(m),str(pub)],capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr

def test_signed_manifest_rejects_mismatched_build_and_non_https(files):
    artifact,latest,proof,key,pem=files
    with pytest.raises(ValueError, match="source commit"):
        publisher.signed_feed(artifact,latest,proof,"0.2.220","c"*40,
           "https://downloads.example.test/"+artifact.name,"",pem)
    with pytest.raises(ValueError, match="HTTPS"):
        publisher.signed_feed(artifact,latest,proof,"0.2.220",COMMIT,
           "http://downloads.example.test/"+artifact.name,"",pem)
