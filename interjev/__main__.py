"""Run with: python -m interjev [--capture] [--dev]"""

import argparse
import os
from pathlib import Path

from .recorder import capture_enabled


def load_dotenv(path: Path) -> None:
    """Minimal .env loader so there's no extra dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def serve_gunicorn(host: str, port: int) -> None:
    from gunicorn.app.base import BaseApplication

    class Server(BaseApplication):
        def load_config(self):
            # One worker: the page cache and site memory live in-process.
            # Threads let many pages stream at once.
            self.cfg.set("bind", f"{host}:{port}")
            self.cfg.set("workers", 1)
            self.cfg.set("worker_class", "gthread")
            self.cfg.set("threads", int(os.environ.get("THREADS", "32")))
            self.cfg.set("timeout", 300)

        def load(self):
            # Built inside the worker so the recorder's DB thread survives the fork.
            from .app import create_app

            return create_app()

    Server().run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m interjev", description="interJEV Explorer")
    parser.add_argument("--capture", action="store_true",
                        help="record searches and generated pages to Postgres (needs DATABASE_URL)")
    parser.add_argument("--dev", action="store_true", help="use Flask's development server")
    args = parser.parse_args()

    load_dotenv(Path.cwd() / ".env")
    if args.capture:
        os.environ["JEV_CAPTURE"] = "1"

    # Railway (and most hosts) set PORT and need us listening on all interfaces.
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    capture = "Postgres" if capture_enabled() else "console"
    print(f"interJEV Explorer running at http://{host}:{port} (recording to {capture})", flush=True)

    if args.dev or os.name == "nt":  # gunicorn doesn't run on Windows
        from .app import create_app

        create_app().run(host=host, port=port, threaded=True)
    else:
        serve_gunicorn(host, port)


if __name__ == "__main__":
    main()
