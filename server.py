#!/usr/bin/env python3
"""EA Dubai Community — single-page community wall.

Serves the page and its static assets, a small JSON API under /api/, and
owns the SQLite store. Python 3 standard library only.

Run: python3 server.py  ->  http://localhost:8000
"""

import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "data" / "community.db"

MAX_BODY_BYTES = 64 * 1024
MAX_FIELD_LEN = 120
MAX_EMAIL_LEN = 254
MAX_TESTIMONY_LEN = 500
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Exact-match path -> (file, mime) whitelist; any other path is a 404.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
API_PATHS = {"/api/testimonies", "/api/members"}
KNOWN_PATHS = set(STATIC_FILES) | API_PATHS

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT '',
  organization TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS testimonies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  member_id INTEGER NOT NULL UNIQUE REFERENCES members(id),
  text TEXT NOT NULL,
  submitted_at TEXT NOT NULL
);
"""

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


def _trim(value, limit):
    """Return value as a trimmed string capped at limit, '' for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def handle_register(body):
    """POST /api/members — insert a new member or refresh a returning one."""
    name = _trim(body.get("name"), MAX_FIELD_LEN + 1)
    title = _trim(body.get("title"), MAX_FIELD_LEN + 1)
    organization = _trim(body.get("organization"), MAX_FIELD_LEN + 1)
    email_raw = body.get("email")
    email = email_raw.strip().lower() if isinstance(email_raw, str) else ""

    if not name:
        return 400, {"error": "Full name is required."}
    if len(name) > MAX_FIELD_LEN:
        return 400, {"error": "Name must be 120 characters or fewer."}
    if not email or len(email) > MAX_EMAIL_LEN or not EMAIL_RE.match(email):
        return 400, {"error": "A valid email address is required."}
    if len(title) > MAX_FIELD_LEN or len(organization) > MAX_FIELD_LEN:
        return 400, {"error": "Job title and organization must be 120 characters or fewer."}

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM members WHERE email = ?", (email,)
        ).fetchone()
        if row is None:
            conn.execute(
                f"INSERT INTO members (name, email, title, organization, created_at)"
                f" VALUES (?, ?, ?, ?, {NOW})",
                (name, email, title, organization),
            )
            returning = False
        else:
            conn.execute(
                "UPDATE members SET name = ?, title = ?, organization = ? WHERE email = ?",
                (name, title, organization, email),
            )
            returning = True

    return 200, {
        "ok": True,
        "returning": returning,
        "member": {"name": name, "title": title, "organization": organization},
    }


def handle_testimony(body):
    """POST /api/testimonies — upsert the member's single testimony."""
    email_raw = body.get("email")
    email = email_raw.strip().lower() if isinstance(email_raw, str) else ""
    text_raw = body.get("text")
    text = text_raw.strip() if isinstance(text_raw, str) else ""

    if not text:
        return 400, {"error": "Your view cannot be empty."}
    if len(text) > MAX_TESTIMONY_LEN:
        return 400, {"error": "Your view must be 500 characters or fewer."}

    with sqlite3.connect(DB_PATH) as conn:
        member = conn.execute(
            "SELECT id, name, title, organization FROM members WHERE email = ?",
            (email,),
        ).fetchone()
        if member is None:
            return 400, {"error": "Please register before sharing your view."}
        member_id, name, title, organization = member
        conn.execute(
            f"INSERT INTO testimonies (member_id, text, submitted_at)"
            f" VALUES (?, ?, {NOW})"
            " ON CONFLICT(member_id) DO UPDATE SET"
            " text = excluded.text, submitted_at = excluded.submitted_at",
            (member_id, text),
        )
        submitted_at = conn.execute(
            "SELECT submitted_at FROM testimonies WHERE member_id = ?",
            (member_id,),
        ).fetchone()[0]

    return 200, {
        "ok": True,
        "testimony": {
            "name": name,
            "title": title,
            "organization": organization,
            "text": text,
            "submitted_at": submitted_at,
        },
    }


def list_testimonies():
    """GET /api/testimonies — every testimony, newest first."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT m.name, m.title, m.organization, t.text, t.submitted_at"
            " FROM testimonies t JOIN members m ON m.id = t.member_id"
            " ORDER BY t.submitted_at DESC, t.id DESC"
        ).fetchall()
    testimonies = [
        {
            "name": name,
            "title": title,
            "organization": organization,
            "text": text,
            "submitted_at": submitted_at,
        }
        for name, title, organization, text, submitted_at in rows
    ]
    return 200, {"count": len(testimonies), "testimonies": testimonies}


class CommunityHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- helpers ---------------------------------------------------------

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filename, mime):
        path = STATIC_DIR / filename
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(404, {"error": "not found"})
            return
        self.send_response(200)
        self._security_headers()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        """Parse the request body as a JSON object; returns (dict, error)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            return None, (400, {"error": "Request body too large."})
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, (400, {"error": "Request body must be valid JSON."})
        if not isinstance(body, dict):
            return None, (400, {"error": "Request body must be a JSON object."})
        return body, None

    def _reject(self):
        """Wrong method on a known path -> 405; anything else -> 404."""
        if self.path in KNOWN_PATHS:
            allowed = (
                "GET"
                if self.path in STATIC_FILES
                else "GET, POST"
                if self.path == "/api/testimonies"
                else "POST"
            )
            self.send_response(405)
            self._security_headers()
            self.send_header("Allow", allowed)
            body = json.dumps({"error": "method not allowed"}).encode("utf-8")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(404, {"error": "not found"})

    # --- routes ----------------------------------------------------------

    def do_GET(self):
        if self.path in STATIC_FILES:
            filename, mime = STATIC_FILES[self.path]
            self._send_file(filename, mime)
        elif self.path == "/api/testimonies":
            status, payload = list_testimonies()
            self._send_json(status, payload)
        elif self.path in KNOWN_PATHS:
            self._reject()
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/members":
            body, error = self._json_body()
            status, payload = error or handle_register(body)
            self._send_json(status, payload)
        elif self.path == "/api/testimonies":
            body, error = self._json_body()
            status, payload = error or handle_testimony(body)
            self._send_json(status, payload)
        elif self.path in KNOWN_PATHS:
            self._reject()
        else:
            self._send_json(404, {"error": "not found"})

    do_PUT = _reject
    do_PATCH = _reject
    do_DELETE = _reject
    do_HEAD = _reject


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CommunityHandler)
    print(f"EA Dubai Community running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
