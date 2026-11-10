# Railway Vault v1.1.0 - Security Hardening

**Status:** Security/architecture update — **breaking change to configuration**

This release fixes a security review's findings against v1.0.0. It changes
how the vault is configured; existing deployments need the migration steps
below before upgrading.

---

## 🚨 Breaking changes

- **`VAULT_TOKEN` (single shared token) is deprecated.** Use `VAULT_TOKENS`,
  a JSON object giving each app its own token scoped to its own key prefix,
  plus one `admin` token with unscoped access. `VAULT_TOKEN` still works for
  backward compatibility but is unscoped (full admin) and logs a warning.
- **`VAULT_MASTER_KEY` is now required.** The encryption key used to be
  derived from `VAULT_TOKEN` itself; it's now independent, so rotating a
  token no longer breaks decryption of existing secrets. The server will
  not start without it, and will not auto-generate one.
- **Existing deployments must run `migrate_encryption.py` once**, offline,
  before switching to this version — it re-encrypts the database from the
  old token-derived key to the new independent `VAULT_MASTER_KEY`. See that
  script's docstring.
- **A real token value was found committed in `DEPLOYMENT_SUCCESS.md`,
  `INDEX.md`, and `ADAJOON_MIGRATION.md`** (introduced in the v1.0.0 docs
  commits). It has been redacted from those files, but anyone with access
  to the repo's git history has already seen it — **rotate it on the live
  service regardless of this release.**

## 🔒 Fixes

- **Per-app token scoping** — a leaked app token can no longer read, list,
  or modify another app's secrets (`vault_server.py`: `Identity.can_access`,
  prefix enforcement on `/get`, `/set`, `/delete`, `/undelete`, `/list`).
- **Encryption key decoupled from auth tokens** — see `VAULT_MASTER_KEY`
  above.
- **`X-Forwarded-For` spoofing fixed** — the rate limiter now trusts only
  the hop appended by Railway's own proxy (`VAULT_TRUSTED_PROXY_HOPS`,
  default 1), not an arbitrary client-supplied header value.
- **No more token auto-generation / plaintext logging** — missing auth
  config is now a fatal startup error instead of a silently generated,
  log-printed token that also changed (and broke decryption) on every
  restart.
- **Audit log** — every `get`/`set`/`delete`/`undelete`/`list`/auth failure
  is recorded with actor, key, status, timestamp, client IP (`audit_log`
  table, `GET /admin/audit`, admin-only).
- **Soft delete + version history** — `/delete` is reversible via
  `POST /undelete/:key`; every overwrite is recorded in `secret_history`
  and viewable via `GET /history/:key` (admin-only).
- **CORS disabled by default** — this is a server-to-server API; the
  wildcard `Access-Control-Allow-Origin: *` is now opt-in via
  `VAULT_ALLOW_CORS=true`.
- **Input validation** — `/set` now rejects non-string `key`/`value`
  instead of throwing an unhandled exception.

## 🔒 Fixes found in a second review pass of this same release

- **`X-Forwarded-For` trust now fails closed.** If `VAULT_TRUSTED_PROXY_HOPS`
  is configured higher than the number of hops actually present (e.g.
  misconfiguration), `_client_ip` previously fell back to the leftmost
  (attacker-controlled) entry — reopening the exact spoofing bug this
  release was meant to fix. It now falls back to the raw TCP peer address
  instead.
- **`/list` scoping rewritten to filter in Python**, using the same
  `Identity.can_access` every other route uses, instead of a separate SQL
  `LIKE` pattern. The `LIKE` version had two real bugs: it was
  case-insensitive while `can_access` is case-sensitive (letting
  differently-cased identities see each other's key names), and its
  "escaping" of `%`/`_` was a no-op (no `ESCAPE` clause), so an app whose
  name contained `_` — a very plausible real name — couldn't see its own
  keys.
- **Startup now validates `VAULT_TOKENS` more strictly**: rejects an empty
  prefix on a non-admin identity (which would otherwise grant unscoped
  access), rejects two identities sharing the same token, and rejects a
  custom prefix that is itself a prefix of another identity's prefix (e.g.
  `stablebank` vs `stablebank-demo`) instead of letting it through as a
  silent cross-tenant access path.
- **Audit log coverage completed.** `/has`, forbidden calls to `/history`
  and `/undelete`, not-found calls to `/delete` and `/undelete`, and
  invalid-input calls to `/set` are now all recorded — previously these
  paths were invisible in `/admin/audit`, so a probing/enumeration attempt
  using a stolen token could go unnoticed.
- **`_init_db`'s schema-upgrade step no longer swallows unrelated errors.**
  It previously caught any `sqlite3.OperationalError` when adding columns to
  an old-schema database; a locked DB, full disk, or permissions error would
  be silently discarded and only surface later as a confusing "no such
  column" error on the first request. It now only ignores the specific
  "duplicate column" case and re-raises everything else at startup.
- **`migrate_encryption.py` is now all-or-nothing.** It previously committed
  successfully-migrated rows even when others failed to decrypt under
  `OLD_VAULT_TOKEN`; a deploy pipeline that didn't check its exit code could
  end up with some secrets permanently stuck on the old key. It now rolls
  back entirely on any failure.
- **Docs corrected**: `migrate_encryption.py` only migrates off the old
  pre-1.1.0 token-derived key, once — it does not support rotating
  `VAULT_MASTER_KEY` itself later. README/DEPLOY previously implied
  otherwise; there is currently no supported master-key rotation path.

## 🧪 Testing

- `test_vault_server.py` — integration test suite covering auth, scoping,
  soft delete/undelete, versioning, audit logging, CORS-off-by-default, and
  the `X-Forwarded-For` trust boundary (including the fail-closed
  misconfiguration case). Run with `python3 -m unittest test_vault_server.py -v`.
- `test_migration_and_startup.py` — startup fail-fast checks (missing/malformed
  `VAULT_MASTER_KEY`, no auth configured, duplicate tokens, colliding
  prefixes) and a `migrate_encryption.py` round trip (including the
  partial-failure rollback case) against a seeded old-format database. Run
  with `python3 -m unittest test_migration_and_startup.py -v`.

## Still single-threaded, on purpose

The server remains a single-threaded `HTTPServer`. The sqlite3 connection
is not shared safely across threads; if concurrency is ever added, give
each worker its own connection and guard writes with a lock/transaction —
don't just swap in `ThreadingHTTPServer`.
