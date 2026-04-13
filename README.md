# Railway KMac Vault

**Version:** 1.0.0 | **Status:** ✅ Production Ready | **Deployed:** April 12, 2026

Centralized encrypted key-value store for all your Railway applications. No more secrets in code or environment variables!

**🚀 Live:** https://kmac-vault-production.up.railway.app  
**🔒 Encryption:** Fernet (AES-128-CBC + HMAC-SHA256)  
**📦 Storage:** Persistent Railway volume

---

## ⚡ Quick Start

### New Users

1. **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md)** ⭐ **Start here** - Complete overview
2. **[DEPLOYMENT_SUCCESS.md](DEPLOYMENT_SUCCESS.md)** ✅ See current deployment
3. **[INDEX.md](INDEX.md)** 📚 Full documentation index

### Already Deployed?

- **Migrate Adajoon:** [ADAJOON_MIGRATION.md](ADAJOON_MIGRATION.md)
- **API Reference:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- **Compare Options:** [COMPARISON.md](COMPARISON.md)

---

## 📚 Complete Documentation

**[→ See INDEX.md for full documentation index](INDEX.md)**

### Essential Guides

- **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md)** - Overview, decision guide, timeline
- **[DEPLOYMENT_SUCCESS.md](DEPLOYMENT_SUCCESS.md)** - Current status & verification
- **[COMPARISON.md](COMPARISON.md)** - HashiCorp vs Railway vs railway-vault
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - API cheat sheet

### Migration Guides

- **[ADAJOON_MIGRATION.md](ADAJOON_MIGRATION.md)** - Migrate Adajoon step-by-step
- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - General service migration
- **[INTEGRATION_PLAN.md](INTEGRATION_PLAN.md)** - 7-day rollout plan
- **[DEPLOY.md](DEPLOY.md)** - Railway deployment instructions

---

## 🎯 Architecture

```
Railway Projects:
├── railway-vault (this service) ← All secrets stored here
│   └── Private networking: vault.railway.internal
│   └── Volume: /vault/data (persistent)
│
├── Adajoon ──────────┐
├── InfoBank ─────────┤
├── StableBank ───────┼──> Fetch secrets at runtime
├── StableBank-Demo ──┤    (no secrets in code/env)
└── FlightPrep ───────┘
```

## 🚀 Features

- ✅ **Encrypted at rest** - Fernet (AES-128-CBC + HMAC-SHA256)
- ✅ **Persistent storage** - Railway volume for database
- ✅ **Private networking** - Only accessible within your Railway account
- ✅ **Rate limiting** - 100 requests/minute per IP
- ✅ **Bearer token auth** - Single secure token
- ✅ **REST API** - Simple HTTP endpoints
- ✅ **No code changes** - Apps fetch secrets at startup

---

## 📦 Deployment

### 1. Create Railway Project

```bash
cd ~/Projects/railway-vault
railway init
railway up
```

### 2. Add Volume

```bash
# Create volume for persistent storage
railway volume create
# Mount to /vault/data
```

Or via Railway dashboard:
- Go to your vault service
- Click "Variables" tab
- Add Volume: `/vault/data`

### 3. Generate Secure Token

```bash
# Generate a strong token
openssl rand -base64 32

# Set as environment variable
railway variables set VAULT_TOKEN="<your-generated-token>"
```

### 4. Enable Private Networking

```bash
# Get private network URL
railway domain

# Note: Use vault.railway.internal in other services
```

---

## 🔌 API Endpoints

### Health Check
```bash
GET /health
```

Response:
```json
{
  "ok": true,
  "backend": "railway",
  "version": "1.0.0"
}
```

### Set Secret
```bash
POST /set
Authorization: Bearer <token>
Content-Type: application/json

{
  "key": "myapp:database_url",
  "value": "postgresql://..."
}
```

### Get Secret
```bash
GET /get/:key
Authorization: Bearer <token>
```

Response:
```json
{
  "key": "myapp:database_url",
  "value": "postgresql://..."
}
```

### List Keys
```bash
GET /list
Authorization: Bearer <token>
```

Response:
```json
{
  "keys": ["myapp:database_url", "myapp:api_key", ...]
}
```

### Delete Secret
```bash
POST /delete/:key
Authorization: Bearer <token>
```

---

## 📱 Client Usage

### Python Example

```python
import os
import requests

class VaultClient:
    def __init__(self):
        self.base_url = os.getenv("VAULT_URL", "http://vault.railway.internal:9999")
        self.token = os.getenv("VAULT_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def get(self, key: str) -> str:
        """Get secret value from vault."""
        response = requests.get(
            f"{self.base_url}/get/{key}",
            headers=self.headers,
            timeout=5
        )
        response.raise_for_status()
        return response.json()["value"]
    
    def set(self, key: str, value: str):
        """Store secret in vault."""
        response = requests.post(
            f"{self.base_url}/set",
            headers=self.headers,
            json={"key": key, "value": value},
            timeout=5
        )
        response.raise_for_status()

# Usage in your app
vault = VaultClient()

# Fetch secrets at startup
DATABASE_URL = vault.get("myapp:database_url")
API_KEY = vault.get("myapp:api_key")
STRIPE_SECRET = vault.get("myapp:stripe_secret")

# Now use them
app.config["DATABASE_URL"] = DATABASE_URL
```

### Node.js Example

```javascript
const axios = require('axios');

class VaultClient {
  constructor() {
    this.baseURL = process.env.VAULT_URL || 'http://vault.railway.internal:9999';
    this.token = process.env.VAULT_TOKEN;
    this.headers = { 'Authorization': `Bearer ${this.token}` };
  }

  async get(key) {
    const response = await axios.get(`${this.baseURL}/get/${key}`, {
      headers: this.headers,
      timeout: 5000
    });
    return response.data.value;
  }

  async set(key, value) {
    await axios.post(`${this.baseURL}/set`, 
      { key, value },
      { headers: this.headers, timeout: 5000 }
    );
  }
}

// Usage
const vault = new VaultClient();

async function loadSecrets() {
  process.env.DATABASE_URL = await vault.get('myapp:database_url');
  process.env.API_KEY = await vault.get('myapp:api_key');
  process.env.STRIPE_SECRET = await vault.get('myapp:stripe_secret');
}

// Load secrets before starting server
loadSecrets().then(() => {
  app.listen(PORT);
});
```

### Go Example

```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "os"
    "time"
)

type VaultClient struct {
    BaseURL string
    Token   string
    Client  *http.Client
}

func NewVaultClient() *VaultClient {
    baseURL := os.Getenv("VAULT_URL")
    if baseURL == "" {
        baseURL = "http://vault.railway.internal:9999"
    }
    
    return &VaultClient{
        BaseURL: baseURL,
        Token:   os.Getenv("VAULT_TOKEN"),
        Client:  &http.Client{Timeout: 5 * time.Second},
    }
}

func (v *VaultClient) Get(key string) (string, error) {
    req, _ := http.NewRequest("GET", fmt.Sprintf("%s/get/%s", v.BaseURL, key), nil)
    req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", v.Token))
    
    resp, err := v.Client.Do(req)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()
    
    body, _ := io.ReadAll(resp.Body)
    var result map[string]string
    json.Unmarshal(body, &result)
    
    return result["value"], nil
}

// Usage
func main() {
    vault := NewVaultClient()
    
    dbURL, _ := vault.Get("myapp:database_url")
    apiKey, _ := vault.Get("myapp:api_key")
    
    // Use secrets
    fmt.Println("Loaded secrets from vault")
}
```

---

## 🔒 Security Best Practices

### 1. Token Management

**DO:**
- ✅ Generate strong tokens: `openssl rand -base64 32`
- ✅ Store token in Railway environment variables
- ✅ Rotate tokens periodically
- ✅ Use different tokens for dev/staging/prod

**DON'T:**
- ❌ Commit tokens to git
- ❌ Log tokens in application code
- ❌ Share tokens via Slack/email

### 2. Key Naming Convention

Use project prefixes to organize secrets:

```
<project>:<key_type>:<optional_env>

Examples:
- adajoon:database_url
- infobank:stripe_secret:prod
- stablebank:jwt_secret
- flightprep:api_key:staging
```

### 3. Application Setup

**For each Railway service:**

1. Add environment variables:
   ```bash
   VAULT_URL=http://vault.railway.internal:9999
   VAULT_TOKEN=<your-vault-token>
   ```

2. Remove all secret environment variables from the service

3. Update code to fetch from vault at startup

4. Restart service

### 4. Private Networking

✅ **IMPORTANT:** Always use Railway's private networking

```bash
# Good: Private network (secure)
VAULT_URL=http://vault.railway.internal:9999

# Bad: Public URL (exposed)
VAULT_URL=https://vault-production-xxxx.railway.app
```

---

## 🛠️ Management

### Add Secret via CLI

```bash
# Set VAULT_URL and VAULT_TOKEN
export VAULT_URL="http://vault.railway.internal:9999"
export VAULT_TOKEN="your-token-here"

# Add secret
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"myapp:database_url","value":"postgresql://..."}'
```

### List All Secrets

```bash
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/list
```

### Backup Secrets

```bash
# Export all secrets to JSON
curl -H "Authorization: Bearer $VAULT_TOKEN" \
  $VAULT_URL/list | jq -r '.keys[]' | while read key; do
    value=$(curl -s -H "Authorization: Bearer $VAULT_TOKEN" \
      "$VAULT_URL/get/$key" | jq -r '.value')
    echo "$key=$value"
done > secrets_backup.txt

# Store securely (not in git!)
```

### Restore from Backup

```bash
# Read from backup and restore
while IFS='=' read -r key value; do
    curl -X POST $VAULT_URL/set \
      -H "Authorization: Bearer $VAULT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"key\":\"$key\",\"value\":\"$value\"}"
done < secrets_backup.txt
```

---

## 📊 Monitoring

### Health Check

```bash
# Check if vault is running
curl http://vault.railway.internal:9999/health
```

Expected response:
```json
{
  "ok": true,
  "backend": "railway",
  "version": "1.0.0"
}
```

### Railway Logs

```bash
# View logs
railway logs

# Follow logs in real-time
railway logs -f
```

---

## 🔄 Migration from Environment Variables

### Before (❌ Insecure)

```yaml
# Railway service environment variables
DATABASE_URL=postgresql://user:pass@host/db
STRIPE_SECRET=sk_live_xxxx
API_KEY=secret123
```

### After (✅ Secure)

```yaml
# Railway service environment variables
VAULT_URL=http://vault.railway.internal:9999
VAULT_TOKEN=<vault-token>

# Secrets now in vault, fetched at runtime
```

**Migration script:**

```python
import os
import requests

vault_url = "http://vault.railway.internal:9999"
vault_token = "your-vault-token"
headers = {"Authorization": f"Bearer {vault_token}"}

# Migrate environment variables to vault
secrets_to_migrate = {
    "myapp:database_url": os.getenv("DATABASE_URL"),
    "myapp:stripe_secret": os.getenv("STRIPE_SECRET"),
    "myapp:api_key": os.getenv("API_KEY"),
}

for key, value in secrets_to_migrate.items():
    if value:
        requests.post(
            f"{vault_url}/set",
            headers=headers,
            json={"key": key, "value": value}
        )
        print(f"✅ Migrated: {key}")

print("\n🎉 Migration complete!")
print("Now remove these from Railway environment variables")
```

---

## 🚨 Troubleshooting

### "Connection refused"

**Problem:** Can't reach vault from other services

**Solution:**
1. Verify vault service is running
2. Check private networking is enabled
3. Use `vault.railway.internal:9999` not localhost
4. Verify VAULT_TOKEN is set correctly

### "Unauthorized" (401)

**Problem:** Authentication failed

**Solution:**
1. Verify VAULT_TOKEN matches in both services
2. Check for whitespace in token
3. Regenerate token if needed:
   ```bash
   openssl rand -base64 32
   railway variables set VAULT_TOKEN="<new-token>"
   ```

### "Not found" (404)

**Problem:** Key doesn't exist

**Solution:**
1. List all keys: `curl -H "Authorization: Bearer $VAULT_TOKEN" $VAULT_URL/list`
2. Verify key name matches exactly (case-sensitive)
3. Add the key if missing

### "Rate limited" (429)

**Problem:** Too many requests

**Solution:**
1. Implement caching in your application
2. Load secrets once at startup, not on every request
3. Current limit: 100 req/min per IP

---

## 📄 License

MIT License - Same as KMac-CLI

---

## 🙏 Credits

Based on [KMac-CLI](https://github.com/ksarrafi/KMAC-CLI) Docker Vault by Khash Sarrafi
