#!/usr/bin/env python3
"""Railway KMac Vault — encrypted key-value store for secrets.

Runs on Railway. Values are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
in a SQLite database stored on a Railway volume.

Auth: Bearer token per caller, resolved to a scoped identity (see VAULT_TOKENS below).
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from collections import deque
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlsplit, unquote

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:
    print(
        "cryptography (Fernet) is required; install with: pip install cryptography",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

# Railway configuration
DB_PATH = os.getenv("VAULT_DB_PATH", "/vault/data/secrets.db")
PORT = int(os.getenv("PORT", 9999))
MAX_BODY_BYTES = 64 * 1024
RATE_WINDOW_SEC = 60.0
RATE_MAX_PER_WINDOW = 100
MAX_AUDIT_LIMIT = 500

# Number of trusted reverse-proxy hops in front of this server (Railway's edge = 1).
# Only the hop our own infrastructure appended to X-Forwarded-For is trusted; anything
# a client prepends ahead of that is attacker-controlled and ignored.
TRUSTED_PROXY_HOPS = max(1, int(os.getenv("VAULT_TRUSTED_PROXY_HOPS", "1")))

# CORS is off by default: this is a server-to-server secrets API, not a browser API.
ALLOW_CORS = os.getenv("VAULT_ALLOW_CORS", "false").strip().lower() == "true"

_ip_request_times: dict[str, deque[float]] = {}


def _rate_limit_allow(client_ip: str) -> bool:
    now = time.monotonic()
    q = _ip_request_times.setdefault(client_ip, deque())
    while q and q[0] < now - RATE_WINDOW_SEC:
        q.popleft()
    if len(_ip_request_times) > 10_000:
        oldest = sorted(
            _ip_request_times.keys(),
            key=lambda k: _ip_request_times[k][-1] if _ip_request_times[k] else 0,
        )
        for k in oldest[: len(_ip_request_times) - 5000]:
            del _ip_request_times[k]
    if len(q) >= RATE_MAX_PER_WINDOW:
        return False
    q.append(now)
    return True


# ---------------------------------------------------------------------------
# Encryption: the data-encryption key is independent of any auth token, so
# rotating a bearer token (or adding/removing apps) never affects existing
# ciphertext, and compromise of the auth token model does not by itself
# imply knowledge of the encryption key.
# ---------------------------------------------------------------------------

def _load_master_key() -> bytes:
    raw = os.getenv("VAULT_MASTER_KEY")
    if not raw:
        print(
            "FATAL: VAULT_MASTER_KEY is not set. Generate one with:\n"
            "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "and set it as the VAULT_MASTER_KEY environment variable. "
            "The server will not auto-generate or guess a key.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    key = raw.strip().encode()
    try:
        Fernet(key)
    except Exception as exc:
        print(f"FATAL: VAULT_MASTER_KEY is not a valid Fernet key: {exc}", file=sys.stderr)
        raise SystemExit(1)
    return key


_MASTER_KEY: bytes = _load_master_key()
_FERNET = Fernet(_MASTER_KEY)


def _encrypt(plaintext: str) -> str:
    return _FERNET.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _FERNET.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Identity / auth: each caller gets its own token, scoped to a key prefix.
# An "admin" identity is unscoped and can also read the audit log and
# per-key history. There is no silent auto-generated fallback token: missing
# configuration is a fatal startup error, not a runtime surprise logged in
# plaintext.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Identity:
    name: str
    token: str
    admin: bool
    prefix: str

    def can_access(self, key: str) -> bool:
        return self.admin or key.startswith(self.prefix)


def _load_identities() -> dict[str, Identity]:
    identities: dict[str, Identity] = {}

    raw_tokens = os.getenv("VAULT_TOKENS")
    if raw_tokens:
        try:
            cfg = json.loads(raw_tokens)
        except json.JSONDecodeError as exc:
            print(f"FATAL: VAULT_TOKENS is not valid JSON: {exc}", file=sys.stderr)
            raise SystemExit(1)
        if not isinstance(cfg, dict):
            print("FATAL: VAULT_TOKENS must be a JSON object of name -> {token, admin?, prefix?}", file=sys.stderr)
            raise SystemExit(1)
        for name, entry in cfg.items():
            if not isinstance(entry, dict) or not entry.get("token"):
                print(f"FATAL: VAULT_TOKENS entry '{name}' must be an object with a 'token' field", file=sys.stderr)
                raise SystemExit(1)
            is_admin = bool(entry.get("admin", False))
            prefix = entry.get("prefix", f"{name}:")
            identities[name] = Identity(
                name=name, token=str(entry["token"]).strip(), admin=is_admin, prefix=str(prefix)
            )

    legacy_token = os.getenv("VAULT_TOKEN")
    if legacy_token:
        if "legacy-admin" not in identities:
            identities["legacy-admin"] = Identity(
                name="legacy-admin", token=legacy_token.strip(), admin=True, prefix=""
            )
        print(
            "WARNING: VAULT_TOKEN is deprecated and grants unscoped admin access to every "
            "secret. Migrate callers to per-app entries in VAULT_TOKENS and remove VAULT_TOKEN.",
            file=sys.stderr,
        )

    if not identities:
        print(
            "FATAL: no auth configured. Set VAULT_TOKENS (recommended, per-app scoped tokens) "
            "or VAULT_TOKEN (deprecated, unscoped admin). The server will not start with no "
            "auth and will not generate a token for you.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return identities


_IDENTITIES: dict[str, Identity] = _load_identities()


def _resolve_identity(token: str) -> Optional[Identity]:
    if not token:
        return None
    match: Optional[Identity] = None
    for identity in _IDENTITIES.values():
        if hmac.compare_digest(token.encode("utf-8", "ignore"), identity.token.encode("utf-8", "ignore")):
            match = identity
    return match


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS secrets (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            deleted_at TIMESTAMP
        )
        """
    )
    # Upgrade path for databases created by older versions of this server.
    for ddl in (
        "ALTER TABLE secrets ADD COLUMN updated_by TEXT",
        "ALTER TABLE secrets ADD COLUMN deleted_at TIMESTAMP",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS secret_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_secret_history_key ON secret_history(key)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            key TEXT,
            status TEXT NOT NULL,
            client_ip TEXT
        )
        """
    )
    conn.commit()
    return conn


# NOTE: the server intentionally stays single-threaded (HTTPServer, not
# ThreadingHTTPServer / socketserver.ThreadingMixIn). The single sqlite3
# connection below is not shared safely across threads; if this is ever
# made concurrent, give each worker its own connection (or a connection
# pool) and wrap writes in a lock/transaction.
_db = _init_db()


def _audit(actor: str, action: str, key: Optional[str], status: str, client_ip: str) -> None:
    _db.execute(
        "INSERT INTO audit_log (actor, action, key, status, client_ip) VALUES (?, ?, ?, ?, ?)",
        (actor, action, key, status, client_ip),
    )
    _db.commit()


def _record_history(key: str, prior_encrypted_value: str, action: str, actor: str) -> None:
    _db.execute(
        "INSERT INTO secret_history (key, value, action, actor) VALUES (?, ?, ?, ?)",
        (key, prior_encrypted_value, action, actor),
    )


class VaultHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Log to stdout for Railway logs
        timestamp = self.log_date_time_string()
        print(f"{timestamp} {format % args}")

    def _client_ip(self) -> str:
        peer = self.client_address[0] if self.client_address else "unknown"
        forwarded = self.headers.get("X-Forwarded-For")
        if not forwarded:
            return peer
        hops = [p.strip() for p in forwarded.split(",") if p.strip()]
        if not hops:
            return peer
        # The entry appended by *our* trusted proxy is the one `TRUSTED_PROXY_HOPS`
        # from the right. Anything further left (closer to the front of the list)
        # may have been set by the client itself and must not be trusted.
        idx = len(hops) - TRUSTED_PROXY_HOPS
        if 0 <= idx < len(hops):
            return hops[idx]
        return hops[0]

    def _identity(self) -> Optional[Identity]:
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            return None
        return _resolve_identity(token)

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if ALLOW_CORS:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length > MAX_BODY_BYTES:
            return None
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if len(raw) != length:
            return {}
        try:
            return json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _content_length_allowed(self) -> bool:
        cl = self.headers.get("Content-Length")
        if cl is None or cl == "":
            return True
        try:
            if int(cl) > MAX_BODY_BYTES:
                self._json_response({"error": "payload too large"}, 413)
                return False
        except ValueError:
            self._json_response({"error": "invalid Content-Length"}, 400)
            return False
        return True

    def _preflight(self) -> bool:
        if not self._content_length_allowed():
            return False
        if not _rate_limit_allow(self._client_ip()):
            self._json_response({"error": "rate limited"}, 429)
            return False
        return True

    def _path_and_key(self, prefix: str) -> str:
        """Extract and normalize the key segment after a fixed route prefix."""
        path = urlsplit(self.path).path  # drop any query string
        return unquote(path[len(prefix):])

    def _require_identity(self) -> Optional[Identity]:
        identity = self._identity()
        if identity is None:
            self._audit("unknown", "auth", None, "unauthorized", self._client_ip())
            self._json_response({"error": "unauthorized"}, 401)
            return None
        return identity

    def _audit(self, actor: str, action: str, key: Optional[str], status: str, client_ip: str) -> None:
        _audit(actor, action, key, status, client_ip)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        if ALLOW_CORS:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._preflight():
            return

        path = urlsplit(self.path).path

        if path == "/health" or path == "/":
            self._json_response({"ok": True, "backend": "railway", "version": "1.1.0"})
            return

        identity = self._require_identity()
        if identity is None:
            return

        if path.startswith("/get/"):
            key = self._path_and_key("/get/")
            if not identity.can_access(key):
                self._audit(identity.name, "get", key, "forbidden", self._client_ip())
                self._json_response({"error": "forbidden"}, 403)
                return
            row = _db.execute(
                "SELECT value FROM secrets WHERE key = ? AND deleted_at IS NULL", (key,)
            ).fetchone()
            if row:
                try:
                    val = _decrypt(row[0])
                    self._audit(identity.name, "get", key, "ok", self._client_ip())
                    self._json_response({"key": key, "value": val})
                except InvalidToken:
                    self._audit(identity.name, "get", key, "decrypt_failed", self._client_ip())
                    self._json_response({"error": "decryption failed"}, 500)
            else:
                self._audit(identity.name, "get", key, "not_found", self._client_ip())
                self._json_response({"error": "not found"}, 404)

        elif path == "/list":
            if identity.admin:
                rows = _db.execute(
                    "SELECT key FROM secrets WHERE deleted_at IS NULL ORDER BY key"
                ).fetchall()
            else:
                rows = _db.execute(
                    "SELECT key FROM secrets WHERE deleted_at IS NULL AND key LIKE ? ORDER BY key",
                    (identity.prefix.replace("%", "\\%").replace("_", "\\_") + "%",),
                ).fetchall()
            self._audit(identity.name, "list", None, "ok", self._client_ip())
            self._json_response({"keys": [r[0] for r in rows]})

        elif path.startswith("/has/"):
            key = self._path_and_key("/has/")
            if not identity.can_access(key):
                self._json_response({"error": "forbidden"}, 403)
                return
            row = _db.execute(
                "SELECT 1 FROM secrets WHERE key = ? AND deleted_at IS NULL", (key,)
            ).fetchone()
            self._json_response({"exists": row is not None})

        elif path.startswith("/history/"):
            key = self._path_and_key("/history/")
            if not identity.admin and not identity.can_access(key):
                self._json_response({"error": "forbidden"}, 403)
                return
            rows = _db.execute(
                "SELECT action, actor, at FROM secret_history WHERE key = ? ORDER BY id DESC LIMIT 100",
                (key,),
            ).fetchall()
            self._audit(identity.name, "history", key, "ok", self._client_ip())
            self._json_response(
                {"key": key, "history": [{"action": a, "actor": b, "at": c} for a, b, c in rows]}
            )

        elif path == "/admin/audit":
            if not identity.admin:
                self._json_response({"error": "forbidden"}, 403)
                return
            query = urlsplit(self.path).query
            limit = 100
            for part in query.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = min(MAX_AUDIT_LIMIT, max(1, int(part[len("limit="):])))
                    except ValueError:
                        pass
            rows = _db.execute(
                "SELECT at, actor, action, key, status, client_ip FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            self._json_response(
                {
                    "entries": [
                        {"at": a, "actor": b, "action": c, "key": d, "status": e, "client_ip": f}
                        for a, b, c, d, e, f in rows
                    ]
                }
            )

        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if not self._preflight():
            return

        identity = self._require_identity()
        if identity is None:
            return

        path = urlsplit(self.path).path

        if path == "/set":
            body = self._read_body()
            if body is None:
                self._json_response({"error": "body too large or invalid"}, 413)
                return
            key = body.get("key", "")
            value = body.get("value", "")
            if not isinstance(key, str) or not isinstance(value, str) or not key or not value:
                self._json_response({"error": "key and value required and must be strings"}, 400)
                return
            if not identity.can_access(key):
                self._audit(identity.name, "set", key, "forbidden", self._client_ip())
                self._json_response({"error": "forbidden"}, 403)
                return

            existing = _db.execute("SELECT value FROM secrets WHERE key = ?", (key,)).fetchone()
            if existing:
                _record_history(key, existing[0], "overwrite", identity.name)

            encrypted = _encrypt(value)
            _db.execute(
                """
                INSERT INTO secrets (key, value, updated_at, updated_by, deleted_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, NULL)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = excluded.updated_by,
                    deleted_at = NULL
                """,
                (key, encrypted, identity.name),
            )
            _db.commit()
            self._audit(identity.name, "set", key, "ok", self._client_ip())
            self._json_response({"ok": True, "key": key})

        elif path.startswith("/delete/"):
            key = self._path_and_key("/delete/")
            if not identity.can_access(key):
                self._audit(identity.name, "delete", key, "forbidden", self._client_ip())
                self._json_response({"error": "forbidden"}, 403)
                return
            row = _db.execute(
                "SELECT value FROM secrets WHERE key = ? AND deleted_at IS NULL", (key,)
            ).fetchone()
            if not row:
                self._json_response({"error": "not found"}, 404)
                return
            _record_history(key, row[0], "delete", identity.name)
            _db.execute(
                "UPDATE secrets SET deleted_at = CURRENT_TIMESTAMP, updated_by = ? WHERE key = ?",
                (identity.name, key),
            )
            _db.commit()
            self._audit(identity.name, "delete", key, "ok", self._client_ip())
            self._json_response({"ok": True, "key": key})

        elif path.startswith("/undelete/"):
            key = self._path_and_key("/undelete/")
            if not identity.can_access(key):
                self._json_response({"error": "forbidden"}, 403)
                return
            row = _db.execute(
                "SELECT 1 FROM secrets WHERE key = ? AND deleted_at IS NOT NULL", (key,)
            ).fetchone()
            if not row:
                self._json_response({"error": "not found or not deleted"}, 404)
                return
            _db.execute(
                "UPDATE secrets SET deleted_at = NULL, updated_by = ? WHERE key = ?",
                (identity.name, key),
            )
            _db.commit()
            self._audit(identity.name, "undelete", key, "ok", self._client_ip())
            self._json_response({"ok": True, "key": key})

        else:
            self._json_response({"error": "not found"}, 404)

    def do_DELETE(self):
        self.do_POST()


if __name__ == "__main__":
    print("=" * 60)
    print("Railway KMac Vault")
    print("=" * 60)
    print(f"  Port:            {PORT}")
    print(f"  Database:        {DB_PATH}")
    print(f"  Identities:      {', '.join(sorted(_IDENTITIES)) or 'NONE'}")
    print(f"  Encryption:      Fernet (AES-128-CBC + HMAC-SHA256), key independent of auth tokens")
    print(f"  Rate limit:      {RATE_MAX_PER_WINDOW} req/{RATE_WINDOW_SEC}s per IP (trusted proxy hops: {TRUSTED_PROXY_HOPS})")
    print(f"  CORS:            {'enabled (*)' if ALLOW_CORS else 'disabled'}")
    print("=" * 60)
    print()

    # Bind to 0.0.0.0 for Railway (not 127.0.0.1)
    server = HTTPServer(("0.0.0.0", PORT), VaultHandler)
    print(f"✅ Server listening on 0.0.0.0:{PORT}")
    print(f"📡 Health: http://localhost:{PORT}/health")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
