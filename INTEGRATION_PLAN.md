# Railway Vault Integration Plan

**Status:** Ready to deploy  
**Date:** April 12, 2026  
**Target Services:** 5 Railway applications  
**Timeline:** 1 week (phased rollout)

---

## 🎯 Objectives

### Primary Goals
1. ✅ **Zero secrets in code** - All secrets fetched from central vault at runtime
2. ✅ **Zero secrets in containers** - No environment variables with sensitive data
3. ✅ **Single source of truth** - One vault for all Railway projects
4. ✅ **Encrypted at rest** - Fernet (AES-128-CBC + HMAC-SHA256)
5. ✅ **Private networking** - Vault only accessible within Railway account

### Success Metrics
- **Security:** 0 secrets in git, 0 secrets in Railway env vars (except VAULT_URL/TOKEN)
- **Reliability:** 99.9% vault uptime, < 100ms response time
- **Adoption:** All 5 services using vault within 1 week

---

## 📊 Current State Analysis

### Your Railway Projects

| Project | Est. Secrets | Priority | Timeline |
|---------|--------------|----------|----------|
| **Adajoon** | 5-10 | High | Day 1-2 |
| **InfoBank** | 5-10 | Medium | Day 3 |
| **StableBank-Demo** | 10-15 | High | Day 4 (test before prod) |
| **StableBank** | 10-15 | Critical | Day 5-6 (production!) |
| **FlightPrep** | 5-10 | Medium | Day 7 |

**Total estimated secrets:** 35-60 keys

### Common Secrets to Migrate

Based on typical Railway applications:

**Database & Cache:**
- `DATABASE_URL`
- `DATABASE_PASSWORD`
- `POSTGRES_URL` / `MYSQL_URL`
- `REDIS_URL`
- `REDIS_PASSWORD`

**Authentication:**
- `JWT_SECRET` / `SESSION_SECRET`
- `AUTH_SECRET`
- `NEXTAUTH_SECRET`

**Payment Processing:**
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`

**External APIs:**
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `SENDGRID_API_KEY`
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`

**Email & Communication:**
- `SMTP_PASSWORD`
- `MAILGUN_API_KEY`
- `SLACK_WEBHOOK_URL`

**OAuth & Social:**
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
- `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET`

---

## 🗓️ Phased Rollout Timeline

### Day 1: Deploy Vault (Monday)

**Morning (9 AM - 10 AM):**
```bash
# 1. Deploy to Railway from GitHub
# https://railway.app/new → Deploy from GitHub

# 2. Configure
railway volume create data --mount /vault/data
TOKEN=$(openssl rand -base64 32)
railway variables set VAULT_TOKEN="$TOKEN"

# 3. Save token
echo "$TOKEN" > ~/railway-vault-token.txt
chmod 600 ~/railway-vault-token.txt

# 4. Test
curl https://your-vault.railway.app/health
```

**Afternoon (2 PM - 4 PM):**
- Monitor vault logs
- Test all API endpoints
- Create backup script
- Prepare migration script for Adajoon

### Day 2: Migrate Adajoon (Tuesday)

**Morning (9 AM - 11 AM):**
```bash
# 1. Add vault variables
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999" --service adajoon
railway variables set VAULT_TOKEN="$TOKEN" --service adajoon

# 2. Migrate secrets
# Edit examples/migrate_secrets.py with Adajoon secrets
python examples/migrate_secrets.py

# 3. Update code
# Add vault_client.py to Adajoon
# Update app.py to fetch secrets from vault

# 4. Deploy
git push

# 5. Test
railway logs -f --service adajoon
curl https://adajoon.railway.app/health
```

**Afternoon (2 PM - 5 PM):**
- Monitor Adajoon logs for errors
- Test all application endpoints
- Verify database connections work
- Check for any auth issues

**Evening (Check before leaving):**
- All endpoints responding normally?
- No errors in logs?
- Database connections stable?

### Day 3: Migrate InfoBank (Wednesday)

**Repeat Adajoon process**

**Morning:**
- Add VAULT_URL + VAULT_TOKEN
- Migrate secrets
- Update code
- Deploy

**Afternoon:**
- Test and monitor
- Verify functionality

### Day 4: Migrate StableBank-Demo (Thursday)

**Critical:** This is your staging environment for StableBank production

**Extra validation:**
```bash
# After deployment, run full test suite
railway run pytest --service stablebank-demo
# or
railway run npm test --service stablebank-demo

# Load test (if applicable)
# artillery run load-test.yml

# Monitor for 24 hours before touching production
```

### Day 5-6: Migrate StableBank Production (Friday)

⚠️ **PRODUCTION - EXTRA CARE REQUIRED**

**Pre-migration (Thursday evening):**
1. [ ] Backup current environment variables
2. [ ] Prepare rollback script
3. [ ] Schedule during low-traffic window
4. [ ] Have monitoring dashboard open
5. [ ] Team on standby

**Migration (Friday low-traffic hours):**

```bash
# 1. Add vault variables (don't remove old ones yet!)
railway variables set VAULT_URL="..." --service stablebank
railway variables set VAULT_TOKEN="$TOKEN" --service stablebank

# 2. Migrate secrets to vault
python examples/migrate_secrets.py

# 3. Deploy new code (still has fallback to env vars)
git push

# 4. Monitor for 30 minutes
railway logs -f --service stablebank

# 5. If all good, restart without old env vars
# (Code should only use vault now)

# 6. Monitor for 4-6 hours minimum
```

**Post-migration monitoring (Friday afternoon):**
- [ ] All endpoints responding?
- [ ] Database connections stable?
- [ ] Payment processing working?
- [ ] No error spikes in logs?
- [ ] Response times normal?

**Cleanup (Monday, after 48h monitoring):**
```bash
# Only if everything is stable!
railway variables delete DATABASE_URL --service stablebank
railway variables delete STRIPE_SECRET_KEY --service stablebank
# ...etc
```

### Day 7: Migrate FlightPrep (Monday)

**Repeat standard process**

### Week 2: Cleanup & Documentation

**Monday:**
- Remove all old secret env vars from all services
- Verify all services still working
- Update internal documentation

**Tuesday:**
- Create runbook for vault operations
- Train team on vault usage
- Set up monitoring alerts

**Wednesday:**
- Backup all secrets
- Test restore procedure
- Document disaster recovery

---

## 🔒 Key Naming Convention

### Format
```
<project>:<key_type>:<optional_env>
```

### Your Projects

**Adajoon:**
```
adajoon:database_url
adajoon:stripe_secret
adajoon:api_key
adajoon:jwt_secret
```

**InfoBank:**
```
infobank:database_url
infobank:api_key
infobank:redis_url
```

**StableBank-Demo:**
```
stablebank:database_url:demo
stablebank:plaid_secret:demo
stablebank:stripe_secret:demo
```

**StableBank (Production):**
```
stablebank:database_url:prod
stablebank:plaid_secret:prod
stablebank:stripe_secret:prod
stablebank:dwolla_key:prod
```

**FlightPrep:**
```
flightprep:database_url
flightprep:api_key
flightprep:weather_api_key
```

---

## 🛡️ Security Best Practices

### DO ✅

1. **Strong tokens**
   ```bash
   openssl rand -base64 32  # 256 bits
   ```

2. **Private networking only**
   ```
   http://kmac-vault.railway.internal:9999
   ```

3. **Token in environment, not code**
   ```python
   token = os.getenv("VAULT_TOKEN")  # ✅
   token = "abc123..."                # ❌
   ```

4. **Regular backups**
   ```bash
   # Weekly backup to encrypted file
   ./backup_secrets.sh
   ```

5. **Token rotation**
   ```
   Every 90 days, generate new token
   ```

### DON'T ❌

1. **Public URLs for vault access**
   ```
   https://vault.railway.app  # ❌ Use private network!
   ```

2. **Log tokens**
   ```python
   print(f"Token: {token}")  # ❌ Never log!
   ```

3. **Commit secrets (even to vault)**
   ```python
   vault.set("key", "hardcoded")  # ❌ Use env vars!
   ```

4. **Share tokens in Slack/email**
   ```
   Use secure channels (1Password, encrypted)
   ```

5. **Use same token everywhere**
   ```
   Dev, staging, prod should have different tokens
   ```

---

## 📈 Monitoring Dashboard

### Key Metrics

```bash
# 1. Vault availability
curl -w "%{http_code}" -o /dev/null -s $VAULT_URL/health
# Expected: 200

# 2. Secret count
curl -s -H "Authorization: Bearer $TOKEN" \
  $VAULT_URL/list | jq '.keys | length'
# Should match your expected count

# 3. Response time
time curl -s $VAULT_URL/health
# Expected: < 100ms

# 4. Service health
railway status
# All services: Running
```

### Alert Conditions

**Critical (Page immediately):**
- Vault service down
- Any production service down
- Error rate > 1% in any service

**Warning (Notify):**
- Vault response time > 500ms
- Secret count changed unexpectedly
- Failed vault connections in logs

**Info (Log):**
- New secret added
- Token rotated
- Service restarted

---

## 💾 Backup Strategy

### Daily Backup (Automated)

```bash
# backup_vault.sh
#!/bin/bash
set -euo pipefail

export VAULT_URL="https://your-vault.railway.app"
export VAULT_TOKEN=$(cat ~/railway-vault-token.txt)

BACKUP_DIR=~/vault-backups
mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/vault_$(date +%Y%m%d_%H%M%S).json"

# Export all secrets
curl -s -H "Authorization: Bearer $VAULT_TOKEN" \
  "$VAULT_URL/list" | jq -r '.keys[]' | while read key; do
    value=$(curl -s -H "Authorization: Bearer $VAULT_TOKEN" \
      "$VAULT_URL/get/$key" | jq -r '.value')
    echo "$key=$value"
done > "$BACKUP_FILE"

# Encrypt
gpg --encrypt --recipient khash@khash.com "$BACKUP_FILE"
rm "$BACKUP_FILE"

echo "✅ Backup saved: ${BACKUP_FILE}.gpg"

# Keep last 30 days
find "$BACKUP_DIR" -name "vault_*.gpg" -mtime +30 -delete
```

### Add to crontab

```bash
crontab -e

# Add daily backup at 2 AM
0 2 * * * ~/backup_vault.sh >> ~/vault_backup.log 2>&1
```

---

## 🎓 Team Training

### For Developers

**Adding a new secret:**
```bash
# 1. SSH into Railway service or use local
export VAULT_URL="https://your-vault.railway.app"
export VAULT_TOKEN="<from-1password>"

# 2. Add secret
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"project:new_api_key","value":"secret-value"}'

# 3. Update code to fetch it
vault.get("project:new_api_key")

# 4. Deploy
git push
```

**Rotating a secret:**
```bash
# 1. Update in vault (same key, new value)
curl -X POST $VAULT_URL/set \
  -H "Authorization: Bearer $VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"project:api_key","value":"new-secret-value"}'

# 2. Restart services
railway restart --service project

# No code changes needed!
```

### For DevOps

**Health checks:**
```bash
# Daily checks
railway status
railway logs --service kmac-vault | tail -50

# Weekly
python verify_all_secrets.py
./backup_vault.sh
```

**Troubleshooting:**
```bash
# Vault not responding
railway logs --service kmac-vault
railway restart --service kmac-vault

# Service can't reach vault
railway run bash --service <service>
curl http://kmac-vault.railway.internal:9999/health

# Secret not found
curl -H "Authorization: Bearer $TOKEN" $VAULT_URL/list
```

---

## 📋 Deployment Checklist

### Pre-Deployment

- [ ] Railway account access verified
- [ ] GitHub repo created and pushed
- [ ] Reviewed all documentation
- [ ] Team briefed on changes
- [ ] Rollback plan documented
- [ ] Low-traffic deployment window scheduled

### Vault Deployment

- [ ] Service deployed to Railway
- [ ] Volume mounted at `/vault/data`
- [ ] VAULT_TOKEN generated (saved securely)
- [ ] Health endpoint verified (200 OK)
- [ ] Private networking enabled
- [ ] Logs showing successful startup
- [ ] Test secret set/get/list/delete

### Service Migration (per service)

- [ ] VAULT_URL and VAULT_TOKEN added
- [ ] Migration script run (secrets copied to vault)
- [ ] Vault client added to codebase
- [ ] Application code updated to use vault
- [ ] Deployed and tested
- [ ] Monitored for 24-48 hours
- [ ] Old environment variables removed
- [ ] Final verification (still works without old vars)

### Post-Deployment

- [ ] All 5 services migrated
- [ ] Backup script created and tested
- [ ] Monitoring alerts configured
- [ ] Team trained
- [ ] Documentation updated
- [ ] Runbook created
- [ ] Success metrics tracked

---

## 🚀 Quick Start (TL;DR)

```bash
# 1. Deploy vault (5 min)
# https://railway.app/new → railway-vault from GitHub
# Add volume: /vault/data
# Set token: openssl rand -base64 32

# 2. For each service (10 min each)
railway variables set VAULT_URL="http://kmac-vault.railway.internal:9999"
railway variables set VAULT_TOKEN="<token>"

# Copy vault client to your app
cp examples/python_client.py your-app/

# Update code:
vault = VaultClient()
DATABASE_URL = vault.get("myapp:database_url")

# Deploy
git push

# 3. After 24h, remove old secrets
railway variables delete DATABASE_URL
railway variables delete API_KEY
# etc...
```

**Total time:** 1 hour to deploy + 1 hour per service = 6 hours spread over 1 week

---

## 💡 Why This Architecture?

### Centralized vs Environment Variables

**Before (Environment Variables):**
```
❌ Secrets visible in Railway dashboard
❌ Secrets in container environment
❌ Each service manages its own secrets
❌ Hard to rotate secrets (update every service)
❌ No audit trail
❌ Easy to commit accidentally
```

**After (Central Vault):**
```
✅ Secrets encrypted in single location
✅ Only VAULT_TOKEN in containers (can be rotated)
✅ Single source of truth
✅ Rotate secrets without redeploying (update vault only)
✅ Audit trail (who accessed what)
✅ Impossible to commit (not in code)
```

### Benefits

1. **Security:**
   - Encrypted at rest (Fernet)
   - No secrets in git, ever
   - Centralized access control
   - Token-based auth

2. **Operability:**
   - Rotate secrets instantly (no redeploy)
   - Add new secrets without code changes
   - Backup/restore all secrets at once
   - Audit who accesses what

3. **Developer Experience:**
   - Simple API (get/set/list/delete)
   - Same pattern across all projects
   - No manual env var management
   - Works in development and production

---

## 📊 Cost Analysis

### Railway Costs

**Vault Service:**
- Compute: ~$5/month (Hobby plan, always-on)
- Volume: ~$1/month (1GB for SQLite database)
- **Total:** ~$6/month

**Savings:**
- Reduced security incidents: Priceless
- Time saved on secret management: ~2 hours/month
- Developer confidence: High

**ROI:** Worth it for any team with > 2 services

---

## 🔄 Rollback Plan

### If Vault Fails Completely

**Quick restore (< 5 minutes per service):**

```bash
# 1. Re-add environment variables from backup
railway variables set DATABASE_URL="..." --service adajoon
railway variables set STRIPE_SECRET="..." --service adajoon
# ...etc

# 2. Revert code changes
cd ~/Projects/Adajoon
git revert HEAD~3..HEAD  # Revert vault integration commits
git push

# 3. Restart
railway restart --service adajoon

# 4. Verify
curl https://adajoon.railway.app/health
```

**Backup restoration (if you backed up vault):**

```bash
# 1. Deploy new vault
railway up

# 2. Restore from backup
gpg --decrypt ~/vault-backups/vault_20260412.json.gpg | \
while IFS='=' read -r key value; do
    curl -X POST $VAULT_URL/set \
      -H "Authorization: Bearer $VAULT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"key\":\"$key\",\"value\":\"$value\"}"
done

# 3. Restart all services
railway restart --all

# 4. Verify
railway status
```

---

## 📞 Support & Resources

### Documentation
- [README.md](README.md) - Feature overview
- [DEPLOY.md](DEPLOY.md) - Deployment instructions
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Step-by-step setup
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - API reference

### Code Examples
- `examples/python_client.py` - Python vault client
- `examples/nodejs_client.js` - Node.js vault client
- `examples/migrate_secrets.py` - Migration script

### Railway Resources
- Railway Dashboard: https://railway.app
- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway

### KMac-CLI (Original Project)
- GitHub: https://github.com/ksarrafi/KMAC-CLI
- Docs: See `docs/` folder for vault guides

---

## ✅ Go/No-Go Criteria

**Go** if all true:
- ✅ Vault deployed and healthy
- ✅ Token generated and saved
- ✅ Volume mounted and persistent
- ✅ Test secrets can be set/get/deleted
- ✅ Private networking working
- ✅ Rollback plan ready
- ✅ Team briefed

**No-Go** if any true:
- ❌ Vault health check failing
- ❌ Volume not persistent (data loss on restart)
- ❌ Token not saved (can't recover)
- ❌ Private networking not enabled
- ❌ No rollback plan
- ❌ Production deployment on Friday afternoon

---

## 🎯 Next Action

**Right now:**

1. Go to: https://railway.app/new
2. Click: "Deploy from GitHub repo"
3. Select: `ksarrafi/railway-vault`
4. Click: "Deploy"
5. Wait 2 minutes
6. Add volume: `/vault/data`
7. Generate token: `openssl rand -base64 32`
8. Set token: Railway dashboard → Variables → Add
9. Test: `curl https://your-vault.railway.app/health`

**Then:**

Come back here and follow Day 2 plan (Adajoon migration)

---

**Status:** ✅ Ready to deploy  
**Repository:** https://github.com/ksarrafi/railway-vault  
**Contact:** khash@khash.com  
**Good luck! 🚀**
