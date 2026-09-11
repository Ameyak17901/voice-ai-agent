import os
import sys
import warnings
from pathlib import Path

# In-memory miniaudio is used for decoding; suppress legacy pydub binary scan warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub.*")

import uvicorn

# Ensure project directories and vocode-core are in sys.path
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
VOCODE_CORE = REPO_ROOT / "vocode-core"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(VOCODE_CORE) not in sys.path:
    sys.path.insert(0, str(VOCODE_CORE))

from backend.config import settings

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Vocode Web Voice Copilot Server")
    parser.add_argument("--host", default=settings.host, help="Host address to bind")
    parser.add_argument("--port", type=int, default=settings.port, help="Port to bind")
    parser.add_argument("--reload", action="store_true", default=settings.debug, help="Enable auto-reload")
    parser.add_argument("--test", action="store_true", help="Perform smoke test and exit")
    args = parser.parse_args()

    if args.test:
        print("[TEST] Verifying server initialization...")
        from backend.app import app
        print(f"[TEST] Routes registered: {[route.path for route in app.routes]}")
        print("[TEST] Server initialized successfully!")
        sys.exit(0)

    print(f"============================================================")
    print(f" [*] Vocode Web Voice Copilot Service Starting")
    print(f" URL: http://{args.host}:{args.port}")
    print(f" WebSocket Conversation: ws://{args.host}:{args.port}/conversation")
    print(f"============================================================")
    reload_dirs = [str(BASE_DIR), str(VOCODE_CORE)] if args.reload else None
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=args.reload, reload_dirs=reload_dirs)
