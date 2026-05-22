"""
models.py — Auth Models (Phase 11)

User schemas and simulated DB for lightweight production setup.
Roles: admin, clinician, reviewer
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr
from typing import Optional

class UserRole:
    ADMIN = "admin"
    CLINICIAN = "clinician"
    REVIEWER = "reviewer"

class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str = UserRole.CLINICIAN

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: str
    disabled: bool = False

class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

# In-memory user store for demo purposes.
# In a real production environment, this would be a PostgreSQL table.
# Pre-populated with an admin for testing.
from backend.auth.security import get_password_hash
import uuid

_FAKE_USERS_DB = {
    "admin": UserInDB(
        id=str(uuid.uuid4()),
        username="admin",
        email="admin@aegis.com",
        role=UserRole.ADMIN,
        hashed_password=get_password_hash("admin"),
        disabled=False,
    )
}

def get_user(username: str) -> Optional[UserInDB]:
    return _FAKE_USERS_DB.get(username)

def create_user(user: UserCreate) -> UserInDB:
    if user.username in _FAKE_USERS_DB:
        raise ValueError("User already exists")
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user.password)
    user_db = UserInDB(
        id=user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        hashed_password=hashed_password,
    )
    _FAKE_USERS_DB[user.username] = user_db
    return user_db
