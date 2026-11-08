import datetime
import math
import uuid
from typing import Dict, Any, Optional
import jwt
import bcrypt
import redis
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from common.config import settings
from common.database import get_db
from common.models import User

_redis_client: Optional[redis.Redis] = None


def _revocation_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Token revocation service unavailable; please retry",
        headers={"Retry-After": "1"},
    )


def get_redis_client() -> redis.Redis:
    global _redis_client
    if not settings.REDIS_URL:
        raise _revocation_unavailable()
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
                socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
                retry_on_timeout=False,
            )
        except (redis.RedisError, ValueError):
            raise _revocation_unavailable() from None
    return _redis_client


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def _decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "id", "jti"]},
        )
        if (
            any(not isinstance(payload[key], str) or not payload[key] for key in ("id", "sub", "jti"))
            or isinstance(payload["exp"], bool)
            or not isinstance(payload["exp"], (int, float))
            or not math.isfinite(payload["exp"])
        ):
            raise jwt.InvalidTokenError("Invalid token claims")
        return payload
    except (jwt.PyJWTError, TypeError, ValueError, OverflowError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def is_token_revoked(token_id: str) -> bool:
    try:
        return get_redis_client().exists(f"revoked_token:{token_id}") > 0
    except redis.RedisError:
        raise _revocation_unavailable() from None


def revoke_token(token: str) -> bool:
    payload = _decode_token(token)
    remaining = max(
        1,
        math.ceil(
            payload["exp"] - datetime.datetime.now(datetime.timezone.utc).timestamp()
        ),
    )
    try:
        written = get_redis_client().setex(
            f"revoked_token:{payload['jti']}", remaining, "revoked"
        )
    except redis.RedisError:
        raise _revocation_unavailable() from None
    if not written:
        raise _revocation_unavailable()
    return True


def decode_access_token(token: str) -> Dict[str, Any]:
    payload = _decode_token(token)
    if is_token_revoked(payload["jti"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_token_from_header(authorization: Optional[str] = Header(None)) -> str:
    parts = authorization.split() if authorization else []
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Bearer credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


def get_current_user(
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    user_id = payload["id"]
    username = payload["sub"]
    user = db.get(User, user_id)
    if user is None or user.username != username or user.role not in ("admin", "employee"):
        raise HTTPException(status_code=401, detail="Account is not active")
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return current_user
