"""Create a verified signed updater feed without publishing or rotating keys."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from release_artifact_gate import verify_windows_release

def signed_feed(artifact, latest, proof, version, commit, url, notes, key_pem):
    verified = verify_windows_release(Path(artifact), Path(latest), Path(proof),
                                       expected_version=version, expected_commit=commit)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("Update URL must be HTTPS without credentials, query or fragment")
    if parsed.path.rsplit("/",1)[-1] != Path(artifact).name:
        raise ValueError("Update URL does not match approved installer")
    if len(notes) > 2000:
        raise ValueError("Release notes too long")
    key = load_pem_private_key(key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Release signing key must be Ed25519")
    value = {"version":version, "notes":notes, "windows":{
        "url":url, "sha256":verified["sha256"], "size":verified["size_bytes"]}}
    payload = json.dumps(value, ensure_ascii=False, separators=(",",":")).encode("utf-8")
    value["signature"] = base64.b64encode(key.sign(payload)).decode("ascii")
    return value

def main():
    parser=argparse.ArgumentParser()
    for field in ("artifact","latest","proof","version","commit","url","key-file","output"):
        parser.add_argument("--"+field, required=True)
    parser.add_argument("--notes", default="")
    args=parser.parse_args()
    try:
        result=signed_feed(args.artifact,args.latest,args.proof,args.version,args.commit,
                           args.url,args.notes,Path(args.key_file).read_bytes())
        with Path(args.output).open("x",encoding="utf-8") as target:
            target.write(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status":"signed","version":result["version"],"output":args.output}))
if __name__=="__main__":
    main()
