# Simple Multi-User Implementation Guide
## Step-by-Step Instructions with All Required Changes

**Version**: 1.1 Corrected
**Date**: 2025-10-21
**Estimated Time**: 3-4 hours (AI implementation)

---

## 📋 Prerequisites Checklist

Before starting:
- [ ] Backup PostgreSQL database: `pg_dump -U multi_user -d multi -f backup_$(date +%Y%m%d).sql`
- [ ] Current working directory: `/home/orochford/tenants/multi.aunoo.ai`
- [ ] Virtual environment activated: `source .venv/bin/activate`
- [ ] No uncommitted changes in git (or commit/stash first)
- [ ] Test database available (optional but recommended)

---

## 📁 Files Overview

### New Files to Create (4 files)
1. `alembic/versions/simple_multiuser_corrected.py` - Migration ✅ READY
2. `app/routes/user_management_routes.py` - User management API
3. `app/security/session_updated.py` - Corrected session validation ✅ READY
4. Updated `templates/config.html` - User management UI

### Files to Modify (3 files)
1. `app/database_query_facade.py` - Add user management methods
2. `app/routes/auth_routes.py` - Add is_active check to login
3. `app/main.py` - Register new routes

### Files to Replace (1 file)
1. `app/security/session.py` - Replace with corrected version

---

## 🚀 Implementation Steps

### Step 1: Create Database Facade Methods (15 min)

**File**: `app/database_query_facade.py`

**Location**: Add these methods to the `DatabaseQueryFacade` class (around line 100, after existing methods)

```python
# ==================== USER MANAGEMENT METHODS ====================
# Add these methods to DatabaseQueryFacade class

def create_user(self, username: str, email: str, password_hash: str,
                role: str = 'user', is_active: bool = True) -> Dict:
    """Create a new user."""
    from app.database_models import t_users
    from sqlalchemy import insert

    # Force username to lowercase for consistency
    username = username.lower()

    stmt = insert(t_users).values(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
        force_password_change=False,
        completed_onboarding=False
    )
    self._execute_with_rollback(stmt, operation_name="create_user")

    # Return created user
    return self.get_user_by_username(username)

def get_user_by_username(self, username: str) -> Optional[Dict]:
    """Get user by username."""
    from app.database_models import t_users
    from sqlalchemy import select

    stmt = select(t_users).where(t_users.c.username == username.lower())
    result = self._execute_with_rollback(stmt, operation_name="get_user_by_username")
    row = result.fetchone()
    return dict(row._mapping) if row else None

def get_user_by_email(self, email: str) -> Optional[Dict]:
    """Get user by email."""
    from app.database_models import t_users
    from sqlalchemy import select

    stmt = select(t_users).where(t_users.c.email == email.lower())
    result = self._execute_with_rollback(stmt, operation_name="get_user_by_email")
    row = result.fetchone()
    return dict(row._mapping) if row else None

def list_all_users(self, include_inactive: bool = False) -> List[Dict]:
    """List all users."""
    from app.database_models import t_users
    from sqlalchemy import select

    stmt = select(t_users)
    if not include_inactive:
        stmt = stmt.where(t_users.c.is_active == True)
    stmt = stmt.order_by(t_users.c.username)

    result = self._execute_with_rollback(stmt, operation_name="list_all_users")
    return [dict(row._mapping) for row in result.fetchall()]

def update_user(self, username: str, **updates) -> bool:
    """Update user fields."""
    from app.database_models import t_users
    from sqlalchemy import update

    stmt = update(t_users).where(t_users.c.username == username.lower()).values(**updates)
    self._execute_with_rollback(stmt, operation_name="update_user")
    return True

def deactivate_user(self, username: str) -> bool:
    """Soft delete user (set is_active=False)."""
    from app.database_models import t_users
    from sqlalchemy import update

    stmt = update(t_users).where(t_users.c.username == username.lower()).values(is_active=False)
    self._execute_with_rollback(stmt, operation_name="deactivate_user")
    return True

def check_user_is_admin(self, username: str) -> bool:
    """Check if user is admin."""
    user = self.get_user_by_username(username)
    return user and user.get('role') == 'admin' if user else False

def count_admin_users(self) -> int:
    """Count active admin users."""
    from app.database_models import t_users
    from sqlalchemy import select, func, and_

    stmt = select(func.count()).select_from(t_users).where(
        and_(t_users.c.role == 'admin', t_users.c.is_active == True)
    )
    result = self._execute_with_rollback(stmt, operation_name="count_admin_users")
    return result.scalar() or 0
```

**Verification**:
```bash
python -c "from app.database import get_database_instance; db = get_database_instance(); print('Facade methods available:', dir(db.facade))" | grep -i user
```

---

### Step 2: Update database_models.py (5 min)

**File**: `app/database_models.py`

**Find** (around line 460):
```python
t_users = Table(
    'users', metadata,
    Column('username', Text, primary_key=True),
    Column('password_hash', Text, nullable=False),
    Column('force_password_change', Boolean, default=text('0')),
    Column('completed_onboarding', Boolean, default=text('0'))
)
```

**Replace with**:
```python
t_users = Table(
    'users', metadata,
    Column('username', Text, primary_key=True),
    Column('password_hash', Text, nullable=False),
    Column('email', Text, unique=True),
    Column('role', Text, default='user'),
    Column('is_active', Boolean, default=True),
    Column('force_password_change', Boolean, default=text('FALSE')),
    Column('completed_onboarding', Boolean, default=text('FALSE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_users_email', 'email'),
    Index('idx_users_is_active', 'is_active'),
    Index('idx_users_role', 'role'),
    CheckConstraint("role IN ('admin', 'user')", name='check_user_role')
)
```

**Note**: Don't run this until after the migration! This is just for the model definition.

---

### Step 3: Replace session.py (10 min)

**File**: `app/security/session.py`

**Action**: Replace entire file contents

```bash
# Backup original
cp app/security/session.py app/security/session.py.backup

# Replace with updated version
cp app/security/session_updated.py app/security/session.py
```

**Or manually**: Copy contents from `session_updated.py` file created earlier

---

### Step 4: Update auth_routes.py (5 min)

**File**: `app/routes/auth_routes.py`

**Find** (around line 78-80):
```python
is_valid = verify_password(password, user['password'])
logger.debug(f"Password verification result: {is_valid}")

if not is_valid:
```

**Add AFTER line 80** (after password verification):
```python
# CRITICAL: Check if user is active
if not user.get('is_active', True):
    logger.warning(f"Login attempt for inactive user: {username}")
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "session": request.session,
            "error": "This account has been deactivated. Please contact an administrator."
        },
        status_code=status.HTTP_401_UNAUTHORIZED
    )
```

---

### Step 5: Create User Management Routes (20 min)

**File**: `app/routes/user_management_routes.py` (NEW)

**Action**: Create new file with full contents:

<details>
<summary>Click to expand full user_management_routes.py code (200 lines)</summary>

```python
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, EmailStr
from app.security.session import verify_session, require_admin, get_current_username
from app.security.auth import get_password_hash, verify_password
from app.database import get_database_instance
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])

# Pydantic Models
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "user"

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# Endpoints
@router.get("/me")
async def get_current_user_info(request: Request, session=Depends(verify_session)):
    """Get current user's information."""
    from app.security.session import get_current_user_info

    user_info = get_current_user_info(request)
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    return user_info

@router.get("/")
async def list_users(
    request: Request,
    include_inactive: bool = False,
    session=Depends(require_admin)
):
    """List all users (admin only)."""
    db = get_database_instance()
    users = db.facade.list_all_users(include_inactive=include_inactive)

    # Remove password hashes and mark OAuth users
    for user in users:
        user.pop('password_hash', None)
        user['is_oauth'] = (not user.get('password_hash'))

    return {"users": users}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    request: Request,
    session=Depends(require_admin)
):
    """Create a new user (admin only)."""
    db = get_database_instance()

    # Check if user already exists
    if db.facade.get_user_by_username(user_data.username):
        raise HTTPException(status_code=400, detail="Username already exists")

    if db.facade.get_user_by_email(user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate role
    if user_data.role not in ['admin', 'user']:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'user'")

    # Hash password
    password_hash = get_password_hash(user_data.password)

    # Create user
    user = db.facade.create_user(
        username=user_data.username,
        email=user_data.email,
        password_hash=password_hash,
        role=user_data.role
    )

    user.pop('password_hash', None)
    return {"user": user}

@router.patch("/{username}")
async def update_user(
    username: str,
    updates: UserUpdate,
    request: Request,
    session=Depends(require_admin)
):
    """Update user information (admin only)."""
    db = get_database_instance()

    user = db.facade.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Apply updates
    update_dict = updates.dict(exclude_unset=True)

    # Validate role if being updated
    if 'role' in update_dict and update_dict['role'] not in ['admin', 'user']:
        raise HTTPException(status_code=400, detail="Invalid role")

    db.facade.update_user(username, **update_dict)

    return {"message": "User updated successfully"}

@router.delete("/{username}")
async def delete_user(
    username: str,
    request: Request,
    session=Depends(require_admin)
):
    """Deactivate a user (admin only)."""
    db = get_database_instance()
    current_user = get_current_username(request)

    # Don't allow deleting yourself
    if current_user and current_user.lower() == username.lower():
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.facade.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # CRITICAL: Prevent deleting last admin
    if user.get('role') == 'admin':
        admin_count = db.facade.count_admin_users()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last admin user. Promote another user to admin first."
            )

    db.facade.deactivate_user(username)

    return {"message": f"User {username} deactivated successfully"}

@router.post("/me/change-password")
async def change_own_password(
    password_data: PasswordChange,
    request: Request,
    session=Depends(verify_session)
):
    """Allow users to change their own password."""
    db = get_database_instance()
    username = get_current_username(request)

    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.facade.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # OAuth users can't change password
    if not user.get('password_hash'):
        raise HTTPException(
            status_code=400,
            detail="OAuth users cannot change password"
        )

    # Verify current password
    if not verify_password(password_data.current_password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Validate new password
    if len(password_data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Update password
    new_hash = get_password_hash(password_data.new_password)
    db.facade.update_user(username, password_hash=new_hash)

    logger.info(f"User {username} changed their password")

    return {"message": "Password changed successfully"}
```
</details>

---

### Step 6: Register Routes in main.py (5 min)

**File**: `app/main.py` (or wherever routes are registered)

**Find** the section where routes are registered (search for `include_router`)

**Add**:
```python
from app.routes import user_management_routes

# Register user management routes
app.include_router(user_management_routes.router)
```

---

### Step 7: Run Migration (10 min)

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Verify migration file exists
ls -la alembic/versions/simple_multiuser_corrected.py

# 3. Run migration
alembic upgrade head

# 4. Verify migration success
python -c "from app.database import get_database_instance; db = get_database_instance(); users = db.facade.list_all_users(include_inactive=True); print(f'Total users: {len(users)}'); [print(f'  - {u[\"username\"]}: {u[\"role\"]}') for u in users]"
```

**Expected Output**:
```
[Migration output with checkmarks]
✅ MIGRATION COMPLETE!
Total users: 1
  - admin: admin
```

---

### Step 8: Update Frontend - Config Page (30-40 min)

**File**: `templates/config.html`

This is the most involved step. See the full specification document for complete HTML/CSS/JavaScript code.

**Quick Reference**:
1. Add Users tab button (line ~35)
2. Wrap dangerous DB operations in admin-only div (line ~115)
3. Add Users tab content pane (before line 499)
4. Add CSS for user management (line ~1200)
5. Add JavaScript functions (line ~1777)

**Simplified Testing Approach**:
You can skip the frontend initially and test via curl/API:

```bash
# Test user creation
curl -X POST http://localhost:PORT/api/users/ \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{"username": "testuser", "email": "test@example.com", "password": "test1234", "role": "user"}'

# Test user listing
curl http://localhost:PORT/api/users/ \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

---

## ✅ Verification Checklist

After implementation:

### Backend Tests
- [ ] Migration completes without errors
- [ ] Admin user can log in
- [ ] Admin user can access `/api/users/`
- [ ] Admin user can create new user
- [ ] Admin user can deactivate user
- [ ] Cannot delete last admin (error returned)
- [ ] Cannot delete own account (error returned)
- [ ] Deactivated user cannot log in
- [ ] Deactivated user's existing session is cleared

### Frontend Tests (if implemented)
- [ ] Users tab appears in config page
- [ ] Current user role displays correctly
- [ ] Admin sees create user form
- [ ] Non-admin does NOT see create user form
- [ ] User list displays all users
- [ ] Create user form validates inputs
- [ ] Edit/Delete buttons work
- [ ] OAuth users show "OAuth" badge

### Security Tests
- [ ] Non-admin cannot access `/api/users/` (403 error)
- [ ] Email uniqueness enforced (duplicate email rejected)
- [ ] Username uniqueness enforced (duplicate username rejected)
- [ ] Inactive user redirected to login with error message
- [ ] Session cleared when user deactivated

---

## 🐛 Troubleshooting

### Migration Fails

**Error**: `column "email" already exists`
```bash
# Check if migration already ran
psql -U multi_user -d multi -c "\d users"

# If email column exists, migration already ran
# Rollback if needed
alembic downgrade -1
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'app.routes.user_management_routes'`
```bash
# Verify file was created
ls -la app/routes/user_management_routes.py

# Restart application
sudo systemctl restart aunooai
```

### Session Not Validating is_active

**Error**: Deactivated user can still access system
```bash
# Verify session.py was replaced
grep "CRITICAL" app/security/session.py

# Should see multiple "CRITICAL:" comments
# If not, session.py wasn't updated correctly
```

### Frontend Not Showing Users Tab

**Error**: Users tab doesn't appear
1. Clear browser cache (Ctrl+Shift+R)
2. Check browser console for JavaScript errors
3. Verify config.html was saved correctly
4. Check if loadCurrentUserInfo() is running

---

## 📊 Implementation Summary

| Step | File | Action | Time |
|------|------|--------|------|
| 1 | database_query_facade.py | Add methods | 15 min |
| 2 | database_models.py | Update t_users | 5 min |
| 3 | security/session.py | Replace file | 10 min |
| 4 | routes/auth_routes.py | Add is_active check | 5 min |
| 5 | routes/user_management_routes.py | Create new | 20 min |
| 6 | main.py | Register routes | 5 min |
| 7 | Migration | Run alembic | 10 min |
| 8 | templates/config.html | Add UI | 40 min |
| **TOTAL** | | | **~2 hours** |

Plus testing time: 30-60 minutes

---

## 🎯 Next Steps After Implementation

1. **Change Default Password**:
   ```
   Login as: admin
   Password: admin123
   → Forced to /change_password page
   → Set new strong password
   ```

2. **Create Additional Users**:
   - Go to /config → Users tab
   - Create users for your team
   - Assign admin role to trusted users

3. **Test OAuth Integration** (if configured):
   - Login via Google/GitHub
   - Verify user appears in users list
   - Verify role assignment works

4. **Monitor Logs**:
   ```bash
   sudo journalctl -u aunooai -f | grep -i user
   ```

5. **Optional Enhancements**:
   - Add user profile page
   - Add password complexity validation
   - Add bulk user import
   - Add activity logging

---

## 📚 Reference Files

All implementation files are located in:
- **Spec**: `spec-files-aunoo/simple-multiuser-spec-v1.1-corrected.md`
- **Migration**: `alembic/versions/simple_multiuser_corrected.py`
- **Session**: `app/security/session_updated.py`
- **This Guide**: `IMPLEMENTATION_GUIDE.md`

---

## 🆘 Need Help?

If you encounter issues:

1. Check logs: `sudo journalctl -u aunooai -n 100`
2. Verify database: `psql -U multi_user -d multi -c "\d users"`
3. Test API directly with curl (bypass frontend)
4. Rollback migration if needed: `alembic downgrade -1`

**Support**:
- Spec has detailed error handling section
- Migration includes rollback function
- All changes are reversible

---

**Version**: 1.1
**Last Updated**: 2025-10-21
**Status**: Ready for Implementation ✅
