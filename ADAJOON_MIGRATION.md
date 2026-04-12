# Adajoon → railway-vault Migration Guide

**Goal:** Move all Adajoon secrets from Railway environment variables to the centralized railway-vault service.

---

## 🎯 Why Use railway-vault Instead of Railway Env Vars?

### Railway Env Vars (Current - What you just switched to)
- ❌ Secrets visible in Railway dashboard UI
- ❌ Scattered across multiple services
- ❌ Must manually sync between backend/worker
- ❌ No audit trail of access
- ✅ Encrypted at rest

### railway-vault (Target - What we just deployed)
- ✅ Secrets never visible in UI
- ✅ Single source of truth for ALL projects
- ✅ Automatic sync (fetch at runtime)
- ✅ Full audit trail in logs
- ✅ Fernet encrypted + AES-256 at rest
- ✅ Instant rotation (update vault, restart services)

**You made the right call!** Let's use railway-vault.

---

## 📋 Step 1: Migrate Adajoon Secrets to railway-vault

### Current Adajoon Secrets (from RAILWAY_SECRETS.md)

Based on your codebase, Adajoon needs these secrets:

```bash
# Database & Cache
DATABASE_URL=${POSTGRES_URL}
REDIS_URL=${REDIS_URL}

# Authentication
JWT_SECRET=<generate-with-openssl-rand-hex-32>

# OAuth
GOOGLE_CLIENT_ID=<your-google-id>
APPLE_CLIENT_ID=<your-apple-id>

# AI
ANTHROPIC_API_KEY=sk-ant-...

# Payment
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_live_...

# Internal
SYNC_API_KEY=<generate-with-openssl-rand-hex-32>

# WebAuthn
WEBAUTHN_RP_ID=adajoon.com
WEBAUTHN_ORIGIN=https://www.adajoon.com

# Configuration (not secrets)
CORS_ORIGINS=https://adajoon.com,https://www.adajoon.com
ENV=production
JSON_LOGS=true
```

### Migrate to railway-vault

```bash
# Set vault credentials
export VAULT_URL="https://kmac-vault-production.up.railway.app"
export VAULT_TOKEN="MC/0uklic3axGOpOPlWaXhnxz+eSeKuHnS+dudoEt+8="

# Get current values from Railway (you'll need to copy these from dashboard)
# Then add to vault with proper namespace:

# Database (these come from Railway service references)
# Note: DATABASE_URL and REDIS_URL are special - keep as references in Railway
# We'll fetch them in code and DON'T store in vault

# Authentication
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:jwt_secret","value":"<your-jwt-secret>"}'

# OAuth
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:google_client_id","value":"<your-google-id>"}'

curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:apple_client_id","value":"<your-apple-id>"}'

# AI
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:anthropic_api_key","value":"sk-ant-..."}'

# Payment
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:stripe_secret_key","value":"sk_live_..."}'

curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:stripe_webhook_secret","value":"whsec_..."}'

curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:stripe_publishable_key","value":"pk_live_..."}'

# Internal
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:sync_api_key","value":"<your-sync-key>"}'

# WebAuthn
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:webauthn_rp_id","value":"adajoon.com"}'

curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:webauthn_origin","value":"https://www.adajoon.com"}'

# Verify all secrets were stored
curl -H "Authorization: Bearer $VAULT_TOKEN" $VAULT_URL/list | jq
```

---

## 📝 Step 2: Update Adajoon Backend Code

### Add Vault Client

```bash
# Copy Python vault client to Adajoon backend
cp ~/Projects/railway-vault/examples/python_client.py \
   ~/Projects/Adajoon/backend/app/vault_client.py
```

### Update config.py

Your current `backend/app/config.py` uses pydantic-settings to load from env vars:

```python
# Current (loads from Railway env vars)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = ""  # Loaded from env
    jwt_secret: str = ""
    # ...
```

**Change to:**

```python
# New (loads from railway-vault)
from pydantic_settings import BaseSettings
from app.vault_client import VaultClient
import os

# Initialize vault client
vault = VaultClient(
    url=os.getenv("VAULT_URL", "http://kmac-vault.railway.internal:9999"),
    token=os.getenv("VAULT_TOKEN")
)

class Settings(BaseSettings):
    # Railway service references (keep as env vars)
    database_url: str = ""  # From ${POSTGRES_URL} reference
    redis_url: str = ""     # From ${REDIS_URL} reference
    
    # Fetch from vault
    jwt_secret: str = vault.get("adajoon:jwt_secret")
    google_client_id: str = vault.get("adajoon:google_client_id")
    apple_client_id: str = vault.get("adajoon:apple_client_id")
    anthropic_api_key: str = vault.get("adajoon:anthropic_api_key")
    stripe_secret_key: str = vault.get("adajoon:stripe_secret_key")
    stripe_webhook_secret: str = vault.get("adajoon:stripe_webhook_secret")
    stripe_publishable_key: str = vault.get("adajoon:stripe_publishable_key")
    sync_api_key: str = vault.get("adajoon:sync_api_key")
    webauthn_rp_id: str = vault.get("adajoon:webauthn_rp_id")
    webauthn_origin: str = vault.get("adajoon:webauthn_origin")
    
    # Non-secret config (keep as env vars)
    cors_origins: str = ""
    env: str = "production"
    json_logs: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

### Add requests dependency

```bash
# Add to backend/requirements.txt
echo "requests==2.31.0" >> backend/requirements.txt
```

---

## 📦 Step 3: Configure Railway Variables

### Backend Service

Keep ONLY these in Railway env vars:

```bash
# Railway Dashboard → Backend Service → Variables

# Vault connection (only secrets needed)
VAULT_URL=http://kmac-vault.railway.internal:9999
VAULT_TOKEN=MC/0uklic3axGOpOPlWaXhnxz+eSeKuHnS+dudoEt+8=

# Database/Redis (service references - keep these)
DATABASE_URL=${POSTGRES_URL}
REDIS_URL=${REDIS_URL}

# Non-secret configuration
CORS_ORIGINS=https://adajoon.com,https://www.adajoon.com
ENV=production
JSON_LOGS=true
```

**Remove these** (now in vault):
```bash
❌ JWT_SECRET
❌ GOOGLE_CLIENT_ID
❌ APPLE_CLIENT_ID
❌ ANTHROPIC_API_KEY
❌ STRIPE_SECRET_KEY
❌ STRIPE_WEBHOOK_SECRET
❌ STRIPE_PUBLISHABLE_KEY
❌ SYNC_API_KEY
❌ WEBAUTHN_RP_ID
❌ WEBAUTHN_ORIGIN
```

### Worker Service

Use variable references:

```bash
# Railway Dashboard → Worker Service → Variables

# Reference backend variables (Railway auto-sync)
VAULT_URL=${backend.VAULT_URL}
VAULT_TOKEN=${backend.VAULT_TOKEN}
DATABASE_URL=${backend.DATABASE_URL}
REDIS_URL=${backend.REDIS_URL}
ENV=${backend.ENV}
```

Worker will fetch secrets from vault using same vault_client.py

---

## 🚀 Step 4: Deploy and Test

```bash
cd ~/Projects/Adajoon

# Commit changes
git add backend/app/vault_client.py
git add backend/app/config.py
git add backend/requirements.txt
git commit -m "feat: migrate to railway-vault for secrets"
git push

# Railway auto-deploys backend and worker

# Monitor logs
railway logs -f --service backend

# Look for:
# ✅ "Connected to vault" or similar
# ✅ No errors about missing secrets
# ❌ Any "unauthorized" or "connection refused" errors

# Test health endpoint
curl https://your-adajoon-backend.railway.app/health
```

---

## 🧪 Step 5: Verify Migration

### Test Backend Can Access Secrets

```bash
# Check logs for successful vault connection
railway logs --service backend | grep -i vault

# Expected: No errors about missing secrets

# Test API endpoints that use secrets
curl https://your-adajoon-backend.railway.app/api/...
```

### Verify Secrets Are Hidden

```bash
# List Railway env vars
railway variables --service backend

# Should ONLY see:
# - VAULT_URL
# - VAULT_TOKEN  
# - DATABASE_URL (reference)
# - REDIS_URL (reference)
# - CORS_ORIGINS
# - ENV
# - JSON_LOGS

# Should NOT see:
# - JWT_SECRET (now in vault)
# - STRIPE_SECRET_KEY (now in vault)
# - etc.
```

### Test Secret Rotation

```bash
# Update a secret in vault
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"adajoon:jwt_secret","value":"new-jwt-secret-value"}'

# Restart backend
railway restart --service backend

# Secret updated! No code changes needed.
```

---

## 📊 Before vs After

### Before (Railway Env Vars)
```
Railway Dashboard → Backend Service → Variables (visible)
├── DATABASE_URL=postgresql://... ❌ Visible
├── JWT_SECRET=abc123... ❌ Visible
├── STRIPE_SECRET_KEY=sk_live_... ❌ Visible
└── ... (12+ secrets visible)
```

### After (railway-vault)
```
Railway Dashboard → Backend Service → Variables
├── VAULT_URL=http://kmac-vault.railway.internal:9999 ✅
├── VAULT_TOKEN=MC/0ukl... ✅ (only this one secret)
├── DATABASE_URL=${POSTGRES_URL} ✅ (reference)
└── CORS_ORIGINS=... ✅ (not secret)

railway-vault Service → Encrypted Storage
├── adajoon:jwt_secret ✅ Encrypted, not visible
├── adajoon:stripe_secret_key ✅ Encrypted, not visible
└── ... (all secrets encrypted, fetched at runtime)
```

**Security improvement:** 90% fewer secrets visible in Railway UI

---

## 🔒 Security Benefits

### With Railway Env Vars (Before)
- ❌ All secrets visible in dashboard
- ❌ Anyone with Railway access sees secrets
- ❌ Secrets logged in deployment history
- ❌ Must manually sync between services
- ❌ No audit trail of access

### With railway-vault (After)
- ✅ Only VAULT_TOKEN visible (1 secret vs 12+)
- ✅ Secrets never shown in UI
- ✅ Full audit trail (vault logs every access)
- ✅ Automatic sync (all services fetch from vault)
- ✅ Instant rotation (update vault, restart)
- ✅ Encrypted at rest (Fernet + AES-256)

---

## 🚨 Rollback Plan

If something goes wrong:

```bash
# 1. Revert code
cd ~/Projects/Adajoon
git revert HEAD
git push

# 2. Re-add secrets to Railway env vars
railway variables set JWT_SECRET="..." --service backend
railway variables set STRIPE_SECRET_KEY="..." --service backend
# ...etc

# 3. Restart
railway restart --service backend

# Time to rollback: < 5 minutes
```

---

## ✅ Migration Checklist

- [ ] Copy vault_client.py to Adajoon backend
- [ ] Update backend/app/config.py to use vault
- [ ] Add requests to requirements.txt
- [ ] Migrate all secrets to railway-vault (curl commands above)
- [ ] Verify secrets in vault: `curl -H "Authorization: Bearer $VAULT_TOKEN" $VAULT_URL/list`
- [ ] Update Railway env vars (add VAULT_URL/TOKEN)
- [ ] Remove old secret env vars from Railway
- [ ] Deploy to Railway
- [ ] Test backend health endpoint
- [ ] Monitor logs for 30 minutes
- [ ] Test API endpoints that use secrets
- [ ] Verify worker service works
- [ ] Test secret rotation

---

## 💡 Pro Tips

### Use Private Network URL in Production
```bash
# Production (private network)
VAULT_URL=http://kmac-vault.railway.internal:9999

# Development (public URL for testing)
VAULT_URL=https://kmac-vault-production.up.railway.app
```

### Cache Secrets for Performance
```python
# In vault_client.py, add caching
from functools import lru_cache

@lru_cache(maxsize=128)
def get(self, key: str) -> str:
    # Vault calls cached for lifetime of process
    ...
```

### Rotate Secrets Regularly
```bash
# Every 90 days, rotate sensitive secrets
# 1. Generate new secret
NEW_SECRET=$(openssl rand -hex 32)

# 2. Update in vault
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"adajoon:jwt_secret\",\"value\":\"$NEW_SECRET\"}"

# 3. Restart services
railway restart --service backend
railway restart --service worker

# Done! No code changes needed.
```

---

## 📞 Need Help?

- **Vault Dashboard:** https://railway.com/project/8d031578-2d1f-475c-b6d7-2f4dd2b04c13
- **Vault Health:** https://kmac-vault-production.up.railway.app/health
- **Documentation:** ~/Projects/railway-vault/QUICK_REFERENCE.md

---

**Estimated migration time:** 30 minutes  
**Risk level:** Low (easy rollback)  
**When to do it:** Now (Adajoon is perfect first candidate)

**Let's do this! 🚀**
