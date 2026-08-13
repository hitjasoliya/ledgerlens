from __future__ import annotations
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import List, Optional
from pathlib import Path

# Path setup for imports when running standalone or in container
root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from common.database import Base, engine, get_db, SessionLocal
from common.models import User
from common.schemas import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    UserCreateRequest,
    ClearChatResponse,
    HealthResponse,
)
from common.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    revoke_token,
)
from common.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin_pass = os.getenv("ADMIN_INITIAL_PASSWORD", "admin123")
            admin = User(
                username="admin",
                hashed_password=get_password_hash(admin_pass),
                role="admin",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="LedgerLens Identity Service", lifespan=lifespan)


def get_token_from_header(
    authorization: Optional[str] = Header(None),
    token_param: Optional[str] = Depends(oauth2_scheme),
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ")[1]
    if token_param:
        return token_param
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin access required",
        )
    return current_user


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "id": user.id}
    )
    user_resp = UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        createdAt=int(user.created_at.timestamp() * 1000),
    )
    return LoginResponse(access_token=access_token, user=user_resp)


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        createdAt=int(current_user.created_at.timestamp() * 1000),
    )


@app.post("/api/auth/logout", response_model=ClearChatResponse)
def logout(token: str = Depends(get_token_from_header)):
    revoke_token(token)
    return ClearChatResponse(ok=True)


@app.get("/api/users", response_model=List[UserResponse])
def get_users(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            role=u.role,
            createdAt=int(u.created_at.timestamp() * 1000),
        )
        for u in users
    ]


@app.post("/api/users", response_model=UserResponse)
def create_user(
    body: UserCreateRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    new_user = User(
        username=body.username,
        hashed_password=get_password_hash(body.password),
        role=body.role if body.role in ["admin", "employee"] else "employee",
        created_by=current_user.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        role=new_user.role,
        createdAt=int(new_user.created_at.timestamp() * 1000),
    )


@app.delete("/api/users/{user_id}", response_model=ClearChatResponse)
def delete_user(
    user_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.delete(user)
    db.commit()
    return ClearChatResponse(ok=True)
