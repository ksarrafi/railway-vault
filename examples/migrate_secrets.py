#!/usr/bin/env python3
"""
Migrate secrets from Railway environment variables to Railway Vault.

Usage:
    1. Set environment variables:
       export VAULT_URL="https://your-vault.railway.app"
       export VAULT_TOKEN="your-token"
       
    2. Edit the SECRETS_TO_MIGRATE dict below with your secrets
    
    3. Run:
       python migrate_secrets.py
       
    4. After successful migration, remove old env vars from Railway
"""

import os
import sys
import requests
from typing import Dict

# Configure vault connection
VAULT_URL = os.getenv("VAULT_URL", "http://vault.railway.internal:9999")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

if not VAULT_TOKEN:
    print("ERROR: VAULT_TOKEN environment variable required")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {VAULT_TOKEN}", "Content-Type": "application/json"}


def test_connection():
    """Test vault connection before migrating."""
    try:
        response = requests.get(f"{VAULT_URL}/health", timeout=5)
        if response.ok:
            print(f"✅ Connected to vault: {VAULT_URL}")
            return True
        else:
            print(f"❌ Vault health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to vault: {e}")
        return False


def migrate_secret(vault_key: str, env_var_name: str) -> bool:
    """
    Migrate a secret from environment variable to vault.
    
    Args:
        vault_key: Key name in vault (e.g., "myapp:database_url")
        env_var_name: Environment variable name (e.g., "DATABASE_URL")
        
    Returns:
        True if successful, False otherwise
    """
    value = os.getenv(env_var_name)
    
    if not value:
        print(f"⚠️  Skipping {vault_key}: env var {env_var_name} not set")
        return False
    
    # Don't migrate placeholder values
    if value in ["your-secret-here", "changeme", "TODO", ""]:
        print(f"⚠️  Skipping {vault_key}: placeholder value detected")
        return False
    
    try:
        response = requests.post(
            f"{VAULT_URL}/set",
            headers=HEADERS,
            json={"key": vault_key, "value": value},
            timeout=5
        )
        
        if response.ok:
            # Mask value in output (show first 4 chars only)
            masked = value[:4] + "..." if len(value) > 4 else "***"
            print(f"✅ Migrated: {vault_key} = {masked}")
            return True
        else:
            print(f"❌ Failed to migrate {vault_key}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error migrating {vault_key}: {e}")
        return False


def verify_secret(vault_key: str, original_value: str) -> bool:
    """Verify secret was stored correctly."""
    try:
        response = requests.get(
            f"{VAULT_URL}/get/{vault_key}",
            headers=HEADERS,
            timeout=5
        )
        
        if response.ok:
            stored_value = response.json()["value"]
            if stored_value == original_value:
                print(f"   ✓ Verified: {vault_key}")
                return True
            else:
                print(f"   ✗ Mismatch: {vault_key}")
                return False
        else:
            print(f"   ✗ Not found: {vault_key}")
            return False
            
    except Exception as e:
        print(f"   ✗ Verification failed: {e}")
        return False


# ==========================================
# CONFIGURE YOUR SECRETS HERE
# ==========================================

# Map vault keys to environment variable names
# Format: "project:key_name": "ENV_VAR_NAME"

SECRETS_TO_MIGRATE: Dict[str, str] = {
    # Example - Adajoon project
    "adajoon:database_url": "DATABASE_URL",
    "adajoon:database_password": "DB_PASSWORD",
    "adajoon:api_key": "API_KEY",
    "adajoon:stripe_secret": "STRIPE_SECRET_KEY",
    "adajoon:stripe_publishable": "STRIPE_PUBLISHABLE_KEY",
    "adajoon:jwt_secret": "JWT_SECRET",
    
    # Example - InfoBank project
    # "infobank:database_url": "DATABASE_URL",
    # "infobank:api_key": "API_KEY",
    
    # Example - StableBank project
    # "stablebank:database_url": "DATABASE_URL",
    # "stablebank:plaid_secret": "PLAID_SECRET",
    
    # Add your secrets here...
}


def main():
    """Run migration."""
    print("=" * 60)
    print("Railway Vault Migration Tool")
    print("=" * 60)
    print(f"Vault URL: {VAULT_URL}")
    print(f"Secrets to migrate: {len(SECRETS_TO_MIGRATE)}")
    print("=" * 60)
    print()
    
    # Test connection first
    if not test_connection():
        print("\n❌ Migration aborted: Cannot connect to vault")
        sys.exit(1)
    
    print()
    print("Starting migration...")
    print("-" * 60)
    
    # Migrate each secret
    migrated = 0
    failed = 0
    skipped = 0
    
    for vault_key, env_var in SECRETS_TO_MIGRATE.items():
        original_value = os.getenv(env_var)
        
        if not original_value:
            skipped += 1
            continue
        
        if migrate_secret(vault_key, env_var):
            # Verify it was stored correctly
            if verify_secret(vault_key, original_value):
                migrated += 1
            else:
                failed += 1
        else:
            failed += 1
    
    # Summary
    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"✅ Migrated:  {migrated}")
    print(f"⚠️  Skipped:   {skipped}")
    print(f"❌ Failed:    {failed}")
    print("=" * 60)
    
    if failed > 0:
        print("\n⚠️  Some secrets failed to migrate. Check errors above.")
        sys.exit(1)
    
    if migrated > 0:
        print("\n✅ Migration complete!")
        print()
        print("Next steps:")
        print("  1. Verify secrets in vault: railway run python verify_secrets.py")
        print("  2. Deploy your app with vault client code")
        print("  3. Test that app can fetch secrets from vault")
        print("  4. After 24-48 hours of successful operation:")
        print("     → Remove old environment variables from Railway")
        print("     → Keep VAULT_URL and VAULT_TOKEN")
    else:
        print("\n⚠️  No secrets were migrated.")
        print("Edit SECRETS_TO_MIGRATE in this script to add your secrets.")


if __name__ == "__main__":
    main()
