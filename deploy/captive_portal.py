"""Tiny captive-portal redirector for HauntOS hotspot mode.

This service listens on port 80 and redirects phones/tablets to the Flask UI on
port 5000. It is optional and only intended for Raspberry Pi hotspot installs.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os


PORT = int(os.environ.get("HAUNTOS_PORTAL_PORT", "80"))
TARGET = os.environ.get("HAUNTOS_PORTAL_TARGET", "http://192.168.4.1:5000")


class PortalHandler(BaseHTTPRequestHandler):
    """Redirect every HTTP request to the HauntOS UI."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._redirect()

    def log_message(self, format: str, *args) -> None:
        return

    def _redirect(self) -> None:
        self.send_response(302)
        self.send_header("Location", TARGET)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), PortalHandler)
    print(f"HauntOS captive portal redirecting port {PORT} to {TARGET}")
    server.serve_forever()


if __name__ == "__main__":
    main()
