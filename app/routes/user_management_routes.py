"""
User Management Routes for Multi-User Support
Created: 2025-10-21

Provides API endpoints for user administration:
- List users (admin only)
- Create users (admin only)
- Update users (admin only)
- Delete/deactivate users (admin only)
- Change own password (all users)
- Get current user info (all users)
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, EmailStr
from app.security.session import verify_session, require_admin, get_current_username
from app.security.auth import get_password_hash, verify_password
from app.database import get_database_instance
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])

# ==================== Pydantic Models ====================

class UserCreate(BaseModel):
    """Model for creating a new user."""
    username: str
    email: EmailStr
    password: str
    role: str = "user"
    force_password_change: bool = True
    completed_onboarding: bool = False

class UserUpdate(BaseModel):
    """Model for updating user information."""
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    """Model for password change requests."""
    current_password: str
    new_password: str

# ==================== API Endpoints ====================

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
    """
    List all users (admin only).

    Args:
        include_inactive: Include deactivated users in the list

    Returns:
        List of users with password hashes removed
    """
    db = get_database_instance()
    users = db.facade.list_all_users(include_inactive=include_inactive)

    # Mark OAuth users (check BEFORE removing password hash)
    for user in users:
        # OAuth users don't have password_hash (authenticate via third-party providers)
        has_password = bool(user.get('password_hash'))
        user['is_oauth'] = not has_password
        # Remove password hash for security (don't send to frontend)
        user.pop('password_hash', None)

    return {"users": users}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    request: Request,
    session=Depends(require_admin)
):
    """
    Create a new user (admin only).

    Validates:
    - Username uniqueness
    - Email uniqueness
    - Role validity

    Returns:
        Created user information (without password hash)
    """
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
    try:
        user = db.facade.create_user(
            username=user_data.username,
            email=user_data.email,
            password_hash=password_hash,
            role=user_data.role,
            force_password_change=user_data.force_password_change,
            completed_onboarding=user_data.completed_onboarding
        )

        user.pop('password_hash', None)
        logger.info(f"User created: {user_data.username} by {get_current_username(request)} "
                   f"(force_pw_change={user_data.force_password_change}, "
                   f"onboarding_done={user_data.completed_onboarding})")
        return {"user": user}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")


@router.patch("/{username}")
async def update_user(
    username: str,
    updates: UserUpdate,
    request: Request,
    session=Depends(require_admin)
):
    """
    Update user information (admin only).

    Can update:
    - email
    - role
    - is_active status

    Validates role if being updated.
    """
    db = get_database_instance()

    user = db.facade.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Apply updates
    update_dict = updates.dict(exclude_unset=True)

    # Validate role if being updated
    if 'role' in update_dict and update_dict['role'] not in ['admin', 'user']:
        raise HTTPException(status_code=400, detail="Invalid role")

    try:
        db.facade.update_user(username, **update_dict)
        logger.info(f"User updated: {username} by {get_current_username(request)}")
        return {"message": "User updated successfully"}
    except Exception as e:
        logger.error(f"Error updating user {username}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")


@router.delete("/{username}")
async def delete_user(
    username: str,
    request: Request,
    session=Depends(require_admin)
):
    """
    Deactivate a user (admin only).

    Security checks:
    - Cannot delete own account
    - Cannot delete last admin user

    Performs soft delete (sets is_active=False).
    """
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

    try:
        db.facade.deactivate_user_by_username(username)
        logger.info(f"User deactivated: {username} by {current_user}")
        return {"message": f"User {username} deactivated successfully"}
    except Exception as e:
        logger.error(f"Error deactivating user {username}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deactivating user: {str(e)}")


@router.post("/me/change-password")
async def change_own_password(
    password_data: PasswordChange,
    request: Request,
    session=Depends(verify_session)
):
    """
    Allow users to change their own password.

    Validates:
    - Current password is correct
    - New password meets requirements (min 8 chars)
    - User is not OAuth user (OAuth users can't change password)
    """
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
    try:
        new_hash = get_password_hash(password_data.new_password)
        db.facade.update_user(username, password_hash=new_hash, force_password_change=False)

        logger.info(f"User {username} changed their password")
        return {"message": "Password changed successfully"}
    except Exception as e:
        logger.error(f"Error changing password for {username}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error changing password")


# ==================== Admin password reset ====================

class AdminPasswordReset(BaseModel):
    """mode: auto = email the reset link when possible, else temp password."""
    mode: str = "auto"  # auto | email | temp


@router.post("/{username}/reset-password")
async def admin_reset_password(
    username: str,
    req: AdminPasswordReset,
    request: Request,
    session=Depends(require_admin),
):
    """Reset a user's password (admin only).

    email: sends a signed, 24h reset link to the user's email — the admin
    never sees the new secret. temp: sets a temporary password (returned
    once) with a forced change on first login. auto picks email when the
    user has an address and email is configured.
    """
    db = get_database_instance()
    user = db.facade.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.get("password_hash"):
        raise HTTPException(status_code=400,
                            detail="OAuth account — password is managed by the identity provider")

    from app.services.email_service import get_email_service
    email_svc = get_email_service()
    has_email = bool(user.get("email")) and "@" in (user.get("email") or "")
    mode = (req.mode or "auto").lower()
    if mode == "auto":
        mode = "email" if (has_email and email_svc.is_available()) else "temp"

    admin_name = get_current_username(request)

    if mode == "email":
        if not has_email:
            raise HTTPException(status_code=400, detail="User has no email address on file")
        if not email_svc.is_available():
            raise HTTPException(status_code=400, detail="Email service is not configured on this tenant")
        from app.routes.auth_routes import build_password_reset_link
        link = build_password_reset_link(username, db)
        html = f"""
        <h2>Password reset</h2>
        <p>An administrator requested a password reset for your account <strong>{username}</strong>.</p>
        <p style="margin:20px 0"><a href="{link}" style="display:inline-block;background:#667eea;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold">Set a new password</a></p>
        <p style="color:#888;font-size:12px">The link is valid for 24 hours and can be used once. If you did not expect this, you can ignore this email — your current password keeps working.</p>
        """
        ok = email_svc.send_email(
            to_addresses=[user["email"]],
            subject="[AuNoo AI] Password reset",
            body_html=html,
            body_text=f"Set a new password for {username}: {link}\n(Valid 24 hours, single use.)",
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to send the reset email")
        logger.info(f"Password reset link emailed to {user['email']} for {username} by {admin_name}")
        return {"method": "email", "email": user["email"], "expires_hours": 24}

    if mode != "temp":
        raise HTTPException(status_code=400, detail="mode must be auto, email or temp")
    import secrets as _secrets
    temp_password = _secrets.token_urlsafe(9)
    db.facade.update_user(username,
                          password_hash=get_password_hash(temp_password),
                          force_password_change=True)
    logger.info(f"Temporary password set for {username} by {admin_name}")
    return {"method": "temp", "temp_password": temp_password,
            "note": "Shown once — the user must change it on first login"}
