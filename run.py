"""Start TerraMind AI: API + built web app on http://localhost:8000

    python run.py            # opens the browser
    python run.py --no-browser --port 8001
"""

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 8000)))
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import uvicorn
    from app.config import ENV_FILES_FOUND, FRONTEND_DIST, ai_available

    print("TerraMind AI")
    print(f"  .env files found: {len(ENV_FILES_FOUND)}  |  AI available: {ai_available()}")
    if not ai_available():
        print("  ! No PORTKEY_API_KEY / OPENAI_API_KEY found. The financial engine works; AI features are disabled.")
    if not (FRONTEND_DIST / "index.html").exists():
        print("  ! frontend/dist is missing. Build it with: cd frontend && npm install && npm run build")
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"  Open {url}")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
