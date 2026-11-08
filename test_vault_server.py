#!/usr/bin/env python3
"""
Integration tests for vault_server.py.

Starts a real instance of the server (HTTPServer) in a background thread on
an ephemeral port, against a temp sqlite file, then exercises it over HTTP.

Run:
    pip install requests
    python3 -m unittest test_vault_server.py -v
"""

import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest

import requests
from cryptography.fernet import Fernet


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class VaultServerTestCase(unittest.TestCase):
    """Boots one server per test class with a fixed identity config."""

    ADMIN_TOKEN = "admin-token-abc123"
    ADAJOON_TOKEN = "adajoon-token-xyz789"
    INFOBANK_TOKEN = "infobank-token-qqq111"

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="vault-test-")
        cls.db_path = os.path.join(cls.tmpdir, "secrets.db")
        cls.port = _free_port()

        os.environ["VAULT_DB_PATH"] = cls.db_path
        os.environ["PORT"] = str(cls.port)
        os.environ["VAULT_MASTER_KEY"] = Fernet.generate_key().decode()
        os.environ["VAULT_TOKENS"] = json.dumps(
            {
                "admin": {"token": cls.ADMIN_TOKEN, "admin": True},
                "adajoon": {"token": cls.ADAJOON_TOKEN},
                "infobank": {"token": cls.INFOBANK_TOKEN},
            }
        )
        os.environ.pop("VAULT_TOKEN", None)
        os.environ["VAULT_TRUSTED_PROXY_HOPS"] = "1"

        # The sqlite3 connection vault_server opens at import time is bound to
        # whichever thread imports/reloads the module (check_same_thread=True,
        # the default). serve_forever() must then run requests on that same
        # thread, so do the (re)import and the serve loop in one background
        # thread rather than importing here and serving elsewhere.
        ready = threading.Event()
        cls.server_holder: list = []

        def _run():
            import importlib
            import vault_server as vs

            importlib.reload(vs)
            cls.vs = vs
            server = vs.HTTPServer(("127.0.0.1", cls.port), vs.VaultHandler)
            cls.server_holder.append(server)
            ready.set()
            server.serve_forever()

        cls.thread = threading.Thread(target=_run, daemon=True)
        cls.thread.start()
        ready.wait(timeout=5)
        cls.server = cls.server_holder[0]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                requests.get(f"{cls.base_url}/health", timeout=1)
                break
            except requests.exceptions.ConnectionError:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _hdr(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_health_requires_no_auth(self):
        r = requests.get(f"{self.base_url}/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_unauthenticated_request_rejected(self):
        r = requests.get(f"{self.base_url}/get/adajoon:db_url")
        self.assertEqual(r.status_code, 401)

    def test_wrong_token_rejected(self):
        r = requests.get(f"{self.base_url}/get/adajoon:db_url", headers=self._hdr("not-a-real-token"))
        self.assertEqual(r.status_code, 401)

    def test_admin_set_and_get(self):
        r = requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADMIN_TOKEN),
            json={"key": "adajoon:db_url", "value": "postgres://x"},
        )
        self.assertEqual(r.status_code, 200)
        r = requests.get(f"{self.base_url}/get/adajoon:db_url", headers=self._hdr(self.ADMIN_TOKEN))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["value"], "postgres://x")

    def test_scoped_token_can_write_own_prefix(self):
        r = requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:api_key", "value": "sk_test_123"},
        )
        self.assertEqual(r.status_code, 200)
        r = requests.get(f"{self.base_url}/get/adajoon:api_key", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.json()["value"], "sk_test_123")

    def test_scoped_token_cannot_write_other_prefix(self):
        r = requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "infobank:secret", "value": "leak-attempt"},
        )
        self.assertEqual(r.status_code, 403)

    def test_scoped_token_cannot_read_other_prefix(self):
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.INFOBANK_TOKEN),
            json={"key": "infobank:stripe_secret", "value": "sk_live_shh"},
        )
        r = requests.get(
            f"{self.base_url}/get/infobank:stripe_secret", headers=self._hdr(self.ADAJOON_TOKEN)
        )
        self.assertEqual(r.status_code, 403)

    def test_list_is_scoped_for_non_admin(self):
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:another_key", "value": "v"},
        )
        r = requests.get(f"{self.base_url}/list", headers=self._hdr(self.ADAJOON_TOKEN))
        keys = r.json()["keys"]
        self.assertTrue(all(k.startswith("adajoon:") for k in keys))
        self.assertNotIn("infobank:stripe_secret", keys)

    def test_list_is_unscoped_for_admin(self):
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.INFOBANK_TOKEN),
            json={"key": "infobank:unscoped_probe", "value": "v"},
        )
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:unscoped_probe", "value": "v"},
        )
        r = requests.get(f"{self.base_url}/list", headers=self._hdr(self.ADMIN_TOKEN))
        keys = r.json()["keys"]
        self.assertIn("infobank:unscoped_probe", keys)
        self.assertIn("adajoon:unscoped_probe", keys)

    def test_delete_is_soft_and_recoverable(self):
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:temp", "value": "to-delete"},
        )
        r = requests.post(f"{self.base_url}/delete/adajoon:temp", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.status_code, 200)

        r = requests.get(f"{self.base_url}/get/adajoon:temp", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.status_code, 404)

        # Row must still exist underneath (soft delete), recoverable via undelete.
        r = requests.post(f"{self.base_url}/undelete/adajoon:temp", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.status_code, 200)
        r = requests.get(f"{self.base_url}/get/adajoon:temp", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["value"], "to-delete")

    def test_overwrite_recorded_in_history(self):
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:versioned", "value": "v1"},
        )
        requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:versioned", "value": "v2"},
        )
        r = requests.get(f"{self.base_url}/history/adajoon:versioned", headers=self._hdr(self.ADMIN_TOKEN))
        self.assertEqual(r.status_code, 200)
        actions = [h["action"] for h in r.json()["history"]]
        self.assertIn("overwrite", actions)

    def test_history_forbidden_for_other_scoped_token(self):
        r = requests.get(
            f"{self.base_url}/history/infobank:stripe_secret", headers=self._hdr(self.ADAJOON_TOKEN)
        )
        self.assertEqual(r.status_code, 403)

    def test_admin_audit_log_requires_admin(self):
        r = requests.get(f"{self.base_url}/admin/audit", headers=self._hdr(self.ADAJOON_TOKEN))
        self.assertEqual(r.status_code, 403)

    def test_admin_audit_log_records_activity(self):
        requests.get(f"{self.base_url}/get/adajoon:db_url", headers=self._hdr(self.ADAJOON_TOKEN))
        r = requests.get(f"{self.base_url}/admin/audit?limit=5", headers=self._hdr(self.ADMIN_TOKEN))
        self.assertEqual(r.status_code, 200)
        entries = r.json()["entries"]
        self.assertTrue(len(entries) > 0)
        self.assertIn("actor", entries[0])

    def test_no_cors_headers_by_default(self):
        r = requests.get(f"{self.base_url}/health")
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)

    def test_xff_leftmost_entries_are_ignored_for_rate_limit_identity(self):
        # With TRUSTED_PROXY_HOPS=1, only the *last* entry in X-Forwarded-For is
        # trusted as the real peer; attacker-supplied earlier entries must not
        # let a single client masquerade as unlimited distinct IPs.
        ip_seen = []
        orig = self.vs.VaultHandler._client_ip

        def spy(self):
            ip = orig(self)
            ip_seen.append(ip)
            return ip

        self.vs.VaultHandler._client_ip = spy
        try:
            for i in range(3):
                requests.get(
                    f"{self.base_url}/health",
                    headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"},
                )
        finally:
            self.vs.VaultHandler._client_ip = orig

        # All requests should resolve to the same trusted (rightmost) hop,
        # regardless of the spoofed leftmost value.
        self.assertTrue(all(ip == "203.0.113.9" for ip in ip_seen), ip_seen)

    def test_type_validation_on_set(self):
        r = requests.post(
            f"{self.base_url}/set",
            headers=self._hdr(self.ADAJOON_TOKEN),
            json={"key": "adajoon:bad", "value": 12345},
        )
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
