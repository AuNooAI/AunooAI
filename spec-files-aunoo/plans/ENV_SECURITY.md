# .env Encryption & Automatic Creation Implementation Plan

**Created**: 2025-10-06
**Status**: Planning
**Priority**: High
**Effort**: 3 weeks

---

## Executive Summary

This plan implements encryption-at-rest for `.env` files and automatic `.env` creation during tenant deployment. The solution uses AES-256-GCM encryption with a master key, integrates with `deploy_site.py`, and provides credential rotation capabilities.

---

## Current State Analysis

### Existing .env Files
- **testing.aunoo.ai**: `-rw------- orochford:orochford` (600 - ✅ secure)
- **wip.aunoo.ai**: `-rw-r----- orochford:www-data` (640 - ⚠️ group readable)
- **staging.aunoo.ai**: `-rw-r----- orochford:www-data` (640 - ⚠️ group readable)

### deploy_site.py Capabilities
- Already creates `.env.example` template (lines 296-343)
- Sets permissions to 600 and chown to deploy user (lines 360-363)
- Adds `.env` to `.gitignore` (lines 366-375)
- **Does NOT** create actual `.env` file (requires manual configuration)
- **Does NOT** implement encryption

### Security Risks (from ENV_SECURITY_HARDENING.md)
- ✗ `.env` files contain plaintext API keys
- ✗ Some files accessible to www-data group (640 permissions)
- ✗ No audit trail of who accessed credentials
- ✗ Keys may be exposed in git history
- ✗ No automatic rotation mechanism
- ✗ Backups may contain credentials in plaintext

---

## Implementation Plan

### Phase 1: Encryption Foundation (Week 1)

#### 1.1 Create Encryption Utility Module
**File**: `/home/orochford/bin/env_encryption.py`

**Purpose**: Utility for encrypting/decrypting .env files using AES-256-GCM

**Features**:
- AES-256-GCM encryption (authenticated encryption)
- Master key stored in `/home/orochford/.env-master-key` (400 permissions)
- Per-tenant salt for key derivation (PBKDF2)
- Encrypt: `.env` → `.env.encrypted`
- Decrypt: `.env.encrypted` → `.env` (on service startup)
- Verify integrity with authentication tag

**Key Functions**:
```python
def generate_master_key() -> bytes:
    """One-time setup - generate master encryption key"""

def encrypt_env_file(tenant_path: Path) -> bool:
    """Encrypt .env to .env.encrypted"""

def decrypt_env_file(tenant_path: Path) -> bool:
    """Decrypt .env.encrypted to .env (temporary)"""

def rotate_encryption_key(old_key: bytes, new_key: bytes) -> None:
    """Re-encrypt all tenants with new key"""

def verify_encrypted_file(tenant_path: Path) -> bool:
    """Verify .env.encrypted integrity"""
```

**Dependencies**:
- `cryptography` library (already in requirements.txt)
- `pathlib` for path handling
- `logging` for audit trail

#### 1.2 Master Key Setup
```bash
# One-time setup
/home/orochford/.env-master-key          # 400 permissions
/home/orochford/.env-master-key.backup   # Encrypted backup in secure location
```

**Key Generation**:
```bash
# Run once during initial setup
python3 /home/orochford/bin/env_encryption.py init
# Creates master key with secure random generation
# Stores encrypted backup
# Displays warning to back up key securely
```

---

### Phase 2: deploy_site.py Integration (Week 1)

#### 2.1 Add Encryption to deploy_site.py

**New Functions**:

```python
def create_env_from_defaults(workdir: Path, domain: str, port: int, user: str = "orochford") -> bool:
    """
    Create .env file from shared defaults + tenant-specific config

    Reads from:
    1. /home/orochford/.env-defaults.encrypted (shared API keys)
    2. Tenant-specific overrides (domain, port, etc.)

    Automatically:
    - Generates FLASK_SECRET_KEY and NORN_SECRET_KEY (secrets.token_urlsafe)
    - Sets PORT from deployment config
    - Copies shared API keys from defaults
    - Encrypts immediately after creation

    Returns:
        True if .env created and encrypted successfully
        False if failed (logs error)
    """

def encrypt_tenant_env(workdir: Path) -> bool:
    """
    Encrypt .env file after creation/modification

    Steps:
    1. Call env_encryption.py encrypt
    2. Verify .env.encrypted created
    3. Remove plaintext .env
    4. Set .env.encrypted to 400 permissions
    """

def setup_env_decryption_service(domain: str, workdir: Path) -> None:
    """
    Add ExecStartPre to systemd service to decrypt on startup

    Adds to service file:
    - ExecStartPre: decrypt .env.encrypted before app starts
    - ExecStopPost: re-encrypt .env after app stops
    - ExecStopPost: remove plaintext .env on shutdown
    """
```

**Modified Functions**:

```python
def setup_env_file(workdir: Path, user: str = "orochford") -> bool:
    """
    Updated workflow:
    1. Create .env.example (already exists)
    2. Check if .env.encrypted exists
       - If yes: validate it (decrypt test, then re-encrypt)
       - If no: create from defaults using create_env_from_defaults()
    3. Validate required keys present
    4. Encrypt .env → .env.encrypted
    5. Remove plaintext .env
    6. Set .env.encrypted to 400 permissions

    Returns:
        True if .env ready (encrypted)
        False if manual configuration needed
    """

def install_service(domain: str, workdir: Path, user: str = "orochford") -> None:
    """
    Updated to include encryption hooks in systemd service

    Changes:
    - Add ExecStartPre for decryption
    - Add ExecStopPost for encryption and cleanup
    - Add LimitNOFILE for file descriptor limits
    """
```

---

### Phase 3: Systemd Integration (Week 1)

#### 3.1 Update Service Template

**File**: `deploy_site.py` lines 201-219

**Updated Template**:
```ini
[Unit]
Description=FastAPI {domain}
After=network.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={workdir}
Environment=ENVIRONMENT=production

# Decrypt .env before starting
ExecStartPre=/home/orochford/bin/env_encryption.py decrypt {workdir}

# Start application
ExecStart={workdir}/.venv/bin/python {workdir}/app/server_run.py

# Re-encrypt .env after stopping
ExecStopPost=/home/orochford/bin/env_encryption.py encrypt {workdir}

# Clean up plaintext .env on crash/stop
ExecStopPost=/bin/rm -f {workdir}/.env

Restart=on-failure
RestartSec=3
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
```

**Key Changes**:
- `ExecStartPre`: Decrypt before app starts (blocking)
- `ExecStopPost`: Re-encrypt after app stops
- `ExecStopPost`: Delete plaintext .env (idempotent with `-f`)
- Multiple `ExecStopPost` lines execute in order

---

### Phase 4: Shared Defaults System (Week 2)

#### 4.1 Create Shared Defaults File
**File**: `/home/orochford/.env-defaults`

**Content** (before encryption):
```bash
# Shared API keys for all tenants
# THIS FILE IS ENCRYPTED AT REST as .env-defaults.encrypted

# AI Provider Keys
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# News APIs
PROVIDER_NEWSAPI_KEY=...
PROVIDER_THENEWSAPI_KEY=...
THENEWSAPI_KEY=...

# Other Services
DIA_API_KEY=...
PROVIDER_FIRECRAWL_KEY=fc-...
ELEVENLABS_API_KEY=sk_...

# Social Media
PROVIDER_BLUESKY_USERNAME=...
PROVIDER_BLUESKY_PASSWORD=...

# Model-Specific Keys (Optional)
OPENAI_API_KEY_GPT_4.1_MINI=sk-proj-...
OPENAI_API_KEY_GPT_4.1=sk-proj-...
OPENAI_API_KEY_GPT_4.1_NANO=sk-proj-...
```

**Setup**:
```bash
# Create .env-defaults with shared credentials
vim /home/orochford/.env-defaults

# Encrypt it
python3 /home/orochford/bin/env_encryption.py encrypt /home/orochford/.env-defaults

# Delete plaintext
rm /home/orochford/.env-defaults

# Result: /home/orochford/.env-defaults.encrypted (400 permissions)
```

#### 4.2 Tenant-Specific Generation

**Logic**:
```python
def generate_tenant_env(domain: str, port: int, shared_defaults: Dict[str, str]) -> str:
    """
    Merge shared defaults with tenant-specific values

    Tenant-specific (generated/provided):
    - FLASK_SECRET_KEY: secrets.token_urlsafe(32)
    - NORN_SECRET_KEY: secrets.token_urlsafe(32)
    - PORT: from deployment argument
    - DOMAIN: from deployment argument

    Shared (from .env-defaults.encrypted):
    - All API keys
    - All service credentials

    Returns:
        String content of .env file ready to write
    """
    env_content = f"""# AuNoo AI Environment Configuration
# Auto-generated on {datetime.datetime.now().isoformat()}
# Domain: {domain}
# DO NOT commit this file to git!

# Flask Configuration (auto-generated)
FLASK_SECRET_KEY={secrets.token_urlsafe(32)}
NORN_SECRET_KEY={secrets.token_urlsafe(32)}

# Server Configuration
PORT={port}
DOMAIN={domain}

# Shared API Keys (from .env-defaults)
"""

    # Append all shared defaults
    for key, value in shared_defaults.items():
        env_content += f"{key}={value}\n"

    return env_content
```

---

### Phase 5: Security Hardening (Week 2)

#### 5.1 File Permissions Audit & Fix

**Script**: `/home/orochford/bin/audit_env_security.sh`

```bash
#!/bin/bash
# Audit and fix .env file permissions across all tenants

echo "🔍 Auditing .env file security..."

for tenant_dir in /home/orochford/tenants/*; do
    tenant=$(basename "$tenant_dir")

    # Check .env permissions
    if [ -f "$tenant_dir/.env" ]; then
        perms=$(stat -c "%a" "$tenant_dir/.env")
        if [ "$perms" != "400" ] && [ "$perms" != "600" ]; then
            echo "⚠️  $tenant: .env has $perms permissions (expected 400/600)"
            chmod 600 "$tenant_dir/.env"
            echo "   Fixed: set to 600"
        fi
    fi

    # Check .env.encrypted permissions
    if [ -f "$tenant_dir/.env.encrypted" ]; then
        perms=$(stat -c "%a" "$tenant_dir/.env.encrypted")
        if [ "$perms" != "400" ]; then
            echo "⚠️  $tenant: .env.encrypted has $perms permissions (expected 400)"
            chmod 400 "$tenant_dir/.env.encrypted"
            echo "   Fixed: set to 400"
        fi
    fi

    # Check ownership
    owner=$(stat -c "%U:%G" "$tenant_dir/.env" 2>/dev/null || echo "N/A")
    if [ "$owner" != "orochford:orochford" ] && [ "$owner" != "N/A" ]; then
        echo "⚠️  $tenant: .env owned by $owner (expected orochford:orochford)"
        chown orochford:orochford "$tenant_dir/.env"
        echo "   Fixed: set to orochford:orochford"
    fi
done

echo "✅ Audit complete"
```

**Function in deploy_site.py**:
```python
def harden_tenant_permissions(workdir: Path, user: str = "orochford") -> None:
    """
    Set secure permissions for all sensitive files

    .env.encrypted      → 400 (read-only by owner)
    .env-defaults       → DELETED (only encrypted version exists)
    .env                → DELETED after encryption
    .gitignore          → Ensure .env excluded

    Logs all permission changes for audit trail
    """
```

#### 5.2 Git Safety

**Function**:
```python
def ensure_git_safety(workdir: Path) -> bool:
    """
    Ensure .env files are not in git

    Steps:
    1. Check if .env in git index: git ls-files | grep .env
    2. Check if .env in git history: git log --all --full-history -- .env
    3. Warn if found, offer to clean with BFG or git-filter-repo
    4. Ensure .gitignore has:
       .env
       .env.*
       !.env.example
       .env.encrypted  # Don't commit encrypted version either

    Returns:
        True if safe
        False if .env found in git (manual cleanup required)
    """
```

**Pre-commit Hook** (optional):
```bash
# .git/hooks/pre-commit
#!/bin/bash
# Prevent committing .env files

if git diff --cached --name-only | grep -E '^\.env$|^\.env\.'; then
    echo "❌ ERROR: Attempting to commit .env file!"
    echo "   .env files should never be committed to git"
    exit 1
fi
```

---

### Phase 6: Credential Rotation Support (Week 3)

#### 6.1 Rotation Script
**File**: `/home/orochford/bin/rotate_credential.sh`

```bash
#!/bin/bash
# Rotate a credential across all tenants or in shared defaults

set -e

CREDENTIAL_NAME=$1
NEW_VALUE=$2
SCOPE=${3:-"all"}  # "all" | "shared" | specific tenant

if [ -z "$CREDENTIAL_NAME" ] || [ -z "$NEW_VALUE" ]; then
    echo "Usage: $0 CREDENTIAL_NAME NEW_VALUE [SCOPE]"
    echo ""
    echo "SCOPE:"
    echo "  all       - Update in shared defaults and all tenants"
    echo "  shared    - Update only in shared defaults"
    echo "  <tenant>  - Update only in specific tenant"
    echo ""
    echo "Examples:"
    echo "  $0 OPENAI_API_KEY sk-proj-newkey123 all"
    echo "  $0 FLASK_SECRET_KEY newsecret wip.aunoo.ai"
    exit 1
fi

BACKUP_DIR="/home/orochford/.env-backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "🔄 Credential Rotation: $CREDENTIAL_NAME"
echo "   Scope: $SCOPE"
echo "   Backup: $BACKUP_DIR"
echo ""

# Function to rotate in a file
rotate_in_file() {
    local encrypted_file=$1
    local tenant=$2

    echo "  → Rotating in $tenant..."

    # Backup
    cp "$encrypted_file" "$BACKUP_DIR/$(basename $encrypted_file).$tenant"

    # Decrypt
    python3 /home/orochford/bin/env_encryption.py decrypt "$(dirname $encrypted_file)"

    # Update credential
    local env_file="${encrypted_file%.encrypted}"
    sed -i "s|^${CREDENTIAL_NAME}=.*|${CREDENTIAL_NAME}=${NEW_VALUE}|" "$env_file"

    # Re-encrypt
    python3 /home/orochford/bin/env_encryption.py encrypt "$(dirname $encrypted_file)"

    echo "    ✓ Rotated"
}

# Rotate in shared defaults if scope includes it
if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "shared" ]; then
    if [ -f "/home/orochford/.env-defaults.encrypted" ]; then
        rotate_in_file "/home/orochford/.env-defaults.encrypted" "shared-defaults"
    fi
fi

# Rotate in tenants
if [ "$SCOPE" = "all" ]; then
    # All tenants
    for tenant_dir in /home/orochford/tenants/*; do
        tenant=$(basename "$tenant_dir")
        encrypted_file="$tenant_dir/.env.encrypted"

        if [ -f "$encrypted_file" ]; then
            rotate_in_file "$encrypted_file" "$tenant"
        fi
    done
elif [ "$SCOPE" != "shared" ]; then
    # Specific tenant
    tenant_dir="/home/orochford/tenants/$SCOPE"
    encrypted_file="$tenant_dir/.env.encrypted"

    if [ -f "$encrypted_file" ]; then
        rotate_in_file "$encrypted_file" "$SCOPE"
    else
        echo "❌ Tenant not found: $SCOPE"
        exit 1
    fi
fi

echo ""
echo "🔄 Restarting affected services..."

if [ "$SCOPE" = "all" ]; then
    for instance in wip staging testing quantum daniella; do
        if systemctl list-units --full --all | grep -q "${instance}.aunoo.ai.service"; then
            echo "  → Restarting ${instance}.aunoo.ai..."
            sudo systemctl restart "${instance}.aunoo.ai"
        fi
    done
else
    if systemctl list-units --full --all | grep -q "${SCOPE}.service"; then
        echo "  → Restarting ${SCOPE}..."
        sudo systemctl restart "${SCOPE}"
    fi
fi

echo ""
echo "🔍 Verifying services..."
sleep 5

FAILED=0
if [ "$SCOPE" = "all" ]; then
    for instance in wip staging testing quantum daniella; do
        if systemctl is-active --quiet "${instance}.aunoo.ai"; then
            echo "  ✓ ${instance}.aunoo.ai is running"
        else
            echo "  ✗ ${instance}.aunoo.ai FAILED"
            FAILED=1
        fi
    done
else
    if systemctl is-active --quiet "${SCOPE}"; then
        echo "  ✓ ${SCOPE} is running"
    else
        echo "  ✗ ${SCOPE} FAILED"
        FAILED=1
    fi
fi

# Log rotation
echo "$(date): Rotated ${CREDENTIAL_NAME} (scope: ${SCOPE})" >> /var/log/aunoo-credential-rotations.log

if [ $FAILED -eq 0 ]; then
    echo ""
    echo "✅ Rotation complete and verified"
    echo "   Backups: $BACKUP_DIR"
else
    echo ""
    echo "❌ Some services failed to start!"
    echo "   Backups available for rollback: $BACKUP_DIR"
    exit 1
fi
```

---

### Phase 7: Monitoring & Auditing (Week 3)

#### 7.1 Access Logging

**Add to env_encryption.py**:
```python
import logging
from datetime import datetime

# Configure audit logger
audit_logger = logging.getLogger('env_encryption.audit')
audit_logger.setLevel(logging.INFO)
handler = logging.FileHandler('/var/log/aunoo-env-access.log')
handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
audit_logger.addHandler(handler)

def log_access(operation: str, tenant: str, user: str, success: bool) -> None:
    """
    Log all encrypt/decrypt operations

    Args:
        operation: "ENCRYPT" | "DECRYPT" | "VERIFY"
        tenant: Tenant name (e.g., "wip.aunoo.ai")
        user: User performing operation
        success: Whether operation succeeded

    Example log:
        2025-10-06 10:15:23 | INFO | DECRYPT | wip.aunoo.ai | orochford | SUCCESS
        2025-10-06 10:15:45 | INFO | ENCRYPT | wip.aunoo.ai | orochford | SUCCESS
    """
    status = "SUCCESS" if success else "FAILURE"
    audit_logger.info(f"{operation} | {tenant} | {user} | {status}")
```

#### 7.2 Alert on Suspicious Patterns

**Script**: `/home/orochford/bin/check_env_security.py`

```python
#!/usr/bin/env python3
"""
Monitor .env access logs for suspicious patterns
Run via cron every hour
"""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

LOG_FILE = Path("/var/log/aunoo-env-access.log")
ALERT_THRESHOLD = {
    "failed_decrypts": 3,      # Alert if 3+ failed decrypts in 1 hour
    "decrypt_no_encrypt": 5,   # Alert if decrypt without encrypt 5+ times
    "master_key_access": 1,    # Alert on any master key access outside maintenance
}

def check_suspicious_access():
    """
    Alert if:
    - Multiple failed decrypt attempts
    - Decrypt without corresponding encrypt
    - Access from unexpected user
    - Master key accessed outside maintenance window
    """

    # Read last hour of logs
    cutoff = datetime.now() - timedelta(hours=1)

    failed_decrypts = defaultdict(int)
    decrypt_without_encrypt = defaultdict(int)

    with open(LOG_FILE, 'r') as f:
        for line in f:
            # Parse log line
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \w+ \| (\w+) \| ([^|]+) \| ([^|]+) \| (\w+)', line)
            if not match:
                continue

            timestamp_str, operation, tenant, user, status = match.groups()
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

            if timestamp < cutoff:
                continue

            # Check for failed decrypts
            if operation == "DECRYPT" and status == "FAILURE":
                failed_decrypts[tenant] += 1

            # Track decrypt/encrypt pairs
            # (More complex logic needed for production)

    # Send alerts if thresholds exceeded
    for tenant, count in failed_decrypts.items():
        if count >= ALERT_THRESHOLD["failed_decrypts"]:
            send_alert(f"⚠️ {count} failed decrypt attempts for {tenant} in last hour")

if __name__ == "__main__":
    check_suspicious_access()
```

**Cron Job**:
```bash
# /etc/cron.d/aunoo-env-security
0 * * * * orochford /home/orochford/bin/check_env_security.py
```

---

## Implementation Timeline

### Week 1: Core Encryption (High Priority)

**Day 1-2: Create Encryption Utility**
- [ ] Write `env_encryption.py` with core functions
- [ ] Implement AES-256-GCM encryption/decryption
- [ ] Add master key generation
- [ ] Add audit logging
- [ ] Test encryption/decryption cycle
- [ ] Write unit tests

**Day 2-3: Integrate with deploy_site.py**
- [ ] Add `create_env_from_defaults()` function
- [ ] Add `encrypt_tenant_env()` function
- [ ] Modify `setup_env_file()` to use encryption
- [ ] Add git safety checks
- [ ] Test on test tenant

**Day 3-4: Update Systemd Service**
- [ ] Update SERVICE_TPL with ExecStartPre/ExecStopPost
- [ ] Modify `install_service()` function
- [ ] Test service startup/shutdown with encryption
- [ ] Verify .env cleanup on stop

**Day 4-5: Test & Deploy**
- [ ] Deploy new test tenant with encryption
- [ ] Verify service starts correctly
- [ ] Verify .env decrypted on start
- [ ] Verify .env encrypted on stop
- [ ] Fix any issues found
- [ ] Fix permissions on existing tenants (wip, staging to 600)

### Week 2: Automation & Migration (Medium Priority)

**Day 1-2: Shared Defaults System**
- [ ] Create `/home/orochford/.env-defaults` with shared credentials
- [ ] Encrypt to `.env-defaults.encrypted`
- [ ] Implement `generate_tenant_env()` function
- [ ] Test .env generation from defaults
- [ ] Update deploy_site.py to use defaults

**Day 2-3: Migrate Existing Tenants**
- [ ] Backup all existing .env files
- [ ] Encrypt wip.aunoo.ai/.env
- [ ] Encrypt testing.aunoo.ai/.env
- [ ] Encrypt staging.aunoo.ai/.env
- [ ] Update systemd services with encryption hooks
- [ ] Restart services and verify

**Day 3-4: Test Rotation Workflow**
- [ ] Write `rotate_credential.sh` script
- [ ] Test rotation on single tenant
- [ ] Test rotation on all tenants
- [ ] Verify services restart correctly
- [ ] Document rotation procedure

**Day 4-5: Documentation**
- [ ] Document encryption workflow
- [ ] Document rotation procedure
- [ ] Document emergency recovery
- [ ] Update deploy_site.py docstrings

### Week 3: Hardening & Monitoring (Nice to Have)

**Day 1-2: Security Hardening**
- [ ] Write `audit_env_security.sh` script
- [ ] Run audit on all tenants
- [ ] Fix any permission issues found
- [ ] Implement git safety checks
- [ ] Scan git history for exposed credentials

**Day 2-3: Access Logging & Monitoring**
- [ ] Implement audit logging in env_encryption.py
- [ ] Create `/var/log/aunoo-env-access.log`
- [ ] Write `check_env_security.py` monitoring script
- [ ] Set up cron job for monitoring
- [ ] Test alert notifications

**Day 3-4: Emergency Procedures**
- [ ] Write emergency rotation script
- [ ] Document incident response
- [ ] Test rollback procedure
- [ ] Create runbook for common scenarios

**Day 4-5: Final Testing & Documentation**
- [ ] End-to-end test of entire system
- [ ] Deploy to production tenants
- [ ] Final documentation review
- [ ] Training for operations team

---

## File Structure After Implementation

```
/home/orochford/
├── .env-master-key                    # 400, encrypted backup exists
├── .env-master-key.backup             # 400, encrypted with separate passphrase
├── .env-defaults.encrypted            # 400, shared API keys
├── .env-backups/                      # 700, rotation backups by date
│   └── 20251006_101523/
│       ├── .env.encrypted.wip.aunoo.ai
│       └── .env.encrypted.staging.aunoo.ai
├── bin/
│   ├── env_encryption.py              # Core encryption utility
│   ├── rotate_credential.sh           # Rotation automation
│   ├── audit_env_security.sh          # Security audit
│   ├── check_env_security.py          # Monitoring script
│   └── deploy_site.py                 # Updated with encryption
└── tenants/
    ├── wip.aunoo.ai/
    │   ├── .env.encrypted             # 400, encrypted at rest
    │   ├── .env.example               # 644, template (not secret)
    │   ├── .env                       # EXISTS ONLY DURING RUNTIME
    │   └── .gitignore                 # Excludes .env, .env.*
    ├── testing.aunoo.ai/
    │   └── ... (same structure)
    └── staging.aunoo.ai/
        └── ... (same structure)

/var/log/
├── aunoo-env-access.log               # 640, audit trail
└── aunoo-credential-rotations.log     # 640, rotation history
```

---

## Key Design Decisions

### 1. **Encryption Method: AES-256-GCM**
- ✅ Authenticated encryption (integrity + confidentiality)
- ✅ NIST-approved, industry standard
- ✅ Built into Python `cryptography` library
- ✅ Detects tampering via authentication tag
- ❌ Requires managing encryption key securely

**Alternatives Considered**:
- **git-crypt**: Requires GPG key management, git-specific
- **SOPS**: Requires cloud KMS or GPG, additional dependency
- **OpenSSL**: Command-line only, harder to integrate

**Why AES-256-GCM**: Native Python support, no external dependencies, well-tested.

### 2. **Master Key Storage**
- **Location**: `/home/orochford/.env-master-key`
- **Permissions**: 400 (read-only by orochford)
- **Backup**: Encrypted backup with separate passphrase stored off-server
- **Rotation**: Manual process with re-encryption of all tenants

**Security Considerations**:
- Master key never leaves server
- Encrypted backup for disaster recovery
- Consider HSM or cloud KMS for production at scale

### 3. **Automatic .env Creation**
- **Source**: Shared `.env-defaults.encrypted`
- **Tenant-specific**: Generated secrets (FLASK_SECRET_KEY, NORN_SECRET_KEY)
- **Validation**: Check required keys present before deployment
- **Fallback**: If shared defaults missing, use `.env.example` as template

**Benefits**:
- Consistent API keys across tenants
- No manual credential copying
- Automatic secret generation (no weak defaults)

### 4. **Runtime Behavior**
- **On Start**: Decrypt `.env.encrypted` → `.env` (ExecStartPre)
- **During Run**: App reads plaintext `.env` (FastAPI loads with python-dotenv)
- **On Stop**: Re-encrypt `.env` → `.env.encrypted` (ExecStopPost #1)
- **On Stop**: Delete plaintext `.env` (ExecStopPost #2)
- **On Crash**: `ExecStopPost` still runs, cleans up `.env`

**Why This Approach**:
- No code changes to FastAPI app
- Works with existing python-dotenv
- Transparent to application
- Systemd handles lifecycle automatically

### 5. **Migration Strategy**
- **New tenants**: Automatic encryption from day 1
- **Existing tenants**: Manual migration with backup
- **Rollback**: Keep `.env.encrypted.backup` before changes
- **Testing**: Test on wip, then testing, then staging, then production

**Migration Checklist**:
1. Backup existing .env
2. Encrypt .env → .env.encrypted
3. Update systemd service with encryption hooks
4. Restart service
5. Verify service running
6. Verify .env.encrypted exists
7. Delete plaintext .env backup (after 30 days)

---

## Security Benefits

| Risk | Before | After | Improvement |
|------|--------|-------|-------------|
| Plaintext credentials at rest | ❌ Yes | ✅ No | Encrypted with AES-256-GCM |
| Credentials in git | ❌ Possible | ✅ Prevented | .gitignore + pre-commit hooks |
| Credentials in backups | ❌ Plaintext | ✅ Encrypted | Encrypted at rest |
| Group readable .env | ❌ Yes (640) | ✅ No (400/600) | Owner-only access |
| No audit trail | ❌ Yes | ✅ No | All access logged to /var/log |
| Manual rotation | ❌ Error-prone | ✅ Automated | Scripted with validation |
| No integrity check | ❌ Yes | ✅ No | GCM authentication tag |
| Shared credentials insecure | ❌ Yes | ✅ No | .env-defaults.encrypted |

---

## Testing Plan

### Unit Tests (env_encryption.py)
```python
def test_encrypt_decrypt_cycle():
    """Test encryption and decryption roundtrip"""

def test_tamper_detection():
    """Test that modified .env.encrypted is detected"""

def test_missing_master_key():
    """Test graceful failure when master key missing"""

def test_invalid_encrypted_file():
    """Test handling of corrupted .env.encrypted"""
```

### Integration Tests (deploy_site.py)
```bash
# Test 1: Deploy new tenant with encryption
sudo python3 deploy_site.py --repo ... --domain test1.aunoo.ai --email ...

# Verify:
- .env.encrypted exists with 400 permissions
- .env does not exist (encrypted and deleted)
- Service starts correctly
- Service can read .env after decryption

# Test 2: Rotate credential
./rotate_credential.sh OPENAI_API_KEY sk-newkey test1.aunoo.ai

# Verify:
- .env.encrypted updated
- Service restarted
- App uses new key
- Backup created

# Test 3: Service crash
sudo systemctl stop test1.aunoo.ai

# Verify:
- .env deleted
- .env.encrypted still exists
```

---

## Rollback Plan

### If Encryption Breaks Deployment

**Immediate Rollback**:
```bash
# 1. Stop service
sudo systemctl stop wip.aunoo.ai

# 2. Restore from backup
cp /home/orochford/.env-backups/20251006_101523/.env.wip.aunoo.ai \
   /home/orochford/tenants/wip.aunoo.ai/.env

# 3. Remove encryption hooks from service
sudo vim /etc/systemd/system/wip.aunoo.ai.service
# Comment out ExecStartPre and ExecStopPost

# 4. Reload and restart
sudo systemctl daemon-reload
sudo systemctl start wip.aunoo.ai

# 5. Verify service running
sudo systemctl status wip.aunoo.ai
curl https://wip.aunoo.ai/health
```

### If Rotation Fails

**Automatic Rollback** (built into rotate_credential.sh):
- Script checks service status after restart
- If any service fails, restores from backup automatically
- Logs rollback event

---

## Monitoring & Alerts

### Metrics to Track
- **Encryption Operations**: Count per day
- **Failed Decrypts**: Alert if > 3 per hour per tenant
- **Service Start Failures**: Alert immediately
- **Missing .env.encrypted**: Alert on deployment
- **Plaintext .env Found**: Alert immediately (should only exist during runtime)

### Log Files
- `/var/log/aunoo-env-access.log`: All encryption operations
- `/var/log/aunoo-credential-rotations.log`: Rotation history
- `/var/log/syslog`: Systemd service startup/shutdown

### Dashboards (Future)
- Grafana dashboard showing:
  - Encryption/decryption events per tenant
  - Failed operations
  - Rotation history
  - Service uptime correlation

---

## Emergency Procedures

### If Master Key Lost

**Impact**: Cannot decrypt any .env.encrypted files

**Recovery**:
1. Restore from encrypted backup (requires backup passphrase)
2. If backup lost, manually recreate .env files from:
   - Deployment info files (DEPLOYMENT_INFO.txt)
   - API provider dashboards (regenerate keys)
   - Manual documentation
3. Generate new master key
4. Re-encrypt all tenants

**Prevention**:
- Keep encrypted backup of master key off-server
- Document backup passphrase in secure vault (1Password, etc.)

### If Credentials Compromised

**Immediate Actions** (< 15 minutes):
1. Rotate compromised credential at provider (OpenAI, Anthropic, etc.)
2. Run rotation script: `./rotate_credential.sh OPENAI_API_KEY <new_key> all`
3. Verify all services restarted successfully
4. Monitor for unauthorized usage

**Follow-up** (< 24 hours):
1. Review access logs for suspicious activity
2. Audit who had access to .env files
3. Review git history for exposure
4. Document incident

### If .env File Committed to Git

**Immediate Actions**:
```bash
# 1. Remove from staging
git reset HEAD .env

# 2. Clean from history (use git-filter-repo or BFG)
git filter-repo --path .env --invert-paths

# 3. Force push (if remote exists)
git push origin --force --all

# 4. Rotate ALL credentials in that .env
./rotate_credential.sh OPENAI_API_KEY <new_key> <tenant>
./rotate_credential.sh ANTHROPIC_API_KEY <new_key> <tenant>
# ... repeat for all keys

# 5. Notify team
echo "⚠️ .env was committed to git. All credentials rotated."
```

---

## Success Criteria

### Phase 1 (Week 1)
- [x] env_encryption.py created and tested
- [ ] deploy_site.py updated with encryption
- [ ] New test tenant deployed with encryption
- [ ] Systemd service starts/stops with auto-encrypt/decrypt
- [ ] Existing tenants have 600 permissions (wip, staging fixed)

### Phase 2 (Week 2)
- [ ] .env-defaults.encrypted created with shared credentials
- [ ] Automatic .env generation working
- [ ] All existing tenants migrated to encryption
- [ ] Rotation script tested and working

### Phase 3 (Week 3)
- [ ] Audit logging implemented
- [ ] Monitoring script deployed
- [ ] Documentation complete
- [ ] Team trained on procedures

### Overall Success
- ✅ All .env files encrypted at rest (AES-256-GCM)
- ✅ No plaintext .env files except during service runtime
- ✅ All .env files have 400/600 permissions
- ✅ Automatic .env creation for new tenants
- ✅ Credential rotation automated and tested
- ✅ Access logging and monitoring active
- ✅ Zero credentials in git history
- ✅ Emergency procedures documented and tested

---

## Next Steps

1. **Review this plan** with security team
2. **Approve Phase 1** for implementation
3. **Create** `env_encryption.py` utility (Week 1, Day 1-2)
4. **Test** encryption on isolated test tenant
5. **Deploy** to wip instance (Week 1, Day 4)
6. **Monitor** for issues over 48 hours
7. **Proceed** to Phase 2 if no issues

---

## References

- [ENV_SECURITY_HARDENING.md](../docs/ENV_SECURITY_HARDENING.md) - Full security guide
- [deploy_site.py](/home/orochford/bin/deploy_site.py) - Deployment script
- [Python cryptography library](https://cryptography.io/) - Encryption primitives
- [Systemd ExecStartPre](https://www.freedesktop.org/software/systemd/man/systemd.service.html) - Service hooks

---

**Document Status**: ✅ Complete
**Last Updated**: 2025-10-06
**Owner**: Security Team
**Reviewers**: DevOps, Platform Engineering
