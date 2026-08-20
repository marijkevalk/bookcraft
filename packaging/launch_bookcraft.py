"""Entry point for the double-click Bookcraft bundle.

Opens the local web UI in the browser and keeps serving until the window is
closed. This is what a PyInstaller-built .exe/.app runs — see bookcraft.spec.
"""

from __future__ import annotations

import threading
import webbrowser

from bookcraft.webui import create_app

HOST = "127.0.0.1"
PORT = 8765


def main() -> None:
    url = f"http://{HOST}:{PORT}/"
    print(f"Bookcraft is running at {url}")
    print("Leave this window open while you work; close it to stop.")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    create_app().run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()
