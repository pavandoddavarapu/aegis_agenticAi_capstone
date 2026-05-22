"""
dependencies.py — Auth Dependencies (Phase 11)

FastAPI dependencies to protect routes and enforce RBAC.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from backend.auth.security import decode_access_token
from backend.auth.models import get_user, User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    user = get_user(username)
    if user is None:
        raise credentials_exception
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

def require_role(allowed_roles: list[str]):
    """Dependency factory for RBAC."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {allowed_roles}",
            )
        return current_user
    return role_checker

# Pre-configured dependencies
require_admin     = require_role([UserRole.ADMIN])
require_reviewer  = require_role([UserRole.REVIEWER, UserRole.CLINICIAN]) # Clinicians can review
require_clinician = require_role([UserRole.CLINICIAN])
