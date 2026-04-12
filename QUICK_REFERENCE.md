# Railway Vault Quick Reference

## 🚀 Deploy Now (5 minutes)

```bash
# 1. Deploy from GitHub
# Go to: https://railway.app/new
# Click: "Deploy from GitHub repo"
# Select: railway-vault
# Wait: ~2 minutes for build

# 2. Add volume
# Dashboard → Settings → Volumes → Add Volume
# Name: data
# Mount: /vault/data

# 3. Set token
TOKEN=$(openssl rand -base64 32)
railway variables set VAULT_TOKEN="$TOKEN"

# 4. Test
curl https://your-vault.railway.app/health

# 5. Save token somewhere safe!
echo "$TOKEN" > ~/railway-vault-token.txt
chmod 600 ~/railway-vault-token.txt
```

---

## 🔌 API Cheat Sheet

```bash
# Setup
export VAULT_URL="http://kmac-vault.railway.internal:9999"
export VAULT_TOKEN="your-token"

# Health
curl $VAULT_URL/health

# Set secret
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"app:db_url","value":"postgresql://..."}'

# Get secret
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/get/app:db_url

# List all
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/list

# Delete
curl -X POST \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/delete/app:db_url
```

---

## 💻 Client Code (Copy-Paste Ready)

### Python (FastAPI/Flask)

```python
import os
import requests

class VaultClient:
    def __init__(self):
        self.url = os.getenv("VAULT_URL")
        self.token = os.getenv("VAULT_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def get(self, key: str) -> str:
        resp = requests.get(f"{self.url}/get/{key}", 
                           headers=self.headers, timeout=5)
        return resp.json()["value"]

# Usage
vault = VaultClient()
DATABASE_URL = vault.get("myapp:database_url")
API_KEY = vault.get("myapp:api_key")
```

### Node.js (Express/Next.js)

```javascript
const axios = require('axios');

class VaultClient {
  constructor() {
    this.url = process.env.VAULT_URL;
    this.token = process.env.VAULT_TOKEN;
    this.headers = { Authorization: `Bearer ${this.token}` };
  }

  async get(key) {
    const resp = await axios.get(`${this.url}/get/${key}`, 
                                 { headers: this.headers, timeout: 5000 });
    return resp.data.value;
  }
}

// Usage
const vault = new VaultClient();
const DATABASE_URL = await vault.get('myapp:database_url');
const API_KEY = await vault.get('myapp:api_key');
```

---

## 📦 Per-Service Setup (2 minutes each)

```bash
# For EACH service (Adajoon, InfoBank, etc.):

# 1. Add vault connection
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999"
railway variables set VAULT_TOKEN="<token>"

# 2. Copy vault client to your code
cp examples/python_client.py your-app/vault_client.py
# or
cp examples/nodejs_client.js your-app/vault_client.js

# 3. Update app to use vault (see examples above)

# 4. Deploy
git add . && git commit -m "feat: use Railway vault" && git push

# 5. Test
railway logs -f

# 6. After 24h, remove old secrets
railway variables delete DATABASE_URL
railway variables delete API_KEY
# ...etc
```

---

## 🔑 Token Management

```bash
# Generate token
openssl rand -base64 32

# Save securely
echo "$TOKEN" > ~/railway-vault-token.txt
chmod 600 ~/railway-vault-token.txt

# Or use 1Password CLI
op item create --category=password \
  --title="Railway Vault Token" \
  token="$TOKEN"

# Rotate every 90 days
# 1. Generate new token
# 2. Update vault service
# 3. Update all client services
# 4. Restart all
```

---

## 📊 Your Services

| Service | Status | Action |
|---------|--------|--------|
| ✅ kmac-vault | Deploy first | [Deploy Guide](DEPLOY.md) |
| ⏳ Adajoon | Migrate first | Start here (smallest) |
| ⏳ InfoBank | Migrate second | - |
| ⏳ StableBank-Demo | Test before prod | - |
| ⏳ StableBank | Migrate last | Production (careful!) |
| ⏳ FlightPrep | Migrate anytime | - |

---

## 🚨 Emergency Rollback

```bash
# If vault fails, quick restore:
# 1. Add back old env vars to service
railway variables set DATABASE_URL="..." --service adajoon

# 2. Revert code
git revert HEAD && git push

# 3. Restart
railway restart --service adajoon
```

---

## ✅ Success Indicators

After full migration, you should see:

```bash
# 1. Vault running
railway status --service kmac-vault
# Status: Running ✅

# 2. All services healthy
railway status
# All services: Running ✅

# 3. No secret env vars (except VAULT_URL/TOKEN)
railway variables --service adajoon
# Should only see: VAULT_URL, VAULT_TOKEN, PORT, NODE_ENV, etc.

# 4. Logs show vault connections
railway logs --service adajoon
# Should see: "Connected to vault" or similar

# 5. Applications working normally
curl https://adajoon.railway.app/health
# Should return: 200 OK
```

---

## 📞 Quick Help

**Can't connect to vault?**
→ Check private networking: `railway status`

**Unauthorized error?**
→ Verify token: `railway variables | grep VAULT_TOKEN`

**Secret not found?**
→ List keys: `curl -H "Authorization: Bearer $TOKEN" $VAULT_URL/list`

**Need to backup?**
→ Use: `examples/migrate_secrets.py` to export

---

## 🎯 Today's Tasks

1. [ ] Deploy vault to Railway (15 min)
2. [ ] Generate and save token (2 min)
3. [ ] Test vault health (2 min)
4. [ ] Migrate Adajoon (30 min)
5. [ ] Monitor for 24 hours
6. [ ] Proceed with other services

**Estimated time:** 1 hour today, then monitor

---

**Repository:** https://github.com/ksarrafi/railway-vault  
**Railway:** https://railway.app/new  
**Support:** khash@khash.com
