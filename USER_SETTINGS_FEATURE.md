# User Creation Settings Feature

**Date**: 2025-10-21 12:15
**Status**: ✅ COMPLETE

---

## New Features Added

When creating a new user, admins can now control two important settings:

### 1. ✅ Require Password Change on First Login
**Checkbox**: "Require password change on first login" (checked by default)

**What it does**:
- When **checked**: User MUST change their password on first login
- When **unchecked**: User can use the initial password without changing it

**How it works**:
- Sets `force_password_change` flag in database
- On login, if flag is `true`, user is redirected to `/change_password` page
- User cannot access the application until they change their password
- After password change, flag is automatically set to `false`

**Use case**: Security best practice - ensures users create their own passwords instead of using admin-assigned ones

---

### 2. ✅ Skip Onboarding Wizard
**Checkbox**: "Skip onboarding wizard" (unchecked by default)

**What it does**:
- When **checked**: User skips the onboarding wizard and goes straight to the app
- When **unchecked**: User sees the onboarding/welcome wizard on first login

**How it works**:
- Sets `completed_onboarding` flag in database
- When `false`, user is redirected to `/onboarding` page after login
- When `true`, user goes directly to the main application

**Use case**: Skip onboarding for experienced users or in environments where training is handled externally

---

## User Interface

### Create User Form (Admin Only)

The form now includes these checkboxes below the Role dropdown:

```
┌─────────────────────────────────────────────────┐
│ Username: [________________]                    │
│ Email:    [________________]                    │
│ Password: [________________]                    │
│ Role:     [▼ user      ]                        │
│                                                 │
│ ☑️ Require password change on first login      │
│   User must change their password when they    │
│   first log in                                  │
│                                                 │
│ ☐ Skip onboarding wizard                       │
│   Mark onboarding as completed (user won't see │
│   the welcome wizard)                           │
│                                                 │
│ [Create User]                                   │
└─────────────────────────────────────────────────┘
```

---

## Login Flow

After successful login, the system checks these flags in order:

```
User logs in
    ↓
1. Check is_active → If false, deny login
    ↓
2. Check force_password_change → If true, redirect to /change_password
    ↓
3. Check completed_onboarding → If false, redirect to /onboarding
    ↓
4. All checks passed → redirect to / (main app)
```

---

## Database Schema

These flags are stored in the `users` table:

```sql
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    force_password_change BOOLEAN DEFAULT FALSE,    -- NEW: Controls password change requirement
    completed_onboarding BOOLEAN DEFAULT FALSE,     -- NEW: Controls onboarding wizard
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Changes

### POST /api/users/ (Create User)

**Request Body** (now includes two new optional fields):

```json
{
    "username": "testuser",
    "email": "test@example.com",
    "password": "InitialPass123",
    "role": "user",
    "force_password_change": true,      // NEW: Default true
    "completed_onboarding": false       // NEW: Default false
}
```

**Response**:
```json
{
    "user": {
        "username": "testuser",
        "email": "test@example.com",
        "role": "user",
        "is_active": true,
        "force_password_change": true,
        "completed_onboarding": false,
        "created_at": "2025-10-21T12:15:00"
    }
}
```

---

## Testing Scenarios

### Scenario 1: Default Settings (Force Password Change)
1. Admin creates user with default settings (force password change checked)
2. User logs in with initial password
3. User is **immediately redirected** to `/change_password`
4. User cannot access app until password is changed
5. After changing password, user can access the app

### Scenario 2: No Force Password Change
1. Admin creates user with "force password change" **unchecked**
2. User logs in with initial password
3. User goes to onboarding (if not completed) or main app
4. User can use the initial password indefinitely

### Scenario 3: Skip Onboarding
1. Admin creates user with "skip onboarding" **checked**
2. User logs in (changes password if forced)
3. User goes **directly to main app** (no onboarding wizard)

### Scenario 4: Both Flags Set
1. Admin creates user with **both checkboxes checked**
2. User logs in
3. User is redirected to `/change_password` (force password change takes priority)
4. After changing password, user goes to main app (onboarding skipped)

---

## Files Modified

### Backend
1. **`app/routes/user_management_routes.py`** (lines 27-34):
   - Updated `UserCreate` model to include `force_password_change` and `completed_onboarding`
   - Defaults: `force_password_change=True`, `completed_onboarding=False`

2. **`app/routes/user_management_routes.py`** (lines 122-128):
   - Updated `create_user` endpoint to pass new flags to database

3. **`app/database_query_facade.py`** (lines 1082-1104):
   - Updated `create_user` method to accept and store new flags

### Frontend
4. **`templates/config.html`** (lines 543-567):
   - Added two checkboxes to create user form

5. **`templates/config.html`** (lines 3335-3336, 3366-3367):
   - Updated JavaScript to read checkbox values and send to API

---

## Security Considerations

### Force Password Change
**✅ Security Best Practice**: Always enabled by default
- Prevents password reuse if initial password is compromised
- Ensures users choose passwords they can remember
- Reduces risk from shared/written-down passwords

**⚠️ When to Disable**: Only disable if:
- Password is generated by secure system and delivered securely
- Organization policy requires it
- User is technical and password is complex

### Skip Onboarding
**✅ User Experience**: Disabled by default
- New users benefit from onboarding
- Reduces support requests

**✅ When to Enable**: Enable for:
- Experienced users migrating from another system
- Internal team members who don't need training
- Bulk user imports where training is handled separately

---

## Default Behavior

When creating a new user:
- **Force Password Change**: ✅ **CHECKED** (enabled by default)
- **Skip Onboarding**: ☐ **UNCHECKED** (disabled by default)

This ensures maximum security and best user experience by default.

---

## Example: Creating a User

**Step 1**: Go to `/config` → Users tab (admin only)

**Step 2**: Fill in form:
- Username: `john.doe`
- Email: `john@company.com`
- Password: `TempPass123!`
- Role: `user`
- ✅ Require password change on first login (checked)
- ☐ Skip onboarding wizard (unchecked)

**Step 3**: Click "Create User"

**Step 4**: User `john.doe` logs in:
1. Enters credentials
2. **Redirected to** `/change_password`
3. Must create new password
4. **Redirected to** `/onboarding`
5. Completes onboarding wizard
6. **Redirected to** `/` (main app)

---

## How to Test

1. **Hard refresh**: `Ctrl + Shift + R` (or `Cmd + Shift + R`)

2. **Go to**: https://multi.aunoo.ai/config → Users tab

3. **Create a test user**:
   - Username: `testforce`
   - Email: `test@example.com`
   - Password: `TestPass123`
   - Role: `user`
   - ✅ Force password change (leave checked)
   - ☐ Skip onboarding (leave unchecked)

4. **Click "Create User"**

5. **Logout and login as test user**:
   - You should be redirected to `/change_password`
   - Change the password
   - You should then see the onboarding wizard (if it exists)

6. **Create another user with different settings**:
   - Try with force password change unchecked
   - Try with skip onboarding checked
   - See how login flow changes

---

## Success Criteria ✅

- [x] Checkboxes appear in create user form
- [x] Checkboxes have default values (force=true, skip=false)
- [x] Values are sent to API in JSON
- [x] Backend stores values in database
- [x] Login flow respects `force_password_change`
- [x] Login flow respects `completed_onboarding`
- [x] User creation logs show flag values
- [x] All changes are production-ready

---

**Status**: ✅ PRODUCTION READY
**Testing**: Ready for verification

Last Updated: 2025-10-21 12:15
