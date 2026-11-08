#!/usr/bin/env python3
"""
Tests for the crypto-critical paths that test_vault_server.py doesn't cover:
startup failure modes (missing/malformed VAULT_MASTER_KEY, no auth configured)
and the migrate_encryption.py round-trip from the old token-derived key scheme.

Run:
    python3 -m unittest test_migration_and_startup.py -v
"""

import base64
import hashlib
import os
import subprocess
import sqlite3
import sys
import tempfile
import unittest

from cryptography.fernet import Fernet

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_server_once(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAULT_")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, os.path.join(REPO_DIR, "vault_server.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


class StartupFailureModeTests(unittest.TestCase):
    def test_fails_without_master_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_server_once(
                {
                    "VAULT_DB_PATH": os.path.join(tmp, "s.db"),
                    "VAULT_TOKENS": '{"admin":{"token":"x","admin":true}}',
                    "PORT": "0",
                }
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("VAULT_MASTER_KEY", result.stderr)

    def test_fails_with_malformed_master_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_server_once(
                {
                    "VAULT_DB_PATH": os.path.join(tmp, "s.db"),
                    "VAULT_MASTER_KEY": "not-a-real-fernet-key",
                    "VAULT_TOKENS": '{"admin":{"token":"x","admin":true}}',
                    "PORT": "0",
                }
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a valid Fernet key", result.stderr)

    def test_fails_without_any_auth_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_server_once(
                {
                    "VAULT_DB_PATH": os.path.join(tmp, "s.db"),
                    "VAULT_MASTER_KEY": Fernet.generate_key().decode(),
                    "PORT": "0",
                }
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no auth configured", result.stderr)

    def test_fails_on_duplicate_tokens_across_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_server_once(
                {
                    "VAULT_DB_PATH": os.path.join(tmp, "s.db"),
                    "VAULT_MASTER_KEY": Fernet.generate_key().decode(),
                    "VAULT_TOKENS": '{"a":{"token":"same"},"b":{"token":"same"}}',
                    "PORT": "0",
                }
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("share the same token", result.stderr)

    def test_fails_on_colliding_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_server_once(
                {
                    "VAULT_DB_PATH": os.path.join(tmp, "s.db"),
                    "VAULT_MASTER_KEY": Fernet.generate_key().decode(),
                    "VAULT_TOKENS": (
                        '{"stablebank":{"token":"t1","prefix":"stablebank"},'
                        '"stablebank-demo":{"token":"t2","prefix":"stablebank-demo:"}}'
                    ),
                    "PORT": "0",
                }
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("is a prefix of", result.stderr)


class MigrationRoundTripTests(unittest.TestCase):
    """Seed an old-format (pre-1.1.0) DB and verify migrate_encryption.py
    correctly re-encrypts it under a new, independent VAULT_MASTER_KEY."""

    def _old_key(self, old_token: str, db_path: str) -> bytes:
        salt_path = db_path + ".salt"
        salt = os.urandom(32)
        with open(salt_path, "wb") as f:
            f.write(salt)
        key = hashlib.pbkdf2_hmac("sha256", old_token.encode(), salt, 200_000)
        return base64.urlsafe_b64encode(key[:32])

    def test_migration_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "secrets.db")
            old_token = "old-shared-token-abc"
            old_fernet = Fernet(self._old_key(old_token, db_path))

            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE secrets (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            plaintext_by_key = {
                "adajoon:db_url": "postgres://old-scheme-secret",
                "infobank:api_key": "sk_old_scheme_123",
            }
            for key, plaintext in plaintext_by_key.items():
                conn.execute(
                    "INSERT INTO secrets (key, value) VALUES (?, ?)",
                    (key, old_fernet.encrypt(plaintext.encode()).decode()),
                )
            conn.commit()
            conn.close()

            new_master_key = Fernet.generate_key().decode()
            env = dict(os.environ)
            env["OLD_VAULT_TOKEN"] = old_token
            env["VAULT_MASTER_KEY"] = new_master_key
            env["VAULT_DB_PATH"] = db_path

            result = subprocess.run(
                [sys.executable, os.path.join(REPO_DIR, "migrate_encryption.py")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            new_fernet = Fernet(new_master_key.encode())
            conn = sqlite3.connect(db_path)
            rows = dict(conn.execute("SELECT key, value FROM secrets").fetchall())
            conn.close()

            for key, expected_plaintext in plaintext_by_key.items():
                decrypted = new_fernet.decrypt(rows[key].encode()).decode()
                self.assertEqual(decrypted, expected_plaintext)

            # Old key must no longer decrypt the (now re-encrypted) rows.
            with self.assertRaises(Exception):
                old_fernet.decrypt(rows["adajoon:db_url"].encode())

    def test_migration_rolls_back_on_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "secrets.db")
            old_token = "old-shared-token-abc"
            old_fernet = Fernet(self._old_key(old_token, db_path))
            wrong_fernet = Fernet(Fernet.generate_key())  # simulates a row from a different old key

            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE secrets (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO secrets (key, value) VALUES (?, ?)",
                ("good:key", old_fernet.encrypt(b"fine").decode()),
            )
            conn.execute(
                "INSERT INTO secrets (key, value) VALUES (?, ?)",
                ("bad:key", wrong_fernet.encrypt(b"undecryptable-with-old-token").decode()),
            )
            conn.commit()
            original_rows = dict(conn.execute("SELECT key, value FROM secrets").fetchall())
            conn.close()

            env = dict(os.environ)
            env["OLD_VAULT_TOKEN"] = old_token
            env["VAULT_MASTER_KEY"] = Fernet.generate_key().decode()
            env["VAULT_DB_PATH"] = db_path

            result = subprocess.run(
                [sys.executable, os.path.join(REPO_DIR, "migrate_encryption.py")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)

            conn = sqlite3.connect(db_path)
            rows_after = dict(conn.execute("SELECT key, value FROM secrets").fetchall())
            conn.close()
            # Nothing should have been written -- including the row that WOULD
            # have migrated successfully -- since the script rolls back as a unit.
            self.assertEqual(rows_after, original_rows)


if __name__ == "__main__":
    unittest.main()
