from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from db import get_repository
from rubric import RUBRIC


PORT = int(os.environ.get("PORT", "8787"))
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGIN.split(",") if origin.strip()]
GCS_AUDIO_BUCKET = os.environ.get("GCS_AUDIO_BUCKET", "").strip()
GCS_AUDIO_OBJECT_TEMPLATE = os.environ.get("GCS_AUDIO_OBJECT_TEMPLATE", "{call_id}.redacted.wav")
HIDDEN_PAGE_IDS = {"workflow_adherence"}


class ApiHandler(BaseHTTPRequestHandler):
    repo = get_repository()
    repo.sync_pages([page for page in RUBRIC if page.get("id") not in HIDDEN_PAGE_IDS])

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
            user_id = _first(query.get("user_id"))
            self._send_json({"calls": self.repo.list_calls(user_id=user_id, status=status)})
            return

        audio_match = re.match(r"^/api/calls/([^/]+)/audio$", path)
        if audio_match:
            self._send_audio(audio_match.group(1))
            return

        if path.startswith("/api/calls/"):
            call_id = path.split("/", 3)[-1]
            user_id = _first(query.get("user_id"))
            call = self.repo.get_call(call_id, user_id=user_id)
            if not call:
                self._send_json({"error": "Call not found"}, status=404)
                return
            self._send_json({"call": call})
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/api/login":
            payload = self._read_json()
            email = str(payload.get("email") or payload.get("name") or "").strip()
            password = str(payload.get("password") or payload.get("passcode") or "").strip()
            if not email:
                self._send_json({"error": "Email is required"}, status=400)
                return
            reviewer = self.repo.authenticate_reviewer(email, password)
            if not reviewer:
                self._send_json({"error": "Invalid email or password"}, status=401)
                return
            self._send_json({"reviewer": reviewer})
            return

        if parsed.path.rstrip("/") == "/api/ratings":
            payload = self._read_json()
            required = {"user_id", "call_id", "ratings", "evidence"}
            missing = sorted(required - set(payload))
            if missing:
                self._send_json({"error": "Missing required fields", "fields": missing}, status=400)
                return

            try:
                saved = self.repo.save_rating(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
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

    def _send_audio(self, call_id: str) -> None:
        if not GCS_AUDIO_BUCKET:
            self._send_json({"error": "GCS audio bucket is not configured"}, status=404)
            return
        try:
            from google.cloud import storage  # type: ignore
        except ImportError:
            self._send_json({"error": "google-cloud-storage is not installed"}, status=500)
            return

        object_name = GCS_AUDIO_OBJECT_TEMPLATE.format(call_id=call_id)
        try:
            blob = storage.Client().bucket(GCS_AUDIO_BUCKET).blob(object_name)
            blob.reload()
        except Exception as exc:
            print(f"Could not load GCS audio object {GCS_AUDIO_BUCKET}/{object_name}: {exc}")
            self._send_json({"error": "Audio not found"}, status=404)
            return

        size = int(blob.size or 0)
        start, end = _range_bounds(self.headers.get("range"), size)
        try:
            audio = blob.download_as_bytes(start=start, end=end)
        except Exception as exc:
            print(f"Could not download GCS audio object {GCS_AUDIO_BUCKET}/{object_name}: {exc}")
            self._send_json({"error": "Audio download failed"}, status=502)
            return

        if start is not None or end is not None:
            actual_start = start or 0
            actual_end = end if end is not None else size - 1
            self.send_response(206)
            self._headers()
            self.send_header("content-range", f"bytes {actual_start}-{actual_end}/{size}")
        else:
            self.send_response(200)
            self._headers()
        self.send_header("content-type", blob.content_type or "audio/wav")
        self.send_header("accept-ranges", "bytes")
        self.send_header("content-length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def _headers(self) -> None:
        self.send_header("access-control-allow-origin", self._cors_origin())
        self.send_header("vary", "Origin")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.send_header("access-control-allow-headers", "content-type,range")
        self.send_header("access-control-expose-headers", "accept-ranges,content-length,content-range")

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


def _range_bounds(header: str | None, size: int) -> tuple[int | None, int | None]:
    if not header or not header.startswith("bytes=") or size <= 0:
        return None, None
    start_raw, _, end_raw = header.removeprefix("bytes=").partition("-")
    try:
        if start_raw:
            start = max(0, int(start_raw))
            end = min(size - 1, int(end_raw)) if end_raw else size - 1
        else:
            suffix = max(0, int(end_raw))
            start = max(0, size - suffix)
            end = size - 1
    except ValueError:
        return None, None
    if start > end or start >= size:
        return None, None
    return start, end


def main() -> None:
    server = ThreadingHTTPServer(("", PORT), ApiHandler)
    print(f"Expert rating API listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
