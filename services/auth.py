# backend/services/auth.py
import uuid
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import users_collection, refresh_tokens_collection

import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Short-lived access token: 30 minutes
REFRESH_TOKEN_EXPIRE_DAYS = 14     # Refresh token: 14 days with rotation

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "token_type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": user_id,
        "jti": jti,
        "token_type": "refresh",
        "exp": expire,
    }
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    refresh_tokens_collection.insert_one({
        "user_id": user_id,
        "jti": jti,
        "revoked": False,
        "created_at": datetime.utcnow(),
        "expires_at": expire,
    })
    return token

def rotate_refresh_token(token_str: str) -> tuple[str, str]:
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    record = refresh_tokens_collection.find_one({"jti": jti})
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or already consumed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if record.get("revoked"):
        # Replay attack protection: revoke all active tokens for this user
        refresh_tokens_collection.update_many({"user_id": user_id}, {"$set": {"revoked": True}})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked. Potential replay attack detected. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Mark old token as revoked (single-use rotation)
    refresh_tokens_collection.update_one(
        {"_id": record["_id"]},
        {"$set": {"revoked": True, "rotated_at": datetime.utcnow()}}
    )
    
    user = users_collection.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User no longer exists")
    
    new_access_token = create_access_token({"sub": user_id})
    new_refresh_token = create_refresh_token(user_id)
    return new_access_token, new_refresh_token

def revoke_refresh_token(token_str: str) -> bool:
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            refresh_tokens_collection.update_one({"jti": jti}, {"$set": {"revoked": True}})
            return True
    except Exception:
        pass
    return False

def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") and payload.get("token_type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type: access token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id: str = payload.get("sub")
    if user_id:
        user = users_collection.find_one({"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Suspension gate: blocked suspended users from accessing any authenticated endpoint
        if user.get("is_suspended"):
            suspended_until = user.get("suspended_until")
            now = datetime.utcnow()
            if suspended_until and now < suspended_until:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ACCOUNT_SUSPENDED",
                        "message": "Your account has been suspended.",
                        "reason": user.get("suspension_reason", "Policy violation"),
                        "suspendedUntil": suspended_until.isoformat()
                    }
                )
            else:
                # Suspension has elapsed — auto-lift it
                users_collection.update_one(
                    {"id": user_id},
                    {"$set": {"is_suspended": False, "suspended_until": None, "suspension_reason": None}}
                )
                user["is_suspended"] = False

        now = datetime.utcnow()
        try:
            users_collection.update_one({"id": user_id}, {"$set": {"last_active_at": now}})
            user["last_active_at"] = now
        except Exception:
            pass
        return user

    # Support OTP-verified registration candidate token
    if payload.get("scope") == "registration_otp_verified":
        phone = payload.get("phone")
        if phone:
            return {
                "id": f"reg_{phone}",
                "phone": phone,
                "is_registration_token": True,
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid: user_id missing",
        headers={"WWW-Authenticate": "Bearer"},
    )

REGISTRATION_TOKEN_EXPIRE_MINUTES = 15

def create_registration_token(phone: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REGISTRATION_TOKEN_EXPIRE_MINUTES))
    to_encode = {
        "phone": phone,
        "scope": "registration_otp_verified",
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_registration_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "registration_otp_verified":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token scope: registration token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        phone = payload.get("phone")
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration token: phone number missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired registration token. Please verify phone OTP again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

# --- Cryptographic OTP Security ---
def hash_otp(target: str, code: str) -> str:
    """
    Computes a cryptographic HMAC-SHA256 digest of the OTP using server SECRET_KEY (pepper)
    and target phone number as part of the message to prevent rainbow-table and precomputation attacks.
    """
    message = f"{target}:{code}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()

def verify_otp_hash(target: str, code: str, stored_hash: str) -> bool:
    """
    Constant-time comparison of computed OTP HMAC hash against stored hash.
    Protects against timing attacks.
    """
    if not stored_hash or not code:
        return False
    computed_hash = hash_otp(target, code)
    return secrets.compare_digest(computed_hash, stored_hash)

def generate_secure_otp() -> str:
    """
    Generates a cryptographically secure 6-digit OTP using secrets module.
    """
    return f"{secrets.randbelow(900000) + 100000}"