from __future__ import annotations
import logging
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

from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.database import Base, engine, get_db, SessionLocal, initialize_database
from common.models import User, Document, ChatSessionModel, ChatMessageModel
from common.schemas import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    UserCreateRequest,
    ClearChatResponse,
    HealthResponse,
    Page,
    ResourceId,
)
from common.auth import (
    get_token_from_header,
    get_current_user,
    get_admin_user,
    verify_password,
    get_password_hash,
    create_access_token,
    revoke_token,
    get_redis_client,
)
from common.config import settings
from common.http import configure_validation_errors, page_params

logger = logging.getLogger("identity")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Explicit schema initialization; no import-time create_all
    initialize_database()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin_pass = settings.ADMIN_INITIAL_PASSWORD
            if not admin_pass:
                raise RuntimeError(
                    "ADMIN_INITIAL_PASSWORD must be explicitly configured to initialize the administrator account"
                )
            try:
                admin = User(
                    username="admin",
                    hashed_password=get_password_hash(admin_pass),
                    role="admin",
                )
                db.add(admin)
                db.commit()
                logger.info("Initial administrator account bootstrapped successfully")
            except IntegrityError:
                db.rollback()
                logger.info("Administrator account was initialized concurrently")
    finally:
        db.close()
    yield
    engine.dispose()



app = FastAPI(title="LedgerLens Identity Service", lifespan=lifespan)
configure_validation_errors(app)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    status_details = {}
    is_ready = True
    try:
        db.execute(text("SELECT 1"))
        status_details["database"] = "connected"
    except Exception as exc:
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        status_details["database"] = "unavailable"
        is_ready = False

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        status_details["redis"] = "connected"
    except Exception as exc:
        logger.warning("Redis readiness probe failed: %s", type(exc).__name__)
        status_details["redis"] = "unavailable"
        is_ready = False

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "dependencies": status_details},
        )
    return {"status": "ready", "dependencies": status_details}


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if (
        not user
        or user.role not in ("admin", "employee")
        or not verify_password(body.password, user.hashed_password)
    ):
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
def logout(
    current_user: User = Depends(get_current_user),
    token: str = Depends(get_token_from_header),
):
    revoke_token(token)
    return ClearChatResponse(ok=True)


@app.get("/api/users", response_model=Page[UserResponse])
def list_users(
    page: tuple[int, int] = Depends(page_params),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(select(User).order_by(User.created_at, User.id).limit(limit).offset(offset)).all()
    return Page[UserResponse](
        items=[
            UserResponse(
                id=u.id,
                username=u.username,
                role=u.role,
                createdAt=int(u.created_at.timestamp() * 1000),
            )
            for u in users
        ],
        total=total, limit=limit, offset=offset,
    )


@app.post("/api/users", response_model=UserResponse)
def create_user(
    body: UserCreateRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    new_user = User(
        username=body.username,
        hashed_password=get_password_hash(body.password),
        role=body.role,
        created_by=current_user.id,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    db.refresh(new_user)

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        role=new_user.role,
        createdAt=int(new_user.created_at.timestamp() * 1000),
    )


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: ResourceId,
    transfer_to: Optional[ResourceId] = Query(None, description="Active admin recipient ID for owned documents"),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    admin_id = current_user.id
    if user_id == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    # Roll back read transaction opened by get_admin_user dependency
    db.rollback()

    try:
        with db.begin():
            if db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            # Acquire row locks in deterministic ordered sequence
            user_ids = sorted(set([admin_id, user_id] + ([transfer_to] if transfer_to else [])))
            locked_users = {
                u.id: u
                for u in db.query(User).filter(User.id.in_(user_ids)).order_by(User.id).with_for_update().all()
            }
            operator = locked_users.get(admin_id)
            if operator is None or operator.role != "admin":
                raise HTTPException(status_code=403, detail="Administrator access required")
            user = locked_users.get(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            # Validate and lock transfer recipient if specified
            recipient = None
            if transfer_to:
                if transfer_to == user_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Transfer recipient cannot be the departing user",
                    )
                recipient = locked_users.get(transfer_to)
                if not recipient or recipient.role != "admin":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Transfer recipient must be an active administrator",
                    )
            # Deterministically lock all documents owned by departing user
            owned_docs = (
                db.query(Document)
                .filter(Document.owner_id == user_id)
                .with_for_update()
                .all()
            )

            # If user owns documents, named active admin recipient is required
            if owned_docs and not transfer_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account owns documents; an active administrator recipient is required for ownership transfer",
                )

            # Transfer document ownership to recipient admin
            if transfer_to and owned_docs:
                for doc in owned_docs:
                    doc.owner_id = transfer_to

            # Deterministically lock and irreversibly delete private conversations
            # Receiving administrator must NOT inherit private conversation history
            sessions = (
                db.query(ChatSessionModel)
                .filter(ChatSessionModel.user_id == user_id)
                .with_for_update()
                .all()
            )
            session_ids = [s.id for s in sessions]
            if session_ids:
                db.query(ChatMessageModel).filter(
                    ChatMessageModel.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.query(ChatSessionModel).filter(
                    ChatSessionModel.id.in_(session_ids)
                ).delete(synchronize_session=False)

            # Remove the departing user record
            db.delete(user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error during account deletion and transfer: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove account due to internal database error",
        )

