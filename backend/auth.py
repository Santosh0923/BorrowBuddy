import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy.orm import Session

import models
from database import get_db


# --------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------
# JWT SETTINGS
# --------------------------------------------------

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32 or SECRET_KEY == 'borrowbuddy-development-secret':
    raise RuntimeError('Set JWT_SECRET_KEY to a random secret of at least 32 characters in backend/.env')

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 120


# --------------------------------------------------
# PASSWORD HANDLING
# --------------------------------------------------

password_hash = PasswordHash.recommended()


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
):
    try:
        return password_hash.verify(plain_password, hashed_password)
    except (ValueError, UnknownHashError):
        # Invalid legacy hashes must not crash login or disclose account details.
        return False


# --------------------------------------------------
# JWT TOKEN CREATION
# --------------------------------------------------

def create_access_token(
    user_id: int,
    email: str,
    role: str,
):
    expiry = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expiry,
    }

    token = jwt.encode(
        payload, SECRET_KEY, algorithm=ALGORITHM,
    )

    return token


# --------------------------------------------------
# OAUTH2
# --------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


# --------------------------------------------------
# CURRENT USER DEPENDENCY
# --------------------------------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired login",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, SECRET_KEY,
            algorithms=[ALGORITHM],
            options={'require': ['sub', 'exp']},
        )
        user_id = int(payload.get("sub", ""))

        if user_id <= 0:
            raise credentials_exception

    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.query(models.User)
        .filter(models.User.id == int(user_id))
        .first()
    )

    if user is None:
        raise credentials_exception

    if not user.is_active or user.role not in ('student', 'faculty', 'admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


# --------------------------------------------------
# ROLE AUTHORIZATION DEPENDENCIES
# --------------------------------------------------

def require_admin(
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_faculty(
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    if current_user.role not in ("faculty",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty access required",
        )
    return current_user


def require_faculty_or_admin(
    current_user: models.User = Depends(
        get_current_user,
    ),
):
    if current_user.role not in ("faculty", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty or Admin access required",
        )
    return current_user


def require_student(current_user: models.User = Depends(get_current_user)):
    if current_user.role != 'student':
        raise HTTPException(status_code=403, detail='Student access required')
    return current_user
