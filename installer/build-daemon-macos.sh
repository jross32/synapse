#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p installer/daemon-dist
python -m PyInstaller --noconfirm --clean --onefile --name synapse-daemon --paths daemon --collect-all synapse_daemon --collect-all uvicorn --hidden-import anyio._backends._asyncio --distpath installer/daemon-dist --workpath installer/build-temp/macos --specpath installer/build-temp/macos daemon/packaged_daemon_main.py
chmod +x installer/daemon-dist/synapse-daemon
