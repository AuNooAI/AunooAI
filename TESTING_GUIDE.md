# Multi-User Implementation - Testing Guide

**Status**: ✅ Application Running
**Port**: 10014
**Started**: 2025-10-21 11:02

---

## ✅ Issue Resolved

**Problem**: Application was crashing due to missing `email-validator` package
**Solution**: Installed `email-validator` package
**Current Status**: Application running successfully with all routes loaded

---

## 🧪 Testing the Implementation

### 1. Login as Admin

**Navigate to**: `http://your-domain/login`

**Credentials**:
- Username: `admin`
- Password: `admin` (if first login) OR your set admin password

**Important**: You MUST be logged in to access the Users tab.

---

### 2. Access Users Tab

Once logged in:

1. Navigate to: `http://your-domain/config`
2. Click on the **"Users"** tab (last tab on the right)
3. The page should load and show:
   - Your current role badge (Admin or User)
   - Create new user form (if you're admin)
   - List of all users

---

### 3. Expected Behavior

**If you're an Admin**:
```
✓ See "Create New User" form
✓ See table with all users
✓ See Delete buttons for other users (not yourself)
✓ Can create new users
✓ Can delete users (except yourself and last admin)
```

**If you're a regular User**:
```
✓ See list of all users
✗ Cannot see Create User form
✗ Cannot delete users
```

---

## 🐛 Troubleshooting

### Error: "Error loading users: Failed to load users"

**Possible Causes**:

1. **Not logged in**
   - Solution: Go to `/login` and log in first

2. **Session expired**
   - Solution: Refresh page and log in again

3. **Not an admin** (for list endpoint)
   - Solution: Only admins can access `/api/users/` endpoint
   - Regular users should still see their own info

---

### Test API Endpoints Directly

**1. Check if you're logged in:**
```bash
curl http://localhost:10014/api/users/me \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

**2. Test list users (admin only):**
```bash
curl http://localhost:10014/api/users/ \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

**Expected responses:**

**Success (admin)**:
```json
{
  "users": [
    {
      "username": "admin",
      "email": "admin@localhost",
      "role": "admin",
      "is_active": true,
      "is_oauth": false
    }
  ]
}
```

**Error (not authenticated)**:
```
307 Temporary Redirect to /login
```

**Error (not admin)**:
```json
{
  "detail": "Admin access required"
}
```

---

## ✅ Verification Checklist

### Backend Verification
- [x] Application started successfully
- [x] email-validator installed
- [x] All routers registered
- [x] Database migration completed
- [x] Facade methods tested

### Frontend Verification (Manual)
- [ ] Login page works
- [ ] Can log in as admin
- [ ] Users tab visible in /config
- [ ] Users tab loads without errors
- [ ] Create user form visible (admin only)
- [ ] Users list displays correctly
- [ ] Can create new user
- [ ] Can delete users (with protections)

---

## 📊 Current Database State

```sql
-- Check users
SELECT username, email, role, is_active FROM users;

Expected:
username | email            | role  | is_active
---------|------------------|-------|----------
admin    | admin@localhost  | admin | true
```

---

## 🎯 Quick Test Script

Run this to verify everything:

```bash
# 1. Check application is running
ps aux | grep "multi.aunoo.ai.*server_run"

# 2. Check logs for errors
sudo journalctl -u multi.aunoo.ai.service --no-pager -n 50 | grep ERROR

# 3. Test database
source .venv/bin/activate
python -c "
from app.database import get_database_instance
db = get_database_instance()
users = db.facade.list_all_users()
print(f'Total users: {len(users)}')
for user in users:
    print(f'  - {user[\"username\"]}: {user[\"role\"]}')
"

# 4. Check port is listening
netstat -tlnp | grep 10014
```

---

## 📝 Next Steps After Testing

1. **Create additional users** via the Users tab
2. **Test login with new users** to verify they work
3. **Test role permissions** (admin vs user)
4. **Test deactivation** - deactivate a test user and verify they can't log in
5. **Test last admin protection** - try to delete the last admin (should fail)

---

## 🔒 Security Tests

1. **Deactivated User Cannot Login**
   - Deactivate a user via API or database
   - Try to login - should see "account deactivated" error

2. **Last Admin Protection**
   - Try to delete the only admin user
   - Should get error: "Cannot delete the last admin user"

3. **Cannot Delete Self**
   - Try to delete your own account
   - Should get error: "Cannot delete your own account"

4. **Session Validation**
   - Deactivate a logged-in user's account
   - Their session should be cleared on next request

---

## 📚 Documentation

- **Full Implementation**: `IMPLEMENTATION_COMPLETE.md`
- **Step-by-Step Guide**: `IMPLEMENTATION_GUIDE.md`
- **Checkpoint Log**: `CHECKPOINT.md`
- **API Documentation**: `app/routes/user_management_routes.py` (docstrings)

---

**Last Updated**: 2025-10-21 11:03
**Status**: ✅ Ready for Testing
