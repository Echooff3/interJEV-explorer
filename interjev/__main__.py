"""Run with: python -m interjev"""

import os
from pathlib import Path


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


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    from .app import create_app

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"interJEV Explorer running at http://{host}:{port}")
    create_app().run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
