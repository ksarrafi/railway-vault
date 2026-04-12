# Step-by-Step Setup Guide for Railway Vault

This guide will walk you through deploying the vault and migrating all your Railway applications.

---

## 📋 Prerequisites

- [x] Railway account (already logged in as khash@khash.com)
- [x] Railway CLI installed (v4.36.1)
- [ ] GitHub account (for deployment)
- [ ] 30 minutes for setup

---

## Phase 1: Deploy the Vault (15 minutes)

### Step 1: Push to GitHub

```bash
cd ~/Projects/railway-vault

# Create GitHub repo
gh repo create railway-vault --public --source=. --remote=origin --push

# Or push to existing repo
git remote add origin https://github.com/ksarrafi/railway-vault.git
git push -u origin master
```

### Step 2: Deploy to Railway

**Option A: Via Railway CLI**

```bash
# Initialize Railway project (interactive - you'll pick workspace)
railway init

# Deploy
railway up

# Check status
railway status
```

**Option B: Via Railway Dashboard** (Easier for first time)

1. Go to https://railway.app/new
2. Click "Deploy from GitHub repo"
3. Select `railway-vault` repository
4. Railway will auto-detect Dockerfile
5. Click "Deploy"
6. Wait ~2 minutes for first build

### Step 3: Add Persistent Volume

**Via Railway CLI:**
```bash
railway volume create data --mount /vault/data
```

**Via Dashboard:**
1. Go to your kmac-vault service
2. Click "Settings" tab
3. Scroll to "Volumes"
4. Click "+ New Volume"
5. Name: `data`
6. Mount Path: `/vault/data`
7. Click "Add"

### Step 4: Generate and Set Token

```bash
# Generate secure token
TOKEN=$(openssl rand -base64 32)
echo "Your vault token: $TOKEN"

# IMPORTANT: Save this token securely!
# You'll need it for all client services

# Set on Railway
railway variables set VAULT_TOKEN="$TOKEN"

# Or copy to clipboard (macOS)
echo "$TOKEN" | pbcopy
echo "Token copied to clipboard!"
```

### Step 5: Verify Deployment

```bash
# Get public URL
railway domain

# Test health (replace with your URL)
curl https://your-vault-production-abc123.railway.app/health

# Expected response:
# {"ok": true, "backend": "railway", "version": "1.0.0"}

# Test authentication
curl -H "Authorization: Bearer $TOKEN" \
  https://your-vault-production-abc123.railway.app/list

# Expected response:
# {"keys": []}
```

### Step 6: Get Private Network URL

```bash
# View service details
railway status

# Note the private URL (format: service-name.railway.internal)
# Example: kmac-vault.railway.internal:9999

# This is what your other services will use!
```

✅ **Vault deployed and ready!**

---

## Phase 2: Migrate Your Applications

### Your Railway Projects

1. **Adajoon** - [Start here - smallest/safest first]
2. **InfoBank**
3. **StableBank-Demo** - [Test before production]
4. **StableBank** - [Production - do last]
5. **FlightPrep**

---

### Service 1: Adajoon (Example)

#### Step 1: Identify Current Secrets

```bash
# Link to Adajoon project
cd ~/Projects/Adajoon  # (if you have local code)
railway link

# List current environment variables
railway variables

# Or via dashboard:
# https://railway.app/project/[adajoon-id]/service/[service-id]/variables
```

Common secrets to migrate:
- `DATABASE_URL`
- `DATABASE_PASSWORD` / `DB_PASSWORD`
- `REDIS_URL`
- `API_KEY` / `API_SECRET`
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `JWT_SECRET` / `SESSION_SECRET`
- `SMTP_PASSWORD`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
- `SENDGRID_API_KEY`
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`

#### Step 2: Add Vault Connection to Adajoon

```bash
# Add vault connection variables
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service adajoon
railway variables set VAULT_TOKEN="<your-vault-token>" --service adajoon
```

#### Step 3: Migrate Secrets to Vault

Edit `examples/migrate_secrets.py`:

```python
SECRETS_TO_MIGRATE = {
    # Adajoon secrets
    "adajoon:database_url": "DATABASE_URL",
    "adajoon:database_password": "DB_PASSWORD",
    "adajoon:redis_url": "REDIS_URL",
    "adajoon:api_key": "API_KEY",
    "adajoon:stripe_secret": "STRIPE_SECRET_KEY",
    "adajoon:stripe_publishable": "STRIPE_PUBLISHABLE_KEY",
    "adajoon:jwt_secret": "JWT_SECRET",
    "adajoon:smtp_password": "SMTP_PASSWORD",
    # Add more...
}
```

Run migration:
```bash
# Set vault credentials
export VAULT_URL="https://your-vault.railway.app"
export VAULT_TOKEN="your-token"

# Set current Adajoon env vars
export DATABASE_URL="postgresql://..."
export STRIPE_SECRET_KEY="sk_live_..."
# ...etc (copy from Railway dashboard)

# Run migration
python examples/migrate_secrets.py

# Verify secrets were stored
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/list | jq
```

#### Step 4: Update Adajoon Code

**Python (Flask/FastAPI):**

```python
# Add to requirements.txt
requests

# Add to app startup (before anything else)
from vault_client import VaultClient

vault = VaultClient()

# Replace os.getenv() with vault.get()
# Before:
# DATABASE_URL = os.getenv("DATABASE_URL")

# After:
DATABASE_URL = vault.get("adajoon:database_url")
STRIPE_SECRET = vault.get("adajoon:stripe_secret")
JWT_SECRET = vault.get("adajoon:jwt_secret")

# Use them normally
app.config["DATABASE_URL"] = DATABASE_URL
```

**Node.js (Express/Next.js):**

```javascript
// Add to package.json dependencies
"axios": "^1.6.0"

// Add to app startup
const VaultClient = require('./vault_client');

const vault = new VaultClient();

// Load secrets before starting server
async function loadSecrets() {
  process.env.DATABASE_URL = await vault.get('adajoon:database_url');
  process.env.STRIPE_SECRET = await vault.get('adajoon:stripe_secret');
  process.env.JWT_SECRET = await vault.get('adajoon:jwt_secret');
}

loadSecrets().then(() => {
  app.listen(PORT);
});
```

#### Step 5: Deploy and Test

```bash
# Commit vault client code
git add vault_client.py  # or vault_client.js
git commit -m "feat: integrate Railway vault for secrets"
git push

# Railway will auto-deploy

# Watch logs
railway logs -f --service adajoon

# Look for successful vault connection
# Expected: "✅ Connected to vault" or "Loaded secrets from vault"
```

#### Step 6: Verify Application Works

```bash
# Check service health
railway status --service adajoon

# Test your application endpoints
curl https://your-adajoon-app.railway.app/health

# Monitor logs for errors
railway logs --service adajoon | grep -i "error\|vault"
```

#### Step 7: Remove Old Secrets (After 24-48 Hours)

⚠️ **IMPORTANT:** Only after confirming everything works!

```bash
# Remove old secret env vars
railway variables delete DATABASE_URL --service adajoon
railway variables delete STRIPE_SECRET_KEY --service adajoon
railway variables delete JWT_SECRET --service adajoon
# ...etc

# Keep these:
# - VAULT_URL
# - VAULT_TOKEN
# - Non-secret configs (PORT, NODE_ENV, etc.)

# Restart to verify still works without old vars
railway restart --service adajoon
```

✅ **Adajoon migrated!**

---

### Services 2-5: Repeat Process

Use the same steps for each service:

**InfoBank:**
```bash
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service infobank
railway variables set VAULT_TOKEN="<token>" --service infobank
# ...migrate, deploy, test, cleanup
```

**StableBank-Demo:**
```bash
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service stablebank-demo
railway variables set VAULT_TOKEN="<token>" --service stablebank-demo
# ...migrate, deploy, test, cleanup
```

**StableBank (Production):**
```bash
# Extra careful with production!
# Do during low-traffic window
# Have rollback plan ready

railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service stablebank
railway variables set VAULT_TOKEN="<token>" --service stablebank
# ...migrate, deploy, test thoroughly, monitor 48h, cleanup
```

**FlightPrep:**
```bash
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service flightprep
railway variables set VAULT_TOKEN="<token>" --service flightprep
# ...migrate, deploy, test, cleanup
```

---

## 🔒 Security Checklist

Before going live:

- [ ] Vault token is strong (32+ bytes random)
- [ ] Token stored securely (password manager)
- [ ] Only VAULT_URL and VAULT_TOKEN in service env vars
- [ ] No secrets in application code
- [ ] No secrets committed to git
- [ ] Private networking enabled
- [ ] Volume mounted for persistence
- [ ] Health checks passing
- [ ] Backup script created
- [ ] Rollback plan documented
- [ ] Team trained on vault usage

---

## 📊 Monitoring Setup

### Create Monitoring Script

```bash
# monitor_vault.sh
#!/bin/bash

VAULT_URL="https://your-vault.railway.app"
VAULT_TOKEN="your-token"

# Health check
health=$(curl -sf "$VAULT_URL/health")
if [ $? -eq 0 ]; then
    echo "✅ Vault healthy: $health"
else
    echo "❌ Vault DOWN!"
    # Send alert (Slack, PagerDuty, etc.)
fi

# Check secret count
count=$(curl -sf -H "Authorization: Bearer $VAULT_TOKEN" \
    "$VAULT_URL/list" | jq -r '.keys | length')
echo "📊 Secrets stored: $count"
```

Run every 5 minutes:
```bash
crontab -e
# Add:
*/5 * * * * ~/monitor_vault.sh >> ~/vault_monitor.log 2>&1
```

---

## 🚨 Troubleshooting

### Vault Not Starting

```bash
# Check Railway logs
railway logs --service kmac-vault

# Common issues:
# 1. Volume not mounted → Add volume to /vault/data
# 2. PORT env var missing → Set PORT=9999
# 3. VAULT_TOKEN not set → Generate and set token
```

### Client Can't Connect

```bash
# Test from client service
railway run bash --service adajoon

# Inside Railway shell:
curl http://kmac-vault.railway.internal:9999/health

# If this fails:
# 1. Check private networking is enabled
# 2. Verify vault service name matches
# 3. Try public URL temporarily (for debugging only)
```

### Secrets Not Loading

```bash
# Check client logs
railway logs --service adajoon | grep vault

# Common issues:
# 1. Wrong VAULT_TOKEN → Verify matches vault service
# 2. Wrong key names → Check vault.list() output
# 3. Network timeout → Increase timeout in client code
```

---

## 📞 Support

**Questions?** 

1. Check Railway logs first: `railway logs -f`
2. Test vault health: `curl $VAULT_URL/health`
3. Verify token: `echo $VAULT_TOKEN | wc -c` (should be 40+)
4. Check private networking status

**Need help?** Open an issue or contact khash@khash.com

---

## ✅ Success Criteria

You'll know the migration is successful when:

✅ Vault service is running on Railway  
✅ Health endpoint returns 200 OK  
✅ All secrets migrated and verified  
✅ All 5 services using vault client  
✅ No secret env vars remain (except VAULT_URL/TOKEN)  
✅ All applications working normally  
✅ Logs show successful vault connections  
✅ Backup script created and tested  

---

**Ready to deploy? Let's do it! 🚀**

Next command: `gh repo create railway-vault --public --source=. --remote=origin --push`
