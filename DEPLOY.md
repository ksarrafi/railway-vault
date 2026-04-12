# Railway Deployment Guide

## 🚀 Quick Deploy

### Option 1: Railway CLI (Recommended)

```bash
cd ~/Projects/railway-vault

# Initialize Railway project (interactive)
railway init

# Create and deploy
railway up

# Add volume for persistent storage
railway volume create data --mount /vault/data

# Generate secure token
TOKEN=$(openssl rand -base64 32)
echo "Generated token: $TOKEN"

# Set environment variables
railway variables set VAULT_TOKEN="$TOKEN"
railway variables set PORT="9999"

# Get service URL
railway status

# Test health endpoint
curl https://your-service.railway.app/health
```

### Option 2: Railway Dashboard

1. **Create New Project**
   - Go to https://railway.app/new
   - Click "Deploy from GitHub repo"
   - Connect your GitHub account
   - Push railway-vault to GitHub first

2. **Or Deploy from Local**
   - Go to https://railway.app/new
   - Click "Empty Project"
   - Name it "kmac-vault"
   - Click "Deploy"

3. **Add Volume**
   - Go to your service
   - Click "Settings" tab
   - Scroll to "Volumes"
   - Click "Add Volume"
   - Name: `data`
   - Mount path: `/vault/data`
   - Click "Add"

4. **Set Environment Variables**
   - Click "Variables" tab
   - Add variables:
     ```
     VAULT_TOKEN=<generate-with-openssl-rand-base64-32>
     PORT=9999
     ```
   - Click "Add" for each

5. **Deploy**
   - Railway will auto-deploy from Dockerfile
   - Wait for deployment to complete
   - Check logs for any errors

---

## 🔒 Generate Secure Token

```bash
# Generate a cryptographically secure token
openssl rand -base64 32

# Output example:
# Nzk4NjE2MzQ1MjE4NzY5Mzk4...

# Save this token securely!
# You'll need it for:
# 1. VAULT_TOKEN env var on vault service
# 2. VAULT_TOKEN env var on all client services
```

---

## 🌐 Enable Private Networking

Railway provides automatic private networking. Your services can reach the vault via:

```
http://kmac-vault.railway.internal:9999
```

**Steps:**
1. Ensure "Private Networking" is enabled in your Railway account settings
2. Use the internal domain in client services
3. Never use the public URL for vault access

---

## 📦 Client Service Setup

For **each** Railway service that needs secrets:

### 1. Add Environment Variables

```bash
# In each client service
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999"
railway variables set VAULT_TOKEN="<your-vault-token>"
```

### 2. Remove Old Secret Variables

```bash
# Remove these from Railway (now in vault):
railway variables delete DATABASE_URL
railway variables delete STRIPE_SECRET
railway variables delete API_KEY
# ... etc
```

### 3. Update Application Code

Add vault client (see README.md for Python/Node/Go examples)

### 4. Migrate Secrets

Use this script to migrate existing secrets to vault:

```python
# migrate_to_vault.py
import os
import requests

vault_url = os.getenv("VAULT_URL", "http://kmac-vault.railway.internal:9999")
vault_token = os.getenv("VAULT_TOKEN")
headers = {"Authorization": f"Bearer {vault_token}"}

# Map old env vars to vault keys
secrets = {
    "adajoon:database_url": os.getenv("DATABASE_URL"),
    "adajoon:stripe_secret": os.getenv("STRIPE_SECRET"),
    "adajoon:api_key": os.getenv("API_KEY"),
}

for key, value in secrets.items():
    if value:
        resp = requests.post(
            f"{vault_url}/set",
            headers=headers,
            json={"key": key, "value": value}
        )
        if resp.ok:
            print(f"✅ Migrated: {key}")
        else:
            print(f"❌ Failed: {key} - {resp.text}")

print("\n✅ Migration complete!")
print("Now remove old env vars from Railway")
```

Run once:
```bash
python migrate_to_vault.py
```

### 5. Restart Service

```bash
railway restart
```

---

## ✅ Verification

### 1. Check Vault Health

```bash
# Via public URL (initial setup)
curl https://your-vault-service.railway.app/health

# Expected:
# {"ok": true, "backend": "railway", "version": "1.0.0"}
```

### 2. Test API

```bash
# Set your token
export VAULT_TOKEN="your-token-here"
export VAULT_URL="https://your-vault-service.railway.app"

# Add a test secret
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"test:hello","value":"world"}'

# Retrieve it
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/get/test:hello

# Should return: {"key":"test:hello","value":"world"}
```

### 3. Test from Client Service

```python
# test_vault_connection.py
import os
import requests

vault_url = os.getenv("VAULT_URL")
vault_token = os.getenv("VAULT_TOKEN")

headers = {"Authorization": f"Bearer {vault_token}"}

# Test connection
try:
    resp = requests.get(f"{vault_url}/health", timeout=5)
    print(f"✅ Vault accessible: {resp.json()}")
except Exception as e:
    print(f"❌ Cannot reach vault: {e}")

# Test auth
try:
    resp = requests.get(f"{vault_url}/list", headers=headers, timeout=5)
    print(f"✅ Auth working: {len(resp.json()['keys'])} keys found")
except Exception as e:
    print(f"❌ Auth failed: {e}")
```

---

## 🔄 Rollout Plan

### Phase 1: Deploy Vault (Day 1)

1. ✅ Deploy kmac-vault to Railway
2. ✅ Add volume for persistence
3. ✅ Generate and set VAULT_TOKEN
4. ✅ Test health endpoint
5. ✅ Verify logs show successful startup

### Phase 2: Migrate One Service (Day 1-2)

Pick your smallest/least critical service first:

1. ✅ Add VAULT_URL + VAULT_TOKEN to service
2. ✅ Run migration script to copy secrets
3. ✅ Update code to use vault client
4. ✅ Deploy and test
5. ✅ Monitor for 24 hours
6. ✅ Remove old env vars

### Phase 3: Migrate Remaining Services (Week 1)

Do one service per day:

**Day 3:** Adajoon
- Morning: Migrate secrets
- Afternoon: Deploy + test
- Evening: Monitor

**Day 4:** InfoBank
- Same process

**Day 5:** StableBank-Demo
- Same process

**Day 6:** StableBank (production - be careful!)
- Same process
- Extra monitoring

**Day 7:** FlightPrep
- Same process

### Phase 4: Cleanup (Week 2)

1. ✅ Verify all services using vault
2. ✅ Remove all secret env vars from Railway
3. ✅ Update documentation
4. ✅ Train team on vault usage

---

## 🚨 Rollback Plan

If something goes wrong:

### Quick Rollback (< 5 minutes)

```bash
# In affected service:
# 1. Re-add old environment variables
railway variables set DATABASE_URL="..."
railway variables set STRIPE_SECRET="..."

# 2. Revert code changes (if needed)
git revert <commit>
git push

# 3. Redeploy
railway up

# 4. Verify service is working
```

### Keep Old Variables During Migration

**Best practice:** Don't delete old env vars until you're 100% confident

```bash
# Migration order:
# 1. Add VAULT_URL + VAULT_TOKEN
# 2. Migrate secrets to vault
# 3. Deploy new code (fetches from vault)
# 4. Test for 24-48 hours
# 5. Then (and only then) remove old env vars
```

---

## 📊 Monitoring

### Railway Logs

```bash
# View vault logs
railway logs --service kmac-vault

# Follow in real-time
railway logs -f --service kmac-vault

# Filter for errors
railway logs --service kmac-vault | grep "error"
```

### Health Checks

Create a cron job or use a monitoring service:

```bash
# Check vault health every minute
* * * * * curl -sf https://your-vault.railway.app/health || echo "Vault down!"
```

### Metrics to Watch

1. **Request rate** - Should be low (secrets fetched at startup)
2. **Error rate** - Should be zero
3. **Response time** - Should be < 100ms
4. **Volume usage** - Should grow slowly (only metadata)

---

## 💾 Backup & Recovery

### Automatic Backups

Railway volumes are automatically backed up. But you should also:

```bash
# Export all secrets weekly
./backup_secrets.sh

# Content:
#!/bin/bash
export VAULT_TOKEN="your-token"
export VAULT_URL="https://your-vault.railway.app"

curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/list | jq -r '.keys[]' | while read key; do
    value=$(curl -s -H "Authorization: Bearer $VAULT_TOKEN" \
      "$VAULT_URL/get/$key" | jq -r '.value')
    echo "$key=$value"
done > "backup_$(date +%Y%m%d).txt"

# Encrypt the backup
gpg --encrypt --recipient your@email.com "backup_$(date +%Y%m%d).txt"

# Store securely (1Password, etc)
```

### Disaster Recovery

If vault is completely lost:

```bash
# 1. Deploy new vault
railway up

# 2. Restore from encrypted backup
gpg --decrypt backup_20260412.txt.gpg > secrets.txt

# 3. Import secrets
while IFS='=' read -r key value; do
    curl -X POST $VAULT_URL/set \
      -H "Authorization: Bearer $VAULT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"key\":\"$key\",\"value\":\"$value\"}"
done < secrets.txt

# 4. Verify
curl -H "Authorization: Bearer $VAULT_TOKEN" $VAULT_URL/list

# 5. Restart all services
railway restart --all
```

---

## 🎓 Best Practices

### 1. Key Naming

```
<project>:<type>:<optional_env>

✅ Good:
- adajoon:database_url:prod
- infobank:stripe_key:dev
- stablebank:jwt_secret

❌ Bad:
- db_url
- secret1
- key
```

### 2. Token Rotation

```bash
# Every 90 days:
# 1. Generate new token
NEW_TOKEN=$(openssl rand -base64 32)

# 2. Update vault service
railway variables set VAULT_TOKEN="$NEW_TOKEN" --service kmac-vault

# 3. Update all client services (one at a time)
railway variables set VAULT_TOKEN="$NEW_TOKEN" --service adajoon
railway variables set VAULT_TOKEN="$NEW_TOKEN" --service infobank
# ...etc

# 4. Restart services
railway restart --all
```

### 3. Access Control

**Single token per environment:**

```
Development:   VAULT_TOKEN=dev_token_...
Staging:       VAULT_TOKEN=staging_token_...
Production:    VAULT_TOKEN=prod_token_...
```

**Or use different vault instances:**

```
Railway Projects:
├── kmac-vault-dev
├── kmac-vault-staging
└── kmac-vault-prod (most secure)
```

---

## 📞 Support

**Issues?**
1. Check Railway logs: `railway logs -f`
2. Verify environment variables are set
3. Test health endpoint: `curl $VAULT_URL/health`
4. Check private networking is enabled
5. Verify token matches in all services

**Need help?**
- GitHub Issues: (create repo first)
- Railway Discord: https://discord.gg/railway
- Email: khash@khash.com

---

## ✅ Deployment Checklist

Before going live:

- [ ] Vault deployed to Railway
- [ ] Volume added and mounted
- [ ] VAULT_TOKEN generated (strong: 32+ bytes)
- [ ] Health endpoint responds
- [ ] Test secret set + get works
- [ ] Private networking enabled
- [ ] Backup script created
- [ ] At least one service migrated and tested
- [ ] Team trained on vault usage
- [ ] Documentation updated
- [ ] Monitoring setup
- [ ] Rollback plan tested

---

**Ready to deploy? Let's do it! 🚀**
