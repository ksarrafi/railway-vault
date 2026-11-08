#!/usr/bin/env python3
"""
One-time migration for existing Railway KMac Vault deployments.

Versions before 1.1.0 derived the encryption key from VAULT_TOKEN itself
(PBKDF2(VAULT_TOKEN, salt_file)). 1.1.0 uses an independent VAULT_MASTER_KEY
so that rotating a caller's token no longer breaks decryption of existing
secrets. Run this ONCE, offline, before switching a deployment to the new
server code, to re-encrypt existing rows under the new key.

Usage:
    export OLD_VAULT_TOKEN="<the VAULT_TOKEN this deployment used before>"
    export VAULT_MASTER_KEY="<new key, e.g. from Fernet.generate_key()>"
    export VAULT_DB_PATH="/vault/data/secrets.db"   # same path the server uses

    python3 migrate_encryption.py

This connects to the sqlite file directly (the server must be stopped) and
rewrites the `value` column of every row in `secrets`, in place. Make a copy
of the database file before running this if you want a rollback point.
"""

import base64
import hashlib
import os
import sqlite3
import sys

from cryptography.fernet import Fernet


def _old_key(old_token: str, db_path: str) -> bytes:
    salt_path = db_path + ".salt"
    if not os.path.exists(salt_path):
        print(f"FATAL: old salt file not found at {salt_path}", file=sys.stderr)
        sys.exit(1)
    with open(salt_path, "rb") as f:
        salt = f.read()
    key = hashlib.pbkdf2_hmac("sha256", old_token.encode(), salt, 200_000)
    return base64.urlsafe_b64encode(key[:32])


def main() -> None:
    old_token = os.getenv("OLD_VAULT_TOKEN")
    new_key_raw = os.getenv("VAULT_MASTER_KEY")
    db_path = os.getenv("VAULT_DB_PATH", "/vault/data/secrets.db")

    if not old_token or not new_key_raw:
        print("FATAL: set OLD_VAULT_TOKEN and VAULT_MASTER_KEY", file=sys.stderr)
        sys.exit(1)

    old_fernet = Fernet(_old_key(old_token, db_path))
    new_fernet = Fernet(new_key_raw.strip().encode())

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT key, value FROM secrets").fetchall()
    print(f"Found {len(rows)} rows to re-encrypt.")

    migrated, failed = 0, 0
    for key, old_ciphertext in rows:
        try:
            plaintext = old_fernet.decrypt(old_ciphertext.encode())
        except Exception as exc:
            print(f"❌ Could not decrypt {key} with OLD_VAULT_TOKEN: {exc}", file=sys.stderr)
            failed += 1
            continue
        new_ciphertext = new_fernet.encrypt(plaintext).decode()
        conn.execute("UPDATE secrets SET value = ? WHERE key = ?", (new_ciphertext, key))
        migrated += 1

    conn.commit()
    conn.close()

    print(f"✅ Migrated: {migrated}")
    if failed:
        print(f"❌ Failed:   {failed} (left unchanged — check OLD_VAULT_TOKEN / salt file)")
        sys.exit(1)
    print("Done. You can now deploy the new server with VAULT_MASTER_KEY and VAULT_TOKENS set.")


if __name__ == "__main__":
    main()
