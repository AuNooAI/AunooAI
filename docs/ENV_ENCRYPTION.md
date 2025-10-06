# .env File Encryption System

**Version**: 1.1.0
**Status**: Production-Ready
**Deployed**: wip.aunoo.ai (2025-10-06)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Deployment](#deployment)
6. [Credential Rotation](#credential-rotation)
7. [Security](#security)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## Overview

The .env encryption system provides transparent encryption-at-rest for environment variables using AES-256-GCM. Environment files are automatically decrypted when services start and re-encrypted when they stop, ensuring credentials are never stored in plaintext on disk.

### Key Features

- ✅ **AES-256-GCM Encryption**: Industry-standard authenticated encryption
- ✅ **Automatic Lifecycle**: Decrypt on start, re-encrypt on stop
- ✅ **Transparent to Apps**: Applications read plaintext .env normally
- ✅ **Audit Logging**: All operations logged with timestamps
- ✅ **Shared Defaults**: Optional shared API keys across tenants
- ✅ **Safe Rotation**: Automated credential rotation with rollback
- ✅ **Git Protected**: Automatic .gitignore configuration

### Security Benefits

| Aspect | Before | After |
|--------|--------|-------|
| Storage at rest | Plaintext (640) | AES-256-GCM encrypted (400) |
| Backup exposure | Credentials visible | Encrypted backups |
| Access control | Group readable | Owner-only (400) |
| Audit trail | None | All operations logged |
| Tamper detection | None | HMAC authentication tag |
| Git commits | Manual prevention | Auto .gitignore + scanning |

---

## Architecture

### File Structure

```
/home/orochford/
├── .env-master-key                    # AES-256 master key (400)
├── .env-defaults.encrypted            # Shared API keys (400) [optional]
├── .env-backups/                      # Rotation backups by timestamp
│   └── 20251006_120000/
│       ├── wip.aunoo.ai.env.encrypted
│       └── staging.aunoo.ai.env.encrypted
├── bin/
│   ├── .venv/                         # Python virtual environment
│   │   ├── bin/python3
│   │   └── lib/python3.12/site-packages/
│   │       ├── cryptography/          # AES-GCM implementation
│   │       └── dotenv/                # .env parsing
│   ├── env_encryption.py              # Core encryption utility
│   ├── deploy_site.py                 # Tenant deployment
│   ├── rotate_credential.sh           # Credential rotation
│   └── requirements.txt               # Python dependencies
└── tenants/
    ├── wip.aunoo.ai/
    │   ├── .env.encrypted             # Encrypted at rest (400)
    │   ├── .env                       # EXISTS ONLY DURING RUNTIME (600)
    │   └── .env.example               # Template for git (644)
    └── staging.aunoo.ai/
        └── ...

/var/log/
├── aunoo-env-access.log               # Encryption operations audit
└── aunoo-credential-rotations.log     # Rotation history

/etc/systemd/system/
├── wip.aunoo.ai.service               # Service with encryption hooks
└── staging.aunoo.ai.service
```

### Encryption Flow

```
┌─────────────────────┐
│  Service Start      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│ ExecStartPre:                                   │
│ env_encryption.py decrypt /path/to/tenant       │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│ .env.encrypted → .env                           │
│ • Load master key                               │
│ • Extract salt + nonce from encrypted file     │
│ • Derive file-specific key (PBKDF2)            │
│ • Decrypt with AES-256-GCM                      │
│ • Verify authentication tag                     │
│ • Write plaintext .env (600 permissions)        │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────┐
│ Application Runs    │
│ Reads .env normally │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Service Stop       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│ ExecStopPost:                                   │
│ env_encryption.py encrypt /path/to/tenant       │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────┐
│ .env → .env.encrypted                           │
│ • Generate random salt + nonce                  │
│ • Derive file-specific key (PBKDF2)            │
│ • Encrypt with AES-256-GCM                      │
│ • Append authentication tag                     │
│ • Write encrypted file (400 permissions)        │
│ • Delete plaintext .env                         │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌─────────────────────┐
│ .env.encrypted only │
│ Plaintext deleted   │
└─────────────────────┘
```

### Encryption Details

**Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Key Size**: 256 bits (32 bytes)
- **Authentication**: HMAC-based authentication tag
- **Nonce**: 96 bits (12 bytes) - random per encryption
- **Salt**: 128 bits (16 bytes) - random per file
- **Key Derivation**: PBKDF2-HMAC-SHA256 (100,000 iterations)

**Encrypted File Format**:
```
[salt (16 bytes)][nonce (12 bytes)][ciphertext + auth_tag]
```

**Security Properties**:
- **Confidentiality**: AES-256 encryption
- **Integrity**: GCM authentication tag prevents tampering
- **Authenticity**: HMAC verifies data hasn't been modified
- **Uniqueness**: Random salt + nonce per encryption

---

## Installation

### Prerequisites

- Python 3.8+
- systemd
- Root/sudo access

### Step 1: Install Scripts

```bash
# Create bin directory
sudo mkdir -p /home/orochford/bin
sudo chown orochford:orochford /home/orochford/bin

# Copy scripts (from deployment package or git)
sudo cp env_encryption.py deploy_site.py rotate_credential.sh requirements.txt /home/orochford/bin/
sudo chown orochford:orochford /home/orochford/bin/*
sudo chmod +x /home/orochford/bin/env_encryption.py /home/orochford/bin/rotate_credential.sh
```

### Step 2: Create Virtual Environment

```bash
cd /home/orochford/bin

# Create venv
python3 -m venv .venv
chown -R orochford:orochford .venv

# Install dependencies
.venv/bin/pip install -r requirements.txt
```

**Dependencies**:
- `cryptography>=41.0.0` - AES-GCM encryption
- `python-dotenv>=1.0.0` - .env file parsing

### Step 3: Initialize Encryption System

```bash
sudo /home/orochford/bin/env_encryption.py init
```

**Output**:
```
INFO: Master key saved to /home/orochford/.env-master-key (permissions: 400)
INFO: ======================================================================
INFO: ✓ Encryption system initialized
INFO: ======================================================================
INFO: Master key: /home/orochford/.env-master-key
INFO: Audit log:  /var/log/aunoo-env-access.log
INFO:
INFO: ⚠️  IMPORTANT: Back up the master key securely!
INFO:
INFO: Recommended backup procedure:
INFO:   1. Encrypt the master key with a passphrase:
INFO:      openssl enc -aes-256-cbc -salt -pbkdf2 \
INFO:        -in /home/orochford/.env-master-key \
INFO:        -out /home/orochford/.env-master-key.encrypted
INFO:   2. Store encrypted backup off-server (secure vault)
INFO:   3. Document passphrase in password manager
INFO: ======================================================================
```

### Step 4: Back Up Master Key

**CRITICAL**: Without the master key, encrypted .env files cannot be decrypted.

```bash
# Encrypt the master key with a passphrase
sudo openssl enc -aes-256-cbc -salt -pbkdf2 \
  -in /home/orochford/.env-master-key \
  -out /home/orochford/.env-master-key.encrypted

# Enter a strong passphrase when prompted
# Store this in a password manager (1Password, LastPass, etc.)

# Copy encrypted backup off-server
scp /home/orochford/.env-master-key.encrypted backup@secure-server:/backups/

# Verify you can decrypt it
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in /home/orochford/.env-master-key.encrypted \
  -out /tmp/test-master-key

# Compare checksums
md5sum /home/orochford/.env-master-key /tmp/test-master-key

# Clean up test
rm /tmp/test-master-key
```

---

## Usage

### Command-Line Interface

#### Initialize System

```bash
env_encryption.py init
```

Generates master key and creates audit log. Run once per server.

#### Encrypt .env File

```bash
env_encryption.py encrypt /path/to/tenant
```

**Example**:
```bash
# Encrypt wip.aunoo.ai's .env
sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/wip.aunoo.ai
```

**Before**:
```
/home/orochford/tenants/wip.aunoo.ai/
├── .env (600, plaintext)
```

**After**:
```
/home/orochford/tenants/wip.aunoo.ai/
├── .env.encrypted (400, encrypted)
```

**Output**:
```
INFO: Read 1984 bytes from /home/orochford/tenants/wip.aunoo.ai/.env
INFO: Wrote 2028 bytes to /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
INFO: Deleted plaintext /home/orochford/tenants/wip.aunoo.ai/.env
INFO: ✓ Encrypted wip.aunoo.ai/.env
```

#### Decrypt .env File

```bash
env_encryption.py decrypt /path/to/tenant
```

**Example**:
```bash
# Decrypt wip.aunoo.ai's .env (temporarily)
sudo /home/orochford/bin/env_encryption.py decrypt /home/orochford/tenants/wip.aunoo.ai
```

**Before**:
```
/home/orochford/tenants/wip.aunoo.ai/
├── .env.encrypted (400, encrypted)
```

**After**:
```
/home/orochford/tenants/wip.aunoo.ai/
├── .env.encrypted (400, encrypted)
├── .env (600, plaintext)
```

**Output**:
```
INFO: Read 2028 bytes from /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
INFO: Wrote 1984 bytes to /home/orochford/tenants/wip.aunoo.ai/.env
INFO: ✓ Decrypted wip.aunoo.ai/.env
```

**⚠️ IMPORTANT**: Re-encrypt after use!
```bash
sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/wip.aunoo.ai
```

#### Verify Encrypted File

```bash
env_encryption.py verify /path/to/tenant
```

**Example**:
```bash
sudo /home/orochford/bin/env_encryption.py verify /home/orochford/tenants/wip.aunoo.ai
```

**Output** (success):
```
INFO: ✓ Verified wip.aunoo.ai/.env.encrypted (decrypts to 1984 bytes)
```

**Output** (failure):
```
ERROR: Verification failed: Decryption failed: ...
```

### Systemd Service Integration

Services automatically decrypt on start and re-encrypt on stop.

**Service File Template**:
```ini
[Unit]
Description=FastAPI {domain}
After=network.target

[Service]
Type=simple
User=orochford
Group=orochford
WorkingDirectory=/home/orochford/tenants/{domain}
Environment=ENVIRONMENT=production

# Decrypt .env before starting
ExecStartPre=/home/orochford/bin/.venv/bin/python3 /home/orochford/bin/env_encryption.py decrypt /home/orochford/tenants/{domain}

# Start application
ExecStart=/home/orochford/tenants/{domain}/.venv/bin/python /home/orochford/tenants/{domain}/app/server_run.py

# Re-encrypt .env after stopping
ExecStopPost=/home/orochford/bin/.venv/bin/python3 /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/{domain}

# Clean up plaintext .env on crash/stop
ExecStopPost=/bin/rm -f /home/orochford/tenants/{domain}/.env

Restart=on-failure
RestartSec=3
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
```

**Service Lifecycle**:

1. **Start**: `systemctl start wip.aunoo.ai`
   - ExecStartPre decrypts .env
   - Service reads plaintext .env

2. **Running**: Service operates normally
   - .env exists in plaintext (600)
   - .env.encrypted exists (400)

3. **Stop**: `systemctl stop wip.aunoo.ai`
   - Service shuts down
   - ExecStopPost re-encrypts .env
   - ExecStopPost deletes plaintext .env

4. **At Rest**: Only encrypted file exists
   - .env.encrypted (400)
   - No plaintext .env

---

## Deployment

### Deploy New Tenant

Use `deploy_site.py` to deploy new tenant instances with automatic .env creation and encryption.

```bash
sudo /home/orochford/bin/deploy_site.py \
  --repo https://github.com/yourorg/aunooai.git \
  --branch main \
  --domain app.example.com \
  --email admin@example.com
```

**What it does**:

1. **Clone Repository**
   ```
   git clone -b main https://github.com/yourorg/aunooai.git /home/orochford/tenants/app.example.com
   ```

2. **Create Python Environment**
   ```
   python3 -m venv /home/orochford/tenants/app.example.com/.venv
   pip install -r requirements.txt
   ```

3. **Create .env File**
   - If `/home/orochford/.env-defaults.encrypted` exists:
     - Decrypt shared defaults
     - Merge with tenant-specific config
   - Generate secrets:
     - FLASK_SECRET_KEY (random 32 bytes)
     - NORN_SECRET_KEY (random 32 bytes)
   - Add tenant config:
     - PORT (auto-assigned from 10000-10999)
     - DOMAIN (from --domain argument)

4. **Encrypt .env**
   ```
   env_encryption.py encrypt /home/orochford/tenants/app.example.com
   ```

5. **Create Systemd Service**
   - Write service file with encryption hooks
   - Enable service
   - Start service

6. **Configure NGINX + SSL**
   - Create NGINX vhost
   - Run certbot for SSL certificate
   - Proxy to application port

7. **Create Deployment Info**
   - Generate admin password
   - Save to DEPLOYMENT_INFO.txt

### Shared Defaults (Optional)

Share common API keys across all tenants.

**Create Shared Defaults**:

```bash
# 1. Create .env with shared keys
sudo vim /home/orochford/.env-defaults
```

```bash
# Shared API Keys
OPENAI_API_KEY=sk-proj-abc123...
ANTHROPIC_API_KEY=sk-ant-xyz789...
GOOGLE_API_KEY=AIza...

# News APIs
PROVIDER_NEWSAPI_KEY=def456...
PROVIDER_THENEWSAPI_KEY=ghi789...

# Other Services
DIA_API_KEY=jkl012...
PROVIDER_FIRECRAWL_KEY=fc-mno345...
ELEVENLABS_API_KEY=sk_pqr678...
```

```bash
# 2. Create temporary directory for encryption
mkdir -p /tmp/env-defaults-temp
cp /home/orochford/.env-defaults /tmp/env-defaults-temp/.env

# 3. Encrypt
sudo /home/orochford/bin/env_encryption.py encrypt /tmp/env-defaults-temp

# 4. Move to final location
sudo mv /tmp/env-defaults-temp/.env.encrypted /home/orochford/.env-defaults.encrypted

# 5. Set permissions
sudo chmod 400 /home/orochford/.env-defaults.encrypted
sudo chown orochford:orochford /home/orochford/.env-defaults.encrypted

# 6. Cleanup
rm -rf /tmp/env-defaults-temp
rm /home/orochford/.env-defaults  # Delete plaintext
```

**Usage**:

Now when deploying new tenants, they'll automatically include these shared keys:

```bash
sudo /home/orochford/bin/deploy_site.py \
  --repo https://github.com/yourorg/aunooai.git \
  --domain new-tenant.example.com \
  --email admin@example.com
```

The new tenant's .env will contain:
- Shared API keys from `.env-defaults.encrypted`
- Auto-generated FLASK_SECRET_KEY and NORN_SECRET_KEY
- Tenant-specific PORT and DOMAIN

### Migrate Existing Tenant

Convert existing plaintext .env to encrypted.

```bash
# 1. Navigate to tenant
cd /home/orochford/tenants/existing.aunoo.ai

# 2. Backup current .env
sudo cp .env .env.backup.pre-encryption

# 3. Fix permissions (if needed)
sudo chmod 600 .env
sudo chown orochford:orochford .env

# 4. Encrypt
sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/existing.aunoo.ai

# 5. Update systemd service
sudo vim /etc/systemd/system/existing.aunoo.ai.service
```

**Add to service file**:
```ini
# Decrypt .env before starting
ExecStartPre=/home/orochford/bin/.venv/bin/python3 /home/orochford/bin/env_encryption.py decrypt /home/orochford/tenants/existing.aunoo.ai

# Re-encrypt .env after stopping
ExecStopPost=/home/orochford/bin/.venv/bin/python3 /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/existing.aunoo.ai

# Clean up plaintext .env on crash/stop
ExecStopPost=/bin/rm -f /home/orochford/tenants/existing.aunoo.ai/.env
```

```bash
# 6. Reload systemd
sudo systemctl daemon-reload

# 7. Restart service
sudo systemctl restart existing.aunoo.ai

# 8. Verify
sudo systemctl status existing.aunoo.ai
ls -la .env*
```

---

## Credential Rotation

### Rotate Credential

Use `rotate_credential.sh` to safely rotate credentials across tenants.

**Syntax**:
```bash
rotate_credential.sh CREDENTIAL_NAME NEW_VALUE [SCOPE]
```

**Scopes**:
- `all` - Rotate in all tenants (default)
- `<tenant>` - Rotate in specific tenant only

### Examples

#### Rotate OpenAI API Key (All Tenants)

```bash
sudo /home/orochford/bin/rotate_credential.sh OPENAI_API_KEY sk-proj-newkey123
```

**Process**:
1. Creates backup: `/home/orochford/.env-backups/20251006_120000/`
2. For each tenant:
   - Decrypt .env.encrypted → .env
   - Update OPENAI_API_KEY in .env
   - Re-encrypt .env → .env.encrypted
3. Restart affected services
4. Verify all services running
5. Log rotation event

**Output**:
```
═══════════════════════════════════════════════════════
   Credential Rotation
═══════════════════════════════════════════════════════
Credential: OPENAI_API_KEY
Scope:      all
Backup:     /home/orochford/.env-backups/20251006_120000

Rotating in all tenants...
  → Rotating in wip.aunoo.ai...
    ✓ Rotated
  → Rotating in staging.aunoo.ai...
    ✓ Rotated
  → Rotating in testing.aunoo.ai...
    ✓ Rotated

Restarting services...
  → Restarting wip.aunoo.ai.service...
    ✓ Running
  → Restarting staging.aunoo.ai.service...
    ✓ Running
  → Restarting testing.aunoo.ai.service...
    ✓ Running

═══════════════════════════════════════════════════════
   Summary
═══════════════════════════════════════════════════════
✓ Rotated successfully: 3 tenant(s)
  • wip.aunoo.ai
  • staging.aunoo.ai
  • testing.aunoo.ai

✓ Credential rotation complete
Backups: /home/orochford/.env-backups/20251006_120000
```

#### Rotate Flask Secret (Specific Tenant)

```bash
sudo /home/orochford/bin/rotate_credential.sh FLASK_SECRET_KEY newsecret123 wip.aunoo.ai
```

**Output**:
```
═══════════════════════════════════════════════════════
   Credential Rotation
═══════════════════════════════════════════════════════
Credential: FLASK_SECRET_KEY
Scope:      wip.aunoo.ai
Backup:     /home/orochford/.env-backups/20251006_120500

  → Rotating in wip.aunoo.ai...
    ✓ Rotated

Restarting services...
  → Restarting wip.aunoo.ai.service...
    ✓ Running

═══════════════════════════════════════════════════════
   Summary
═══════════════════════════════════════════════════════
✓ Rotated successfully: 1 tenant(s)
  • wip.aunoo.ai

✓ Credential rotation complete
Backups: /home/orochford/.env-backups/20251006_120500
```

### Rotation Rollback

If rotation fails, restore from backup:

```bash
# 1. Find latest backup
ls -lt /home/orochford/.env-backups/ | head -5

# 2. Stop affected service
sudo systemctl stop wip.aunoo.ai

# 3. Restore backup
sudo cp /home/orochford/.env-backups/20251006_120000/wip.aunoo.ai.env.encrypted \
        /home/orochford/tenants/wip.aunoo.ai/.env.encrypted

# 4. Fix ownership
sudo chown orochford:orochford /home/orochford/tenants/wip.aunoo.ai/.env.encrypted

# 5. Start service
sudo systemctl start wip.aunoo.ai

# 6. Verify
sudo systemctl status wip.aunoo.ai
```

### Rotation Schedule

Recommended rotation schedule:

| Credential Type | Frequency | Notes |
|----------------|-----------|-------|
| API Keys (OpenAI, Anthropic) | Quarterly | Rotate every 3 months |
| Service Keys (NewsAPI, etc.) | Annually | Rotate yearly |
| FLASK_SECRET_KEY | Never* | Only on compromise or personnel change |
| NORN_SECRET_KEY | Never* | Only on compromise or personnel change |

*Rotating Flask/Norn secret keys invalidates all user sessions

---

## Security

### File Permissions

All encryption-related files use strict permissions:

| File | Permissions | Owner | Purpose |
|------|------------|-------|---------|
| `.env-master-key` | 400 | orochford:orochford | Master encryption key |
| `.env-defaults.encrypted` | 400 | orochford:orochford | Shared API keys |
| `.env.encrypted` | 400 | orochford:orochford | Tenant credentials |
| `.env` | 600 | orochford:orochford | Plaintext (runtime only) |
| `.env.example` | 644 | orochford:orochford | Template for git |

**Verify permissions**:
```bash
# Check master key
ls -la /home/orochford/.env-master-key
# Should show: -r-------- orochford orochford

# Check tenant encrypted file
ls -la /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
# Should show: -r-------- orochford orochford

# Check audit log
ls -la /var/log/aunoo-env-access.log
# Should show: -rw-rw-rw- or -rw-r--r--
```

**Fix permissions**:
```bash
# Fix master key
sudo chmod 400 /home/orochford/.env-master-key
sudo chown orochford:orochford /home/orochford/.env-master-key

# Fix tenant encrypted files
sudo chmod 400 /home/orochford/tenants/*/.env.encrypted
sudo chown orochford:orochford /home/orochford/tenants/*/.env.encrypted
```

### Audit Logging

All encryption operations are logged to `/var/log/aunoo-env-access.log`.

**Log Format**:
```
YYYY-MM-DD HH:MM:SS | LEVEL | OPERATION | TENANT | USER | STATUS [| ERROR]
```

**Example**:
```
2025-10-06 12:09:38 | INFO | INIT | system | orochford | SUCCESS
2025-10-06 12:13:38 | INFO | ENCRYPT | wip.aunoo.ai | orochford | SUCCESS
2025-10-06 12:15:15 | INFO | DECRYPT | wip.aunoo.ai | orochford | SUCCESS
2025-10-06 12:16:00 | INFO | ENCRYPT | wip.aunoo.ai | orochford | SUCCESS
2025-10-06 12:14:53 | INFO | DECRYPT | wip.aunoo.ai | orochford | FAILURE | [Errno 13] Permission denied
```

**Monitor audit log**:
```bash
# Tail in real-time
tail -f /var/log/aunoo-env-access.log

# View recent operations
tail -50 /var/log/aunoo-env-access.log

# Search for failures
grep FAILURE /var/log/aunoo-env-access.log

# Count operations by type
grep -c ENCRYPT /var/log/aunoo-env-access.log
grep -c DECRYPT /var/log/aunoo-env-access.log
```

### Git Protection

The deployment system automatically protects .env files from git commits.

**Automatic .gitignore**:

When `deploy_site.py` runs or `setup_env_file()` is called, it adds:

```gitignore
# Environment variables (NEVER commit these!)
.env
.env.*
!.env.example
```

**Manual check**:
```bash
# Verify .env is in .gitignore
cd /home/orochford/tenants/wip.aunoo.ai
cat .gitignore | grep .env

# Check if .env is tracked
git ls-files | grep -E '^\.env$'
# Should return nothing

# Check git history
git log --all --full-history --oneline -- .env
# Should return nothing (or very old commits before encryption)
```

**If .env is in git**:
```bash
# Remove from staging
git reset HEAD .env

# Remove from git (keep local file)
git rm --cached .env

# Commit removal
git commit -m "Remove .env from git tracking (now encrypted)"

# Add to .gitignore if not already there
echo -e "\n# Environment variables\n.env\n.env.*\n!.env.example" >> .gitignore
git add .gitignore
git commit -m "Add .env to .gitignore"
```

### Best Practices

#### ✅ DO

1. **Back up master key** (encrypted, off-server)
   ```bash
   openssl enc -aes-256-cbc -salt -pbkdf2 \
     -in /home/orochford/.env-master-key \
     -out /home/orochford/.env-master-key.encrypted
   ```

2. **Rotate credentials quarterly**
   ```bash
   sudo /home/orochford/bin/rotate_credential.sh OPENAI_API_KEY new-key all
   ```

3. **Monitor audit logs**
   ```bash
   tail -f /var/log/aunoo-env-access.log
   ```

4. **Use shared defaults for consistency**
   ```bash
   # Create /home/orochford/.env-defaults.encrypted
   ```

5. **Test rotation in staging first**
   ```bash
   sudo /home/orochford/bin/rotate_credential.sh TEST_KEY test staging.aunoo.ai
   ```

6. **Verify backups are encrypted**
   ```bash
   file /home/orochford/.env-backups/*/*.env.encrypted
   ```

7. **Keep master key passphrase in password manager**
   - 1Password, LastPass, Bitwarden, etc.

#### ❌ DON'T

1. **Commit .env or .env.encrypted to git**
   - Always in .gitignore

2. **Share master key via email/chat**
   - Use secure vault or in-person handoff

3. **Run services as root**
   - Always use orochford user

4. **Store plaintext credentials anywhere**
   - Always encrypted at rest

5. **Skip rotation after personnel changes**
   - Rotate immediately when staff leaves

6. **Edit .env.encrypted directly**
   - Always decrypt → edit → re-encrypt

7. **Delete .env-backups immediately**
   - Keep for 30-90 days for rollback

8. **Use same credentials across environments**
   - Separate staging/production keys

---

## Troubleshooting

### Service Won't Start

**Symptom**: `systemctl status <service>` shows failed

**Check**:
```bash
# View service logs
sudo journalctl -xeu wip.aunoo.ai.service | tail -50

# View encryption logs
tail -20 /var/log/aunoo-env-access.log

# Check for .env files
ls -la /home/orochford/tenants/wip.aunoo.ai/.env*
```

**Common Causes**:

1. **Permission denied on master key**
   ```
   ERROR: [Errno 13] Permission denied: '/home/orochford/.env-master-key'
   ```

   **Fix**:
   ```bash
   sudo chown orochford:orochford /home/orochford/.env-master-key
   sudo chmod 400 /home/orochford/.env-master-key
   ```

2. **Permission denied on .env.encrypted**
   ```
   ERROR: [Errno 13] Permission denied: '/home/orochford/tenants/wip.aunoo.ai/.env.encrypted'
   ```

   **Fix**:
   ```bash
   sudo chown orochford:orochford /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
   sudo chmod 400 /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
   ```

3. **.env.encrypted not found**
   ```
   ERROR: .env.encrypted not found: /home/orochford/tenants/wip.aunoo.ai/.env.encrypted
   ```

   **Fix**: Encrypt existing .env
   ```bash
   sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/wip.aunoo.ai
   ```

4. **Decryption failed (corrupted file)**
   ```
   ERROR: Decryption failed: ...
   ```

   **Fix**: Restore from backup
   ```bash
   sudo cp /home/orochford/tenants/wip.aunoo.ai/.env.backup.pre-encryption \
           /home/orochford/tenants/wip.aunoo.ai/.env
   sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/wip.aunoo.ai
   ```

### Master Key Lost

**Symptom**: Cannot decrypt any .env.encrypted files

**Recovery**:

1. **Check for backup**
   ```bash
   ls -la /home/orochford/.env-master-key*
   ```

2. **If encrypted backup exists**
   ```bash
   # Decrypt backup
   openssl enc -d -aes-256-cbc -pbkdf2 \
     -in /home/orochford/.env-master-key.encrypted \
     -out /home/orochford/.env-master-key

   # Enter passphrase

   # Fix permissions
   sudo chmod 400 /home/orochford/.env-master-key
   sudo chown orochford:orochford /home/orochford/.env-master-key
   ```

3. **If no backup exists**
   - **Cannot recover** encrypted .env files
   - Must manually recreate .env from:
     - DEPLOYMENT_INFO.txt (admin password)
     - API provider dashboards (regenerate keys)
     - Documentation
   - Generate new master key: `sudo /home/orochford/bin/env_encryption.py init`
   - Re-encrypt all .env files

### ModuleNotFoundError: cryptography

**Symptom**: Script fails with module not found

**Cause**: Virtual environment not set up or dependencies not installed

**Fix**:
```bash
cd /home/orochford/bin

# Check if venv exists
ls -la .venv

# If not, create it
python3 -m venv .venv

# Install dependencies
.venv/bin/pip install -r requirements.txt

# Verify
.venv/bin/python3 -c "import cryptography; print(cryptography.__version__)"
```

### Plaintext .env Left Behind

**Symptom**: .env file exists when service is stopped

**Cause**: ExecStopPost didn't run (crash, kill -9, etc.)

**Fix**:
```bash
# Manually re-encrypt
sudo /home/orochford/bin/env_encryption.py encrypt /home/orochford/tenants/wip.aunoo.ai

# Verify plaintext deleted
ls -la /home/orochford/tenants/wip.aunoo.ai/.env
# Should show: No such file or directory
```

**Prevention**: Use `systemctl stop` instead of `kill -9`

### Rotation Failed - Service Won't Start

**Symptom**: After rotation, service fails to start

**Cause**: Credential update failed or service can't start with new credential

**Recovery**:
```bash
# 1. Stop service
sudo systemctl stop wip.aunoo.ai

# 2. Find backup
ls -lt /home/orochford/.env-backups/ | head -5

# 3. Restore backup
sudo cp /home/orochford/.env-backups/20251006_120000/wip.aunoo.ai.env.encrypted \
        /home/orochford/tenants/wip.aunoo.ai/.env.encrypted

# 4. Fix ownership
sudo chown orochford:orochford /home/orochford/tenants/wip.aunoo.ai/.env.encrypted

# 5. Start service
sudo systemctl start wip.aunoo.ai

# 6. Verify
sudo systemctl status wip.aunoo.ai
```

---

## API Reference

### env_encryption.py

#### `init`

Initialize encryption system (one-time setup).

**Usage**:
```bash
env_encryption.py init
```

**Actions**:
- Generates 32-byte master key
- Saves to `/home/orochford/.env-master-key` (400 permissions)
- Creates audit log at `/var/log/aunoo-env-access.log`
- Displays backup instructions

**Returns**: Exit code 0 on success, 1 on failure

---

#### `encrypt <workdir>`

Encrypt .env file to .env.encrypted.

**Usage**:
```bash
env_encryption.py encrypt /path/to/tenant
```

**Arguments**:
- `workdir`: Path to tenant directory containing .env

**Actions**:
- Reads plaintext .env
- Generates random salt (16 bytes)
- Generates random nonce (12 bytes)
- Derives file key from master key + salt (PBKDF2, 100k iterations)
- Encrypts with AES-256-GCM
- Writes encrypted file with format: `[salt][nonce][ciphertext+tag]`
- Sets permissions to 400
- Deletes plaintext .env
- Logs operation to audit log

**Returns**: Exit code 0 on success, 1 on failure

**Errors**:
- `.env not found`: No .env file in workdir
- `Master key not found`: Run `init` first
- `Permission denied`: Check file/directory permissions

---

#### `decrypt <workdir>`

Decrypt .env.encrypted to .env (temporary).

**Usage**:
```bash
env_encryption.py decrypt /path/to/tenant
```

**Arguments**:
- `workdir`: Path to tenant directory containing .env.encrypted

**Actions**:
- Reads .env.encrypted
- Extracts salt, nonce, and ciphertext+tag
- Derives file key from master key + salt
- Decrypts with AES-256-GCM
- Verifies authentication tag
- Writes plaintext .env (600 permissions)
- Logs operation to audit log

**Returns**: Exit code 0 on success, 1 on failure

**Errors**:
- `.env.encrypted not found`: No encrypted file
- `Decryption failed`: Wrong key, corrupted file, or tampered data
- `Permission denied`: Check file/directory permissions

**⚠️ WARNING**: Plaintext .env left on disk. Re-encrypt when done!

---

#### `verify <workdir>`

Verify .env.encrypted can be decrypted (without writing .env).

**Usage**:
```bash
env_encryption.py verify /path/to/tenant
```

**Arguments**:
- `workdir`: Path to tenant directory containing .env.encrypted

**Actions**:
- Reads .env.encrypted
- Attempts to decrypt in memory
- Verifies authentication tag
- Logs operation to audit log
- Does NOT write plaintext .env to disk

**Returns**: Exit code 0 if valid, 1 if invalid or error

**Use Cases**:
- Verify encrypted file integrity
- Check if master key can decrypt
- Test encryption/decryption cycle

---

### deploy_site.py

Deploy new tenant with automatic .env creation and encryption.

**Usage**:
```bash
deploy_site.py --repo <git-url> --branch <branch> --domain <domain> --email <email>
```

**Required Arguments**:
- `--repo`: Git repository URL
- `--domain`: Domain name (e.g., app.example.com)
- `--email`: Email for SSL certificate

**Optional Arguments**:
- `--branch`: Git branch (default: experimental_clean)
- `--enable-modsec`: Enable ModSecurity
- `--modsec-file`: Path to ModSecurity config
- `--git-token`: Git personal access token
- `--git-username`: Git username
- `--git-password`: Git password

**Actions**:
1. Clones repository to `/home/orochford/tenants/<domain>`
2. Creates Python venv and installs dependencies
3. Finds free port (10000-10999)
4. Creates .env file:
   - Loads shared defaults from .env-defaults.encrypted (if exists)
   - Generates FLASK_SECRET_KEY and NORN_SECRET_KEY
   - Sets PORT and DOMAIN
5. Encrypts .env → .env.encrypted
6. Creates systemd service with encryption hooks
7. Configures NGINX with SSL
8. Starts service
9. Creates DEPLOYMENT_INFO.txt with admin password

**Returns**: Exit code 0 on success, 1 on failure

---

### rotate_credential.sh

Rotate credential across tenants.

**Usage**:
```bash
rotate_credential.sh CREDENTIAL_NAME NEW_VALUE [SCOPE]
```

**Arguments**:
- `CREDENTIAL_NAME`: Name of environment variable (e.g., OPENAI_API_KEY)
- `NEW_VALUE`: New value for credential
- `SCOPE`: Optional scope (default: all)
  - `all`: All tenants
  - `<tenant>`: Specific tenant (e.g., wip.aunoo.ai)

**Actions**:
1. Creates backup directory with timestamp
2. For each tenant in scope:
   - Backs up .env.encrypted
   - Decrypts .env
   - Updates credential with sed
   - Re-encrypts .env
3. Restarts affected services
4. Verifies services started successfully
5. Logs rotation to /var/log/aunoo-credential-rotations.log

**Returns**: Exit code 0 on success, 1 on failure

**Rollback**: Backups stored in `/home/orochford/.env-backups/<timestamp>/`

---

## Appendix

### Encryption Performance

| Operation | File Size | Time | Overhead |
|-----------|-----------|------|----------|
| Encrypt | 2KB .env | ~50ms | +2.2% size |
| Decrypt | 2KB .env | ~50ms | - |
| Service Start | - | +200ms | Decrypt |
| Service Stop | - | +200ms | Encrypt |

**Impact**: Negligible for typical deployments. Services start in 5-8s, encryption adds ~0.2s.

### File Size Comparison

```
Original .env:        1984 bytes
Encrypted .env:       2028 bytes  (+44 bytes, 2.2%)
Breakdown:
  - Salt:             16 bytes
  - Nonce:            12 bytes
  - Auth Tag:         16 bytes
  - Ciphertext:       1984 bytes
```

### Security Audit

**Encryption Strength**: AES-256-GCM is NIST-approved and used by:
- TLS 1.3
- AWS Encryption SDK
- Google Cloud KMS
- Azure Key Vault

**Key Derivation**: PBKDF2 with 100,000 iterations provides:
- ~100ms computation time (slow enough to resist brute force)
- Unique per-file keys (salt-based derivation)

**Authentication**: GCM mode provides:
- Encryption (confidentiality)
- Authentication (integrity)
- Cannot be modified without detection

### Compliance

| Standard | Requirement | Compliance |
|----------|------------|------------|
| PCI DSS | Encrypt sensitive data at rest | ✅ AES-256 |
| HIPAA | Encryption of ePHI | ✅ NIST-approved |
| GDPR | Appropriate security measures | ✅ Industry standard |
| SOC 2 | Encryption controls | ✅ Authenticated encryption |

---

## Support

For questions or issues:

1. Check this documentation
2. Review audit logs: `/var/log/aunoo-env-access.log`
3. Check service logs: `sudo journalctl -xeu <service>`
4. See implementation summary: `/home/orochford/ENCRYPTION_IMPLEMENTATION_SUMMARY.md`
5. See full plan: `/home/orochford/tenants/staging.aunoo.ai/spec-files-aunoo/plans/ENV_SECURITY.md`

---

**Last Updated**: 2025-10-06
**Version**: 1.1.0
**Authors**: AunooAI Team
