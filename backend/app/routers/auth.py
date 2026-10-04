"""
Auth router — login, /auth/me, admin user management, rate-limited login.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.deps import get_current_user, get_db, require_role
from app.models import User, UserRole
from app.schemas import PaginatedResponse, Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for login (per-IP, sliding window)
# ---------------------------------------------------------------------------

_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 60


def _rate_limit_login(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts.setdefault(ip, [])
    # Purge old
    _login_attempts[ip] = [t for t in attempts if now - t < _WINDOW_SECONDS]
    if len(_login_attempts) > 10_000:
        expired_before = now - _WINDOW_SECONDS
        for address, timestamps in list(_login_attempts.items()):
            active = [timestamp for timestamp in timestamps if timestamp >= expired_before]
            if active:
                _login_attempts[address] = active
            else:
                _login_attempts.pop(address, None)
    if len(_login_attempts[ip]) >= _MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try later.")
    _login_attempts[ip].append(now)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password flow login. Returns a JWT."""
    _rate_limit_login(request)

    user = db.query(User).filter(User.email == form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")

    # Authorization always uses the current database role, never a client-editable JWT claim.
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return user


@router.get("/users", response_model=PaginatedResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Admin-only: list all users with pagination."""
    total = db.query(User).count()
    items = (
        db.query(User)
        .order_by(User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(
        items=[UserRead.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(
    body: UserCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Admin-only: create a new user."""
    # Validate role
    valid_roles = {r.value for r in UserRole}
    if body.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"Invalid role. Must be one of {valid_roles}")

    # Check duplicate email
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    new_user = User(
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
        role=UserRole(body.role),
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
