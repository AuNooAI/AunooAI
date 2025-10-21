# OAuth Users - How It Works

**Date**: 2025-10-21 12:19
**Status**: ✅ FIXED

---

## What is an OAuth User?

**OAuth User** = A user who authenticates via a third-party provider (Google, GitHub, Microsoft, etc.) instead of using a username/password.

### Regular User vs OAuth User

| Aspect | Regular User | OAuth User |
|--------|-------------|------------|
| **Authentication** | Username + Password | Third-party provider (Google, etc.) |
| **Password** | Has password_hash in database | No password_hash (null) |
| **Badge in UI** | Shows "Admin" or "User" only | Shows "Admin/User" + "OAuth" badge |
| **Created via** | Create User form (admin) | OAuth login flow |
| **Password change** | Can change password | Cannot change password (uses provider) |

---

## How the OAuth Badge Works

### Backend Logic (FIXED)

**File**: `app/routes/user_management_routes.py` (lines 79-85)

```python
# Mark OAuth users (check BEFORE removing password hash)
for user in users:
    # OAuth users don't have password_hash (authenticate via third-party providers)
    has_password = bool(user.get('password_hash'))
    user['is_oauth'] = not has_password  # True if no password
    # Remove password hash for security (don't send to frontend)
    user.pop('password_hash', None)
```

**Logic**:
1. Check if user has a `password_hash` in the database
2. If **password_hash exists** → Regular user → `is_oauth = False`
3. If **password_hash is NULL** → OAuth user → `is_oauth = True`
4. Remove password_hash before sending to frontend (security)

### Frontend Display

**File**: `templates/config.html` (lines 3254-3255, 3275)

```javascript
const oauthBadge = user.is_oauth ?
    ' <span class="badge bg-info">OAuth</span>' : '';

// In the table:
<td>${roleBadge}${oauthBadge}</td>
```

**Display**:
- Regular admin: `[Admin]`
- OAuth admin: `[Admin] [OAuth]`
- Regular user: `[User]`
- OAuth user: `[User] [OAuth]`

---

## Bug That Was Fixed

### The Problem

**Before** (lines 80-82):
```python
for user in users:
    user.pop('password_hash', None)           # ❌ Remove first
    user['is_oauth'] = (not user.get('password_hash'))  # ❌ Then check (always None!)
```

**Result**: ALL users were marked as OAuth because `password_hash` was removed before checking!

### The Fix

**After** (lines 80-85):
```python
for user in users:
    has_password = bool(user.get('password_hash'))  # ✅ Check first
    user['is_oauth'] = not has_password              # ✅ Then mark
    user.pop('password_hash', None)                  # ✅ Then remove
```

**Result**: Only users WITHOUT passwords are marked as OAuth

---

## OAuth User System Architecture

The application has TWO user systems:

### 1. Main Users Table (`users`)
```sql
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    password_hash TEXT,           -- NULL for OAuth users
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,
    is_active BOOLEAN,
    force_password_change BOOLEAN,
    completed_onboarding BOOLEAN,
    created_at TIMESTAMP
);
```

**Contains**:
- Regular users (created via Create User form)
- OAuth users (migrated or created via OAuth flow)

**Identification**: OAuth users have `password_hash = NULL`

### 2. OAuth Users Table (`oauth_users`)
```sql
CREATE TABLE oauth_users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    name TEXT,
    provider TEXT NOT NULL,        -- 'google', 'github', etc.
    provider_id TEXT,              -- User ID from provider
    avatar_url TEXT,
    created_at TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN
);
```

**Contains**: OAuth provider-specific data

### 3. OAuth Allowlist Table (`oauth_allowlist`)
```sql
CREATE TABLE oauth_allowlist (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    added_by TEXT,
    added_at TIMESTAMP,
    is_active BOOLEAN
);
```

**Purpose**: Whitelist of emails allowed to use OAuth login

---

## Current State

**Database Check**:
```sql
SELECT username, email, role,
       CASE WHEN password_hash IS NULL THEN 'OAuth' ELSE 'Regular' END as type
FROM users;
```

**Current Users** (as of 2025-10-21):
```
username  | email                     | role  | type
----------|---------------------------|-------|--------
admin     | admin@localhost           | admin | Regular
orochford | oliver.rochford@gmail.com | user  | Regular
oliver    | orochford@aunoo.ai        | user  | Regular
```

**Result**: No OAuth users currently exist (all have passwords)

---

## How OAuth Users Are Created

### Method 1: OAuth Login Flow (Not Implemented Yet?)
1. User clicks "Login with Google"
2. Google authenticates user
3. App checks `oauth_allowlist` for user's email
4. If allowed, creates user in `users` table with `password_hash = NULL`
5. Also creates record in `oauth_users` table with provider info

### Method 2: Migration (Already Done)
The migration script (`simple_multiuser_corrected.py`) tried to:
1. Find OAuth users in `oauth_allowlist`
2. Create them in `users` table without password_hash
3. Set role based on email

**However**: This migration only added users if they existed in oauth_allowlist, which was empty.

---

## How to Create an OAuth User Manually

If you want to test the OAuth badge:

```sql
-- Create an OAuth user without password
INSERT INTO users (
    username,
    email,
    password_hash,  -- NULL!
    role,
    is_active,
    force_password_change,
    completed_onboarding
) VALUES (
    'googleuser',
    'user@gmail.com',
    NULL,           -- No password = OAuth user
    'user',
    true,
    false,
    true
);
```

**Result**: This user will show the OAuth badge in the UI

---

## OAuth User Restrictions

### What OAuth Users CANNOT Do:
- ❌ Change password (they don't have one!)
- ❌ Use the "Change Password" form
- ❌ Login with username/password

### What OAuth Users CAN Do:
- ✅ Login via OAuth provider
- ✅ Use all application features
- ✅ Be promoted to admin
- ✅ Be deactivated by admins

---

## UI Behavior for OAuth Users

### In User List
```
Username    Email              Role           Status  Actions
--------    -----              ----           ------  -------
admin       admin@localhost    [Admin]        Active  You
googleuser  user@gmail.com     [User] [OAuth] Active  [Delete]
```

### Password Change
If an OAuth user tries to access `/change_password`:
- Should show message: "You use OAuth to login and cannot change your password here"
- OR redirect them back to main app

---

## Testing OAuth Badge

### Current Behavior
**All users created via the Create User form** will be regular users (not OAuth) because:
1. The form requires a password
2. Password is hashed and stored
3. `password_hash` exists → Not OAuth

### To See OAuth Badge
You would need to:
1. Manually create a user with NULL password_hash (SQL)
2. OR implement OAuth login flow
3. OR have users migrated from oauth_allowlist

---

## Security Implications

### Why We Remove password_hash from API Response

**Before sending to frontend**:
```python
user.pop('password_hash', None)  # Remove password hash
```

**Reason**:
- Password hashes should NEVER be sent to the frontend
- Even though they're hashed, it's a security best practice
- Reduces attack surface if frontend is compromised

### OAuth User Security

**Advantages**:
- ✅ No password to leak
- ✅ Provider handles 2FA
- ✅ Centralized authentication

**Considerations**:
- ⚠️ Depends on provider security
- ⚠️ Requires OAuth allowlist management
- ⚠️ Can't login if provider is down

---

## Summary

**OAuth Badge Shows When**:
- User has `password_hash = NULL` in database
- User authenticates via third-party provider (Google, GitHub, etc.)

**Fixed Bug**:
- ✅ Was checking password_hash AFTER removing it
- ✅ Now checks BEFORE removing it
- ✅ OAuth badge will only show for actual OAuth users

**Current State**:
- No OAuth users exist (all have passwords)
- All users created via form are regular users
- OAuth badge will work correctly if/when OAuth users are added

---

**Status**: ✅ OAuth detection fixed and working correctly
**Testing**: Create a NULL password user to see badge

Last Updated: 2025-10-21 12:19
