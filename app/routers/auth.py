from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User
from app.ratelimit import RateLimiter
from app.schemas import PasswordChange, Token, UserCreate, UserOut, UserUpdate
from app.security import create_access_token, get_current_user, hash_password, require_roles, verify_password

router = APIRouter(tags=["auth"])

login_limiter = RateLimiter(lambda: settings.rate_limit_login_per_minute)
password_limiter = RateLimiter(lambda: settings.rate_limit_password_per_minute)


@router.post("/auth/login", response_model=Token, dependencies=[Depends(login_limiter)])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return Token(access_token=create_access_token(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password", status_code=204, dependencies=[Depends(password_limiter)])
def change_password(body: PasswordChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, full_name=body.full_name, role=body.role, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_roles(Role.admin))
):
    """Edit name/role, deactivate or reactivate, or reset a password (admin-driven reset)."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    removing_admin = user.role == Role.admin and user.is_active and (
        body.is_active is False or (body.role is not None and body.role != Role.admin)
    )
    if removing_admin:
        others = db.scalar(
            select(func.count()).select_from(User).where(User.role == Role.admin, User.is_active, User.id != user.id)
        )
        if user.id == admin.id or not others:
            raise HTTPException(409, "Cannot deactivate or demote yourself / the last active admin")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    db.commit()
    return user
