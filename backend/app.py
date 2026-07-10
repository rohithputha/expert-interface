from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from db import get_repository
from rubric import RUBRIC


PORT = int(os.environ.get("PORT", "8787"))
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGIN.split(",") if origin.strip()]


class ApiHandler(BaseHTTPRequestHandler):
    repo = get_repository()

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"ok": True})
            return

        if path == "/api/rubric":
            self._send_json({"rubric": RUBRIC})
            return

        if path == "/api/calls":
            status = _first(query.get("status"))
            self._send_json({"calls": self.repo.list_calls(status=status)})
            return

        if path.startswith("/api/calls/"):
            call_id = path.split("/", 3)[-1]
            call = self.repo.get_call(call_id)
            if not call:
                self._send_json({"error": "Call not found"}, status=404)
                return
            self._send_json({"call": call})
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/api/ratings":
            payload = self._read_json()
            required = {"call_id", "ratings", "evidence"}
            missing = sorted(required - set(payload))
            if missing:
                self._send_json({"error": "Missing required fields", "fields": missing}, status=400)
                return

            saved = self.repo.save_rating(payload)
            self._send_json({"rating": saved}, status=201)
            return

        self._send_json({"error": "Not found"}, status=404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._headers()
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers()
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _headers(self) -> None:
        self.send_header("access-control-allow-origin", self._cors_origin())
        self.send_header("vary", "Origin")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")

    def _cors_origin(self) -> str:
        request_origin = self.headers.get("origin")
        if "*" in ALLOWED_ORIGINS:
            return "*"
        if request_origin and request_origin in ALLOWED_ORIGINS:
            return request_origin
        return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def main() -> None:
    server = ThreadingHTTPServer(("", PORT), ApiHandler)
    print(f"Expert rating API listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
