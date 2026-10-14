"""Create the PUBLIC publisher configuration bundled with Synapse installers.

The Ed25519 private signing key must remain outside Git and installers.
The trusted public key is intentionally distributed with the Electron app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def configured_public_feed(feed_url: str, public_key_pem: bytes) -> dict:
    parsed = urlparse(feed_url)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Feed origin must be an unauthenticated HTTPS hostname")
    if parsed.query or parsed.fragment:
        raise ValueError("Feed URL may not contain a query or fragment")
    key = load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Publisher key must be an Ed25519 public key")
    return {"schema": 1, "feed_url": feed_url, "public_key": public_key_pem.decode("ascii")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed-url", required=True)
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        public = args.public_key_file.read_bytes()
        result = configured_public_feed(args.feed_url, public)
        document = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists() and args.output.read_bytes() != document:
            raise ValueError("Existing bundled publisher metadata differs; refuse overwrite")
        if not args.output.exists():
            with args.output.open("xb") as out:
                out.write(document)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status":"configured",
                      "public_key_sha256":hashlib.sha256(public).hexdigest(),
                      "feed_url":args.feed_url, "output":str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
