from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.backup import create_verified_backup
from friendly_hub.main import create_app


def _open_browser_when_ready() -> None:
    health_url = "http://127.0.0.1:8765/api/v1/health"
    for _ in range(80):
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open("http://127.0.0.1:8765")
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)


def main() -> None:
    settings = RuntimeSettings.from_environment()
    backup = create_verified_backup(settings)
    if backup is not None:
        print(f"Safety backup verified: {backup.path}")
    browser_thread = threading.Thread(target=_open_browser_when_ready, daemon=True)
    browser_thread.start()
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=8765,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
