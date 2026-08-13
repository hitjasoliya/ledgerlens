import datetime
from typing import Dict, Any, Optional
import jwt
import bcrypt
import redis
from fastapi import HTTPException, status
from common.config import settings

# Optional Redis connection for token revocation
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is None and settings.REDIS_URL:
        try:
            _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


_in_memory_revoked_tokens: set[str] = set()


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
    if expires_delta:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def is_token_revoked(token: str) -> bool:
    r = get_redis_client()
    if r is not None:
        try:
            return r.exists(f"revoked_token:{token}") > 0
        except Exception:
            pass
    return token in _in_memory_revoked_tokens


def revoke_token(token: str, expire_seconds: int = 86400) -> bool:
    r = get_redis_client()
    if r is not None:
        try:
            r.setex(f"revoked_token:{token}", expire_seconds, "revoked")
            return True
        except Exception:
            pass
    _in_memory_revoked_tokens.add(token)
    return True


def decode_access_token(token: str) -> Dict[str, Any]:
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
