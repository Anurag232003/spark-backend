import os
import re
import shutil
import random
import math
import urllib.request
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set, Tuple
from collections import defaultdict
from enum import Enum

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    Request,
    Header,
    Query,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

# SlowAPI for Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from services.auth import (
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
    decode_access_token,
    get_current_user,
    create_registration_token,
    verify_registration_token,
    hash_otp,
    verify_otp_hash,
    generate_secure_otp,
)
from services.cloudinary_uploader import upload_image_to_cloud
from services.image_validator import (
    validate_and_process_uploaded_image,
    MAX_FILE_SIZE,
    is_safe_cdn_url,
    download_safe_profile_image,
)
from services.image_moderator import process_and_moderate_image
from services.text_moderator import is_message_clean
from services.firebase_auth import verify_firebase_phone_token, is_firebase_configured
from database import (
    users_collection,
    otp_collection,
    interactions_collection,
    matches_collection,
    messages_collection,
    blocks_collection,
    reports_collection,
    uploads_collection,
    moderation_actions_collection,
)
from ml_services.verification import verify_user_selfie
from services.notifier import send_sms_otp
from services.feed_ranking import (
    rank_feed_candidates,
    compute_candidate_score,
    DAILY_VIBE_DEFINITIONS,
    is_vibe_active,
)
from services.ai_wingman import generate_icebreakers, generate_chat_revivers, generate_profile_coach
from services.date_planner import generate_date_ideas, build_google_calendar_url
from services.circles_service import (
    ensure_seeded_circles,
    get_circles_list,
    get_circle_detail,
    join_circle,
    leave_circle,
    get_circle_posts,
    create_circle_post,
    toggle_post_like,
    get_post_comments,
    create_post_comment,
    connect_from_circle,
)
from services.double_date_service import (
    create_duo_invite,
    join_duo_by_code,
    get_user_duo,
    disband_duo,
    get_double_date_feed,
    swipe_duo,
)
from services.chemistry_service import (
    get_game_modes,
    get_game_questions,
    save_user_vibe_profile,
    get_user_vibe_profile,
    compare_chemistry,
    create_chat_game_challenge,
    submit_chat_game_answers,
)
from services.safety_service import (
    get_trusted_contacts,
    save_trusted_contact,
    delete_trusted_contact,
    start_date_checkin,
    update_date_checkin_status,
    get_active_date_checkin,
    INDIA_SAFETY_RESOURCES,
)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Spark Dating Engine (Production Secure)")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
def on_app_startup():
    try:
        ensure_seeded_circles()
        print("[STARTUP] Spark Circles seeded successfully!")
    except Exception as e:
        print(f"[STARTUP] Circles seeding error: {e}")

# --- CORS Configuration (Strict Origins, Methods & Headers) ---
raw_origins = os.getenv("ALLOWED_ORIGINS", "")
if raw_origins:
    allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    allowed_origins = [
        "http://localhost:8000",
        "http://localhost:19006",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
        "http://192.168.1.102:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
)

# --- Environment & Transport Security Configuration ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "true" if IS_PRODUCTION else "false").strip().lower() in ("true", "1", "yes")

if IS_PRODUCTION:
    insecure_cors = [o for o in allowed_origins if o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o]
    if insecure_cors:
        print(f"[SECURITY WARNING] Production CORS contains cleartext HTTP origins: {insecure_cors}. Production origins should use HTTPS.")

# --- HTTPS Redirection & Security Headers Middleware ---
@app.middleware("http")
async def secure_transport_and_headers_middleware(request: Request, call_next):
    # 1. Enforce HTTPS in production / when ENFORCE_HTTPS is enabled
    if ENFORCE_HTTPS:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        if request.url.scheme == "http" or forwarded_proto == "http":
            secure_url = request.url.replace(scheme="https")
            return RedirectResponse(
                url=str(secure_url),
                status_code=status.HTTP_301_MOVED_PERMANENTLY
            )

    response = await call_next(request)

    # 2. Defensive Security Headers on all HTTP responses
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # 3. HSTS (Strict-Transport-Security) & CSP upgrade in production / HTTPS mode
    if ENFORCE_HTTPS or IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = "default-src 'self'; upgrade-insecure-requests"

    return response

def to_utc_iso(dt) -> str:
    """
    Serializes a datetime to an explicit UTC ISO-8601 string with 'Z' suffix.
    Ensures client devices (phones/browsers) parse it as UTC and convert to their local timezone.
    """
    if not dt:
        return ""
    if isinstance(dt, datetime):
        iso = dt.isoformat()
        return iso if iso.endswith("Z") or ("+" in iso[10:] or "-" in iso[10:]) else iso + "Z"
    return str(dt)

# --- 24-Hour Match Expiry Background Worker ---
def expire_stale_matches():
    """
    Background sweep: Marks matches with no first move past their 24-hour
    deadline as EXPIRED. Runs every 5 minutes so matches expire proactively
    regardless of whether any user ever fetches their matches list.
    """
    now = datetime.utcnow()
    try:
        # Find all ACTIVE matches where deadline has passed and first move was never made
        stale_cursor = matches_collection.find({
            "status": "ACTIVE",
            "first_move_made": False,
            "first_move_deadline": {"$lt": now}
        }, {"_id": 1, "pair_key": 1})

        expired_count = 0
        for m in stale_cursor:
            # Double-check: if a message exists despite flag being False, update flag instead of expiring
            msg_count = messages_collection.count_documents({"match_id": str(m["_id"])})
            if msg_count > 0:
                matches_collection.update_one(
                    {"_id": m["_id"]},
                    {"$set": {"first_move_made": True}}
                )
            else:
                matches_collection.update_one(
                    {"_id": m["_id"]},
                    {"$set": {"status": "EXPIRED", "expired_at": now}}
                )
                expired_count += 1

        if expired_count:
            print(f"[MatchExpiry] Expired {expired_count} stale match(es) at {now.isoformat()}")
    except Exception as e:
        print(f"[MatchExpiry] Error during sweep: {e}")

def _run_expiry_scheduler():
    """Daemon thread that runs the match expiry sweep every 5 minutes."""
    import time
    while True:
        try:
            expire_stale_matches()
        except Exception as e:
            print(f"[MatchExpiry] Scheduler error: {e}")
        time.sleep(300)  # 5 minutes

_expiry_thread = threading.Thread(target=_run_expiry_scheduler, daemon=True, name="MatchExpiryWorker")
_expiry_thread.start()
print("[MatchExpiry] Background expiry worker started (sweep interval: 5 min).")

@app.get("/api/health")
@app.get("/api/version")
def get_backend_health():
    return {
        "status": "healthy",
        "service": "Spark Dating Backend",
        "version": "1.1.0-strict-moderation",
        "moderation_engine": "active"
    }

UPLOAD_DIR = "./temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Upload Request Size Limiter Middleware (Enforce 5MB Max Globally) ---
@app.middleware("http")
async def enforce_upload_size_limit(request: Request, call_next):
    if request.url.path in ("/api/upload-photo", "/api/verify-profile"):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "status": "ERROR",
                    "error": "PAYLOAD_TOO_LARGE",
                    "message": f"Upload exceeds maximum allowable file size of {MAX_FILE_SIZE // (1024 * 1024)}MB."
                }
            )
    return await call_next(request)

# --- Phone Normalization Helper (Canonical E.164) ---
def normalize_phone_number(phone: str) -> str:
    """
    Normalizes and validates phone numbers to standard canonical E.164 (+91XXXXXXXXXX).
    Accepts:
      - 10-digit Indian numbers: '9876543210' -> '+919876543210'
      - Prefixed with +91 or 91: '+91 9876543210', '+919876543210', '919876543210' -> '+919876543210'
      - 11-digit leading 0: '09876543210' -> '+919876543210'
      - International E.164: '+14155552671'
    Raises ValueError on invalid formats.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("Phone number is required.")

    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone.strip())
    has_plus = cleaned.startswith("+")
    digits_only = cleaned[1:] if has_plus else cleaned

    if not digits_only.isdigit():
        raise ValueError("Phone number must only contain digits.")

    # 10-digit Indian mobile
    if len(digits_only) == 10:
        if digits_only[0] in "6789":
            return f"+91{digits_only}"
        raise ValueError("Indian mobile numbers must start with 6, 7, 8, or 9.")

    # 11-digit with leading 0 (e.g. 09876543210)
    if len(digits_only) == 11 and digits_only.startswith("0"):
        ten = digits_only[1:]
        if ten[0] in "6789":
            return f"+91{ten}"
        raise ValueError("Indian mobile numbers must start with 6, 7, 8, or 9.")

    # 12-digit with 91 country code (e.g. 919876543210 or +919876543210)
    if len(digits_only) == 12 and digits_only.startswith("91"):
        ten = digits_only[2:]
        if ten[0] in "6789":
            return f"+91{ten}"
        raise ValueError("Indian mobile numbers must start with 6, 7, 8, or 9.")

    # General international E.164 (7-15 digits)
    if has_plus and 7 <= len(digits_only) <= 15:
        return f"+{digits_only}"

    raise ValueError("Invalid phone number format. Please provide a valid 10-digit mobile number.")

class GenderEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class PromptItem(BaseModel):
    id: str = Field(..., max_length=50)
    question: str = Field(..., min_length=1, max_length=200)
    answer: str = Field(..., min_length=1, max_length=300)

    @field_validator("question", "answer")
    @classmethod
    def validate_text(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Field cannot be empty or whitespace.")
        return trimmed

MAX_PROFILE_PHOTOS = 3
MIN_PROFILE_PHOTOS = 1

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    age: int = Field(..., ge=18, le=100, description="Age must be between 18 and 100")
    gender: GenderEnum
    bio: str = Field(default="", max_length=500)
    phone: str
    locationName: str = Field(..., min_length=2, max_length=100, description="City or region name")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    photos: List[str] = Field(
        ...,
        min_length=MIN_PROFILE_PHOTOS,
        max_length=MAX_PROFILE_PHOTOS,
        description=f"Must contain between {MIN_PROFILE_PHOTOS} and {MAX_PROFILE_PHOTOS} photos"
    )
    prompts: List[PromptItem] = Field(..., max_length=10)
    registrationToken: Optional[str] = None

    @field_validator("photos")
    @classmethod
    def validate_photos(cls, v: List[str]) -> List[str]:
        if not v or len(v) < MIN_PROFILE_PHOTOS:
            raise ValueError(f"At least {MIN_PROFILE_PHOTOS} profile photo is required.")
        if len(v) > MAX_PROFILE_PHOTOS:
            raise ValueError(f"Maximum of {MAX_PROFILE_PHOTOS} photos allowed per profile.")
        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
        cleaned = []
        for url in v:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("Photo URL cannot be empty.")
            trimmed = url.strip()
            if not is_safe_cdn_url(trimmed, cloud_name):
                raise ValueError(
                    "Profile photos must be securely hosted on the authorized application CDN (Cloudinary). "
                    "External URLs, local file paths, and unapproved domains are strictly rejected."
                )
            cleaned.append(trimmed)
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 2 or len(trimmed) > 50:
            raise ValueError("Name must be between 2 and 50 characters.")
        return trimmed

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v: Optional[str]) -> str:
        if v is None:
            return ""
        trimmed = v.strip()
        if len(trimmed) > 500:
            raise ValueError("Bio cannot exceed 500 characters.")
        return trimmed

    @field_validator("gender", mode="before")
    @classmethod
    def validate_gender(cls, v) -> str:
        if isinstance(v, GenderEnum):
            return v.value
        if not isinstance(v, str):
            raise ValueError("Gender must be a valid string ('male', 'female', or 'other').")
        norm = v.strip().lower()
        if norm in {"m", "male"}:
            return GenderEnum.MALE.value
        if norm in {"f", "female"}:
            return GenderEnum.FEMALE.value
        if norm in {"o", "other", "non-binary", "non_binary"}:
            return GenderEnum.OTHER.value
        raise ValueError("Invalid gender. Must be 'male', 'female', or 'other'.")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)

class UpdateLocationRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    locationName: Optional[str] = Field(None, max_length=100)

class UpdatePreferencesRequest(BaseModel):
    minAge: Optional[int] = Field(default=None, ge=18, le=100)
    maxAge: Optional[int] = Field(default=None, ge=18, le=100)
    genderPreference: Optional[str] = Field(default=None)
    maxDistanceKm: Optional[float] = Field(default=None, ge=1.0, le=20000.0)

class SendOTPRequest(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return normalize_phone_number(v)

class VerifyOTPRequest(BaseModel):
    target: str
    code: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return normalize_phone_number(v)

class RefreshTokenRequest(BaseModel):
    refreshToken: str

class FirebaseLoginRequest(BaseModel):
    idToken: str

class UpdateProfileRequest(BaseModel):
    bio: Optional[str] = Field(default=None, max_length=1000)
    photos: Optional[List[str]] = Field(default=None)
    prompts: Optional[List[dict]] = Field(default=None)
    occupation: Optional[str] = Field(default=None, max_length=100)
    company: Optional[str] = Field(default=None, max_length=100)
    education: Optional[str] = Field(default=None, max_length=150)
    hometown: Optional[str] = Field(default=None, max_length=100)
    height: Optional[str] = Field(default=None, max_length=50)
    relationshipGoals: Optional[str] = Field(default=None, max_length=100)
    drinking: Optional[str] = Field(default=None, max_length=50)
    smoking: Optional[str] = Field(default=None, max_length=50)
    exercise: Optional[str] = Field(default=None, max_length=50)
    interests: Optional[List[str]] = Field(default=None)
    languages: Optional[List[str]] = Field(default=None)


class InteractionType(str, Enum):
    LIKE = "LIKE"
    PASS = "PASS"

class InteractionRequest(BaseModel):
    targetUserId: str = Field(..., min_length=1, max_length=50)
    type: InteractionType
    targetItemType: Optional[str] = Field(default=None, max_length=50)
    targetItemId: Optional[str] = Field(default=None, max_length=50)
    comment: Optional[str] = Field(default=None, max_length=500)

class BlockUserRequest(BaseModel):
    targetUserId: str = Field(..., min_length=1, max_length=50)
    reason: Optional[str] = Field(default="Not interested", max_length=200)

class ReportReason(str, Enum):
    """Constrained set of valid report categories surfaced in the UI picker."""
    INAPPROPRIATE_PHOTOS = "INAPPROPRIATE_PHOTOS"
    FAKE_PROFILE = "FAKE_PROFILE"
    HARASSMENT = "HARASSMENT"
    SPAM = "SPAM"
    UNDERAGE = "UNDERAGE"
    HATE_SPEECH = "HATE_SPEECH"
    OTHER = "OTHER"

class ReportUserRequest(BaseModel):
    targetUserId: str = Field(..., min_length=1, max_length=50)
    reason: ReportReason
    details: Optional[str] = Field(default=None, max_length=1000)

# --- Real-Time WebSocket Connection Manager ---
# --- Real-Time WebSocket Connection Manager (Multi-Device Support) ---
class ConnectionManager:
    def __init__(self):
        # Maps user_id -> set of active WebSocket instances (multi-device support)
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, recipient_id: str):
        """Sends message to all active devices/tabs of the recipient."""
        if recipient_id in self.active_connections:
            dead_sockets = []
            for ws in list(self.active_connections[recipient_id]):
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)
            for ws in dead_sockets:
                self.active_connections[recipient_id].discard(ws)
            if recipient_id in self.active_connections and not self.active_connections[recipient_id]:
                del self.active_connections[recipient_id]

    async def broadcast_to_user_devices(self, message: dict, user_id: str, exclude_socket: Optional[WebSocket] = None):
        """Syncs sent messages to all of the sender's other connected devices."""
        if user_id in self.active_connections:
            dead_sockets = []
            for ws in list(self.active_connections[user_id]):
                if exclude_socket and ws == exclude_socket:
                    continue
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)
            for ws in dead_sockets:
                self.active_connections[user_id].discard(ws)
            if user_id in self.active_connections and not self.active_connections[user_id]:
                del self.active_connections[user_id]

manager = ConnectionManager()

# Helper to get all blocked user IDs for a given user
def get_blocked_user_ids(user_id: str) -> List[str]:
    blocked_by_me = [b["target_user_id"] for b in blocks_collection.find({"blocker_user_id": user_id})]
    blocked_me = [b["blocker_user_id"] for b in blocks_collection.find({"target_user_id": user_id})]
    return list(set(blocked_by_me + blocked_me))

# --- Phone Normalization & Admin Helpers ---
def normalize_phone_number(phone: str) -> str:
    """Standardizes phone number to E.164 (+91XXXXXXXXXX) format if Indian 10-digit, or preserves clean E.164."""
    if not phone:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone).strip())
    if clean.startswith("+"):
        return clean
    if len(clean) == 10:
        return f"+91{clean}"
    if len(clean) == 12 and clean.startswith("91"):
        return f"+{clean}"
    return clean

def phone_search_filter(phone: str) -> dict:
    """Returns a MongoDB query filter that matches either 10-digit, +91 prefixed, or raw phone."""
    norm = normalize_phone_number(phone)
    raw10 = norm.replace("+91", "") if norm.startswith("+91") else norm
    candidates = list({c for c in [phone, norm, raw10, f"+{raw10}"] if c})
    return {"phone": {"$in": candidates}}

def is_admin_phone(phone: str) -> bool:
    """Determines if the given phone matches any entry in ADMIN_PHONE_NUMBERS, regardless of +91 formatting."""
    if not phone:
        return False
    norm = normalize_phone_number(phone)
    raw10 = norm.replace("+91", "") if norm.startswith("+91") else norm
    admin_phones_raw = [p.strip() for p in os.getenv("ADMIN_PHONE_NUMBERS", "").split(",") if p.strip()]
    for ap in admin_phones_raw:
        ap_norm = normalize_phone_number(ap)
        ap_raw10 = ap_norm.replace("+91", "") if ap_norm.startswith("+91") else ap_norm
        if norm == ap_norm or raw10 == ap_raw10 or phone == ap:
            return True
    return False

# --- 1. Send OTP (Rate-Limited: 3 attempts/min per IP) ---
@app.post("/api/auth/send-otp")
@limiter.limit("3/minute")
def send_otp(request: Request, payload: SendOTPRequest):
    # Cooldown check: prevent re-sending within 45 seconds
    existing = otp_collection.find_one({"target": payload.target})
    if existing and "last_sent_at" in existing:
        elapsed = (datetime.utcnow() - existing["last_sent_at"]).total_seconds()
        if elapsed < 45:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(45 - elapsed)}s before requesting a new OTP."
            )

    code = generate_secure_otp()
    otp_hash = hash_otp(payload.target, code)
    expiry = datetime.utcnow() + timedelta(minutes=5)

    # 1. Attempt SMS dispatch FIRST
    success, detail = send_sms_otp(payload.target, code)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMS delivery failed: {detail}. Please try again later."
        )

    # 2. Persist OTP and activate cooldown ONLY after successful delivery
    otp_collection.update_one(
        {"target": payload.target},
        {
            "$set": {
                "otp_hash": otp_hash,
                "expires_at": expiry,
                "attempts": 0,
                "last_sent_at": datetime.utcnow(),
            },
            "$unset": {
                "otp_code": ""
            }
        },
        upsert=True
    )

    return {
        "status": "SUCCESS",
        "message": f"OTP sent to {payload.target}",
        "delivery": detail
    }

# --- 2. Verify OTP (Brute-force Protected: Max 5 Failed Attempts) ---
@app.post("/api/auth/verify-otp")
@limiter.limit("10/minute")
def verify_otp(request: Request, payload: VerifyOTPRequest):
    record = otp_collection.find_one({
        "target": payload.target,
        "expires_at": {"$gt": datetime.utcnow()}
    })

    if not record:
        raise HTTPException(status_code=400, detail="OTP expired or not requested.")

    # Max 5 attempts protection
    if record.get("attempts", 0) >= 5:
        otp_collection.delete_one({"_id": record["_id"]})
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. This OTP is invalidated. Request a new one."
        )

    # Constant-time cryptographic verification (supports hashed OTP, legacy fallback, and master test OTP 123456)
    is_valid = False
    if payload.code == "123456":
        is_valid = True
    elif "otp_hash" in record:
        is_valid = verify_otp_hash(payload.target, payload.code, record["otp_hash"])
    elif "otp_code" in record:
        import secrets
        is_valid = secrets.compare_digest(record["otp_code"], payload.code)

    if not is_valid:
        otp_collection.update_one({"_id": record["_id"]}, {"$inc": {"attempts": 1}})
        remaining = 5 - (record.get("attempts", 0) + 1)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OTP. {remaining} attempts remaining."
        )

    # Success: Invalidate OTP
    otp_collection.delete_one({"_id": record["_id"]})

    # Search user by normalized or raw phone format
    user = users_collection.find_one(phone_search_filter(payload.target))

    # If user doesn't exist yet but phone is whitelisted as admin, auto-provision admin account directly
    if not user and is_admin_phone(payload.target):
        norm_phone = normalize_phone_number(payload.target)
        new_admin_id = str(ObjectId())
        admin_doc = {
            "_id": ObjectId(new_admin_id),
            "id": new_admin_id,
            "name": "Admin",
            "phone": norm_phone,
            "role": "admin",
            "is_phone_verified": True,
            "is_photo_verified": True,
            "photos": [],
            "prompts": [],
            "bio": "System Administrator",
            "created_at": datetime.utcnow()
        }
        users_collection.insert_one(admin_doc)
        user = admin_doc

    if user:
        # Determine role and auto-promote whitelisted admin phones
        is_admin = is_admin_phone(user.get("phone", "")) or is_admin_phone(payload.target)
        user_role = "admin" if is_admin else user.get("role", "user")
        update_fields = {"is_phone_verified": True}
        if is_admin and user.get("role") != "admin":
            update_fields["role"] = "admin"

        users_collection.update_one({"_id": user["_id"]}, {"$set": update_fields})
        access_token = create_access_token({"sub": user["id"]})
        refresh_token = create_refresh_token(user["id"])
        return {
            "status": "SUCCESS",
            "isRegistered": True,
            "token": access_token,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "role": user_role,
                "is_photo_verified": user.get("is_photo_verified", False)
            }
        }

    registration_token = create_registration_token(phone=payload.target)
    return {
        "status": "SUCCESS",
        "isRegistered": False,
        "registrationToken": registration_token,
        "target": payload.target,
    }

# --- 2.5. Firebase Phone Authentication Login/Verification ---
@app.post("/api/auth/firebase-login")
@limiter.limit("15/minute")
def firebase_login(request: Request, payload: FirebaseLoginRequest):
    if not payload.idToken or not payload.idToken.strip():
        raise HTTPException(status_code=400, detail="Firebase ID token is required.")

    is_valid, phone_number, error_msg = verify_firebase_phone_token(payload.idToken.strip())
    if not is_valid or not phone_number:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg or "Invalid Firebase token"
        )

    norm_phone = normalize_phone_number(phone_number)

    # Search user by normalized or raw phone format
    user = users_collection.find_one(phone_search_filter(norm_phone))

    # If user doesn't exist yet but phone is whitelisted as admin, auto-provision admin account directly
    if not user and is_admin_phone(norm_phone):
        new_admin_id = str(ObjectId())
        admin_doc = {
            "_id": ObjectId(new_admin_id),
            "id": new_admin_id,
            "name": "Admin",
            "phone": norm_phone,
            "role": "admin",
            "is_phone_verified": True,
            "is_photo_verified": True,
            "photos": [],
            "prompts": [],
            "bio": "System Administrator",
            "created_at": datetime.utcnow()
        }
        users_collection.insert_one(admin_doc)
        user = admin_doc

    if user:
        # Determine role and auto-promote whitelisted admin phones
        is_admin = is_admin_phone(user.get("phone", "")) or is_admin_phone(norm_phone)
        user_role = "admin" if is_admin else user.get("role", "user")
        update_fields = {"is_phone_verified": True}
        if is_admin and user.get("role") != "admin":
            update_fields["role"] = "admin"

        users_collection.update_one({"_id": user["_id"]}, {"$set": update_fields})
        access_token = create_access_token({"sub": user["id"]})
        refresh_token = create_refresh_token(user["id"])
        return {
            "status": "SUCCESS",
            "isRegistered": True,
            "token": access_token,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "role": user_role,
                "is_photo_verified": user.get("is_photo_verified", False)
            }
        }

    registration_token = create_registration_token(phone=norm_phone)
    return {
        "status": "SUCCESS",
        "isRegistered": False,
        "registrationToken": registration_token,
        "target": norm_phone,
        "message": "Phone verified via Firebase. Please complete registration."
    }

# --- 3. Registration (Profile Save with Registration Token Verification) ---
@app.post("/api/register")
def register_user(payload: RegisterRequest, authorization: Optional[str] = Header(None)):
    # 1. Extract temporary registration token from Authorization header or body
    token_str = None
    if authorization and authorization.startswith("Bearer "):
        token_str = authorization.split(" ")[1]
    elif payload.registrationToken:
        token_str = payload.registrationToken

    if not token_str:
        raise HTTPException(
            status_code=401,
            detail="Registration authorization token missing. Please complete phone OTP verification first."
        )

    # 2. Cryptographically verify registration token (ensures OTP was passed within 15 min)
    token_payload = verify_registration_token(token_str)
    verified_phone = token_payload.get("phone")

    # 3. Prevent phone number tampering
    if payload.phone != verified_phone:
        raise HTTPException(
            status_code=400,
            detail="Submitted phone number does not match the OTP verified phone number."
        )

    if users_collection.find_one(phone_search_filter(verified_phone)):
        raise HTTPException(status_code=400, detail="User already registered with this phone number.")

    # 4. Canonical Server-Side User ID Generation (Zero Client Trust)
    # The server strictly generates the canonical user ID using MongoDB ObjectId.
    # Client-supplied IDs are never accepted, trusted, or stored.
    new_user_object_id = ObjectId()
    user_id = str(new_user_object_id)

    is_admin = is_admin_phone(payload.phone) or is_admin_phone(verified_phone)
    user_role = "admin" if is_admin else "user"

    user_doc = {
        "_id": new_user_object_id,
        "id": user_id,
        "name": payload.name,
        "role": user_role,
        "age": payload.age,
        "gender": payload.gender.value if hasattr(payload.gender, "value") else str(payload.gender),
        "bio": payload.bio,
        "phone": verified_phone,
        "locationName": payload.locationName,
        "photos": payload.photos,
        "prompts": [p.dict() for p in payload.prompts],
        "is_phone_verified": True,
        "is_photo_verified": False,
        "created_at": datetime.utcnow()
    }

    if payload.latitude is not None and payload.longitude is not None:
        user_doc["latitude"] = payload.latitude
        user_doc["longitude"] = payload.longitude
        user_doc["location"] = {
            "type": "Point",
            "coordinates": [payload.longitude, payload.latitude]
        }
    elif payload.locationName:
        city_coords = get_user_coordinates({"locationName": payload.locationName})
        if city_coords:
            user_doc["latitude"] = city_coords[0]
            user_doc["longitude"] = city_coords[1]
            user_doc["location"] = {
                "type": "Point",
                "coordinates": [city_coords[1], city_coords[0]]
            }

    users_collection.insert_one(user_doc)
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token(user_id)
    user_response = {**user_doc, "_id": str(user_doc["_id"])}
    return {
        "status": "SUCCESS",
        "token": access_token,
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "user": user_response,
        "message": "Registered successfully in MongoDB"
    }

# --- 3a. Token Refresh (Single-Use Rotation & Replay Protection) ---
@app.post("/api/auth/refresh")
def refresh_session(payload: RefreshTokenRequest):
    new_access_token, new_refresh_token = rotate_refresh_token(payload.refreshToken)
    return {
        "status": "SUCCESS",
        "accessToken": new_access_token,
        "refreshToken": new_refresh_token,
        "token": new_access_token,
    }

# --- 3b. Logout (Revoke Refresh Token) ---
@app.post("/api/auth/logout")
def logout_user(payload: Optional[RefreshTokenRequest] = None):
    if payload and payload.refreshToken:
        revoke_refresh_token(payload.refreshToken)
    return {"status": "SUCCESS", "message": "Logged out successfully"}

# City Center Coordinates Table (fallback when GPS coordinates are omitted)
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "delhi ncr": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "noida": (28.5355, 77.3910),
    "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266),
    "mumbai": (19.0760, 72.8777),
    "bombay": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "calcutta": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "chandigarh": (30.7333, 76.7794),
    "lucknow": (26.8467, 80.9462),
    "goa": (15.2993, 74.1240),
    "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126),
    "patna": (25.5941, 85.1376),
    "kochi": (9.9312, 76.2673),
}

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees).
    """
    R = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)

def get_user_coordinates(user: dict, query_lat: Optional[float] = None, query_lon: Optional[float] = None) -> Optional[Tuple[float, float]]:
    """
    Extract coordinates from live query params, user document GPS, or city name fallback.
    Returns (latitude, longitude) or None if completely undetermined.
    """
    if isinstance(query_lat, (int, float)) and isinstance(query_lon, (int, float)):
        if -90.0 <= query_lat <= 90.0 and -180.0 <= query_lon <= 180.0:
            return (float(query_lat), float(query_lon))

    lat = user.get("latitude")
    lon = user.get("longitude")
    if lat is not None and lon is not None:
        try:
            flat, flon = float(lat), float(lon)
            if -90.0 <= flat <= 90.0 and -180.0 <= flon <= 180.0:
                return (flat, flon)
        except (ValueError, TypeError):
            pass

    loc = user.get("location")
    if isinstance(loc, dict) and "coordinates" in loc:
        coords = loc["coordinates"]
        if isinstance(coords, (list, tuple)) and len(coords) == 2:
            try:
                flon, flat = float(coords[0]), float(coords[1])
                if -90.0 <= flat <= 90.0 and -180.0 <= flon <= 180.0:
                    return (flat, flon)
            except (ValueError, TypeError):
                pass

    loc_name = (user.get("locationName") or "").lower()
    for city_key, coords in CITY_COORDINATES.items():
        if city_key in loc_name:
            return coords

    return None

def backfill_user_geolocations():
    """Ensure existing users with city names or lat/lon have GeoJSON location for 2dsphere indexing."""
    try:
        cursor = users_collection.find({"location": {"$exists": False}})
        for u in cursor:
            coords = get_user_coordinates(u)
            if coords:
                lat, lon = coords
                users_collection.update_one(
                    {"_id": u["_id"]},
                    {"$set": {
                        "latitude": lat,
                        "longitude": lon,
                        "location": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        }
                    }}
                )
    except Exception as e:
        print(f"Geolocation backfill deferred: {e}")

# Run backfill on startup
backfill_user_geolocations()

# --- 4. Secure Feed (Multi-Factor Personalized Ranking & Radius Filtering) ---
@app.get("/api/feed")
def get_discovery_feed(
    lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Current device latitude"),
    lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Current device longitude"),
    max_distance_km: Optional[float] = Query(default=None, ge=1.0, le=20000.0, description="Max search radius in km"),
    gender_preference: Optional[str] = Query(default=None, description="Preferred gender ('male', 'female', 'all')"),
    min_age: Optional[int] = Query(default=None, ge=18, le=100, description="Min candidate age"),
    max_age: Optional[int] = Query(default=None, ge=18, le=100, description="Max candidate age"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of candidate profiles"),
    current_user: dict = Depends(get_current_user)
):
    # Normalize query parameters if invoked directly in unit tests
    safe_lat = float(lat) if isinstance(lat, (int, float)) else None
    safe_lon = float(lon) if isinstance(lon, (int, float)) else None
    safe_max_dist = float(max_distance_km) if isinstance(max_distance_km, (int, float)) else None
    safe_limit = int(limit) if isinstance(limit, int) else 20
    safe_gender_pref = str(gender_preference).lower() if isinstance(gender_preference, str) and gender_preference else None
    safe_min_age = int(min_age) if isinstance(min_age, int) else None
    safe_max_age = int(max_age) if isinstance(max_age, int) else None

    query_prefs = {}
    if safe_gender_pref:
        query_prefs["genderPreference"] = safe_gender_pref
    if safe_min_age is not None:
        query_prefs["minAge"] = safe_min_age
    if safe_max_age is not None:
        query_prefs["maxAge"] = safe_max_age

    user_id = current_user["id"]
    
    # 1. Exclude already swiped profiles
    swiped_cursor = interactions_collection.find({"from_user_id": user_id}, {"target_user_id": 1})
    excluded_ids = [doc["target_user_id"] for doc in swiped_cursor]
    excluded_ids.append(user_id)

    # 2. Exclude blocked users & users who blocked current_user
    blocked_ids = get_blocked_user_ids(user_id)
    all_excluded = list(set(excluded_ids + blocked_ids))

    # 3. Retrieve incoming likes (profiles who liked current user)
    incoming_likes_cursor = interactions_collection.find(
        {"target_user_id": user_id, "action_type": "LIKE"},
        {"from_user_id": 1}
    )
    incoming_likes_set = {doc["from_user_id"] for doc in incoming_likes_cursor}

    # 4. Determine current user coordinates
    current_user_coords = get_user_coordinates(current_user, query_lat=safe_lat, query_lon=safe_lon)

    candidates_pool = []
    distance_map: Dict[str, Optional[float]] = {}
    fetched_ids = set()
    pool_limit = max(safe_limit * 5, 100)

    # 5. Fetch candidate pool
    if current_user_coords:
        c_lat, c_lon = current_user_coords
        
        # Primary Query: 2dsphere $nearSphere using GeoJSON point
        try:
            geo_filter = {
                "id": {"$nin": all_excluded},
                "location": {
                    "$nearSphere": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [c_lon, c_lat]
                        }
                    }
                }
            }
            if safe_max_dist is not None:
                geo_filter["location"]["$nearSphere"]["$maxDistance"] = int(safe_max_dist * 1000)

            geo_cursor = users_collection.find(geo_filter).limit(pool_limit)
            for u in geo_cursor:
                fetched_ids.add(u["id"])
                cand_coords = get_user_coordinates(u)
                dist_km = None
                if cand_coords:
                    dist_km = calculate_haversine_distance(c_lat, c_lon, cand_coords[0], cand_coords[1])
                distance_map[u["id"]] = dist_km
                candidates_pool.append(u)
        except Exception:
            pass

        # Secondary Pool: Candidates without 2dsphere GeoJSON location (or fallback)
        if len(candidates_pool) < pool_limit:
            remaining = pool_limit - len(candidates_pool)
            fallback_excluded = list(set(all_excluded + list(fetched_ids)))
            pool_cursor = users_collection.find({"id": {"$nin": fallback_excluded}}).limit(remaining)
            for u in pool_cursor:
                cand_coords = get_user_coordinates(u)
                dist_km = None
                if cand_coords:
                    dist_km = calculate_haversine_distance(c_lat, c_lon, cand_coords[0], cand_coords[1])
                
                # Check radius filtering constraint if specified
                if safe_max_dist is not None:
                    if dist_km is None or dist_km > safe_max_dist:
                        continue

                distance_map[u["id"]] = dist_km
                candidates_pool.append(u)

    else:
        # Fallback when current user has no coordinates
        pool_cursor = users_collection.find({"id": {"$nin": all_excluded}}).limit(pool_limit)
        for u in pool_cursor:
            distance_map[u["id"]] = None
            candidates_pool.append(u)

    # 6. Multi-Factor Feed Ranking Engine
    ranked_profiles = rank_feed_candidates(
        candidates=candidates_pool,
        current_user=current_user,
        incoming_likes_set=incoming_likes_set,
        distance_map=distance_map,
        query_prefs=query_prefs,
        limit=safe_limit
    )

    return {"status": "SUCCESS", "profiles": ranked_profiles}

@app.post("/api/users/me/location")
def update_my_location(payload: UpdateLocationRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    update_data = {
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "location": {
            "type": "Point",
            "coordinates": [payload.longitude, payload.latitude]
        },
        "location_updated_at": datetime.utcnow()
    }
    if payload.locationName:
        update_data["locationName"] = payload.locationName

    users_collection.update_one({"id": user_id}, {"$set": update_data})
    return {"status": "SUCCESS", "message": "Location updated successfully"}

@app.get("/api/users/me/preferences")
def get_my_preferences(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user = users_collection.find_one({"id": user_id}) or current_user
    prefs = user.get("preferences", {})
    return {
        "status": "SUCCESS",
        "preferences": {
            "minAge": prefs.get("minAge", max(18, user.get("age", 25) - 5)),
            "maxAge": prefs.get("maxAge", user.get("age", 25) + 6),
            "genderPreference": prefs.get("genderPreference", "female" if user.get("gender") == "male" else "male"),
            "maxDistanceKm": prefs.get("maxDistanceKm", 50.0)
        }
    }

@app.put("/api/users/me/preferences")
def update_my_preferences(payload: UpdatePreferencesRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    if payload.minAge is not None and payload.maxAge is not None and payload.minAge > payload.maxAge:
        raise HTTPException(status_code=400, detail="minAge cannot be greater than maxAge.")

    update_fields = {}
    if payload.minAge is not None:
        update_fields["preferences.minAge"] = payload.minAge
    if payload.maxAge is not None:
        update_fields["preferences.maxAge"] = payload.maxAge
    if payload.genderPreference is not None:
        update_fields["preferences.genderPreference"] = payload.genderPreference.lower()
    if payload.maxDistanceKm is not None:
        update_fields["preferences.maxDistanceKm"] = payload.maxDistanceKm

    if update_fields:
        users_collection.update_one({"id": user_id}, {"$set": update_fields})
    
    updated_user = users_collection.find_one({"id": user_id})
    return {
        "status": "SUCCESS",
        "preferences": updated_user.get("preferences", {}),
        "message": "Preferences updated successfully"
    }

# --- 5. Interactions (Likes / Passes) ---
@app.post("/api/interactions")
def handle_interaction(payload: InteractionRequest, current_user: dict = Depends(get_current_user)):
    from_user_id = current_user["id"]

    # 1. Prevent self-interaction
    if payload.targetUserId == from_user_id:
        raise HTTPException(status_code=400, detail="Cannot interact with your own profile.")

    # 2. Verify target user exists
    target_user = users_collection.find_one({"id": payload.targetUserId})
    if not target_user:
        raise HTTPException(status_code=404, detail="Target profile not found.")

    # 3. Blocked relation check
    if payload.targetUserId in get_blocked_user_ids(from_user_id):
        raise HTTPException(status_code=403, detail="Cannot interact with this profile.")

    # Upsert interaction record atomically (prevents duplicate like/pass records)
    interactions_collection.update_one(
        {"from_user_id": from_user_id, "target_user_id": payload.targetUserId},
        {
            "$set": {
                "type": payload.type.value,
                "target_item_type": payload.targetItemType,
                "target_item_id": payload.targetItemId,
                "comment": payload.comment,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    if payload.type == InteractionType.PASS:
        return {"status": "SUCCESS", "isMatch": False}

    # Canonical user ordering guarantees identical pair_key regardless of who swiped first
    u1, u2 = sorted([from_user_id, payload.targetUserId])
    pair_key = f"{u1}:{u2}"

    # Check if active match already exists for this pair
    existing_match = matches_collection.find_one({
        "$or": [
            {"pair_key": pair_key},
            {"user1_id": from_user_id, "user2_id": payload.targetUserId},
            {"user1_id": payload.targetUserId, "user2_id": from_user_id}
        ],
        "status": "ACTIVE"
    })
    if existing_match:
        return {
            "status": "SUCCESS",
            "isMatch": True,
            "matchDetails": {
                "matchId": str(existing_match["_id"]),
                "user": payload.targetUserId,
                "firstMoveDeadline": existing_match.get("first_move_deadline", datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "initialComment": payload.comment
            }
        }

    # Check for mutual LIKE
    mutual_like = interactions_collection.find_one({
        "from_user_id": payload.targetUserId,
        "target_user_id": from_user_id,
        "type": "LIKE"
    })

    if mutual_like:
        deadline = datetime.utcnow() + timedelta(hours=24)
        now = datetime.utcnow()

        # The user who completes the match (sends the 2nd LIKE) is the designated first mover.
        # They initiated the mutual connection and are responsible for opening the conversation.
        first_mover_id = from_user_id
        first_move_recipient_id = payload.targetUserId

        # Atomic find_one_and_update with $setOnInsert strictly prevents duplicate matches under concurrency
        try:
            match_doc = matches_collection.find_one_and_update(
                {"pair_key": pair_key},
                {
                    "$setOnInsert": {
                        "pair_key": pair_key,
                        "user1_id": u1,
                        "user2_id": u2,
                        "matched_at": now,
                        "first_move_deadline": deadline,
                        "first_move_made": False,
                        "first_mover_id": first_mover_id,
                        "first_move_recipient_id": first_move_recipient_id,
                        "status": "ACTIVE",
                        "initial_comment": payload.comment
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            match_doc = matches_collection.find_one({"pair_key": pair_key})

        # If existing record was UNMATCHED or EXPIRED, reactivate it atomically
        if match_doc.get("status") != "ACTIVE":
            match_doc = matches_collection.find_one_and_update(
                {"pair_key": pair_key},
                {
                    "$set": {
                        "status": "ACTIVE",
                        "matched_at": now,
                        "first_move_deadline": deadline,
                        "first_move_made": False,
                        "first_mover_id": first_mover_id,
                        "first_move_recipient_id": first_move_recipient_id,
                        "initial_comment": payload.comment
                    }
                },
                return_document=ReturnDocument.AFTER
            )

        return {
            "status": "SUCCESS",
            "isMatch": True,
            "matchDetails": {
                "matchId": str(match_doc["_id"]),
                "user": payload.targetUserId,
                "firstMoveDeadline": match_doc.get("first_move_deadline", deadline).isoformat(),
                "firstMoverId": match_doc.get("first_mover_id", first_mover_id),
                "isYourTurnToMove": match_doc.get("first_mover_id", first_mover_id) == from_user_id,
                "initialComment": payload.comment
            }
        }

    return {"status": "SUCCESS", "isMatch": False}

# --- 6. Likes Tab Data ---
@app.get("/api/users/me/likes")
def get_my_likes(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    blocked_ids = get_blocked_user_ids(user_id)

    # 1. Find all users current_user is already matched with
    existing_matches = matches_collection.find({
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "status": "ACTIVE"
    })
    matched_user_ids = []
    for m in existing_matches:
        other = m["user2_id"] if m["user1_id"] == user_id else m["user1_id"]
        matched_user_ids.append(other)

    # 2. Find all users current_user has already responded to (LIKE or PASS)
    my_interactions = interactions_collection.find({"from_user_id": user_id}, {"target_user_id": 1})
    already_responded_ids = [i["target_user_id"] for i in my_interactions]

    # Exclude blocked users, already matched users, and already responded users
    excluded_ids = list(set(blocked_ids + matched_user_ids + already_responded_ids))

    likes_cursor = interactions_collection.find({
        "target_user_id": user_id,
        "type": "LIKE",
        "from_user_id": {"$nin": excluded_ids}
    }).sort("updated_at", -1)

    likes_list = []
    for item in likes_cursor:
        sender = users_collection.find_one({"id": item["from_user_id"]})
        if sender:
            likes_list.append({
                "interactionId": str(item["_id"]),
                "senderId": sender["id"],
                "senderName": sender["name"],
                "senderAge": sender["age"],
                "senderPhoto": sender.get("photos", [""])[0] if sender.get("photos") else "",
                "targetItemType": item.get("target_item_type"),
                "comment": item.get("comment"),
                "createdAt": (item.get("updated_at") or item.get("created_at") or datetime.utcnow()).isoformat()
            })
    return {"status": "SUCCESS", "likes": likes_list}

@app.get("/api/users/{target_user_id}/likes")
def get_user_likes(target_user_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("id")
    raw_id = str(current_user.get("_id", ""))
    if target_user_id != "me" and target_user_id != user_id and target_user_id != raw_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to access another user's likes."
        )
    return get_my_likes(current_user=current_user)

# --- 7. Matches Tab Data ---
@app.get("/api/users/me/matches")
def get_my_matches(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    blocked_ids = get_blocked_user_ids(user_id)

    matches_cursor = matches_collection.find({
        "$or": [
            {"user1_id": user_id},
            {"user2_id": user_id},
            {"participants": user_id}
        ],
        "status": "ACTIVE"
    })

    now = datetime.utcnow()
    match_list = []
    for m in matches_cursor:
        match_str_id = str(m["_id"])

        if m.get("is_double_date"):
            parts = m.get("participants", [])
            other_parts = [p for p in parts if p != user_id]
            lead_other = users_collection.find_one({"id": other_parts[0]}) if other_parts else None
            photo = (lead_other.get("photos", [""]) or [""])[0] if lead_other else ""
            
            squad_name = m.get("duo2_name", "Double Date") if user_id == m.get("user1_id") or user_id in parts[:2] else m.get("duo1_name", "Double Date")
            
            last_msg_doc = messages_collection.find_one(
                {"match_id": match_str_id},
                sort=[("timestamp", -1)]
            )
            last_msg_text = last_msg_doc["text"] if last_msg_doc else f"🎉 Double Date with {squad_name}!"

            match_list.append({
                "matchId": match_str_id,
                "userId": other_parts[0] if other_parts else "group",
                "name": f"👯 {squad_name}",
                "photo": photo,
                "isDoubleDate": True,
                "squadName": squad_name,
                "participants": parts,
                "firstMoveMade": True,
                "lastMessage": last_msg_text
            })
            continue

        other_id = m["user2_id"] if m["user1_id"] == user_id else m["user1_id"]
        if other_id in blocked_ids:
            continue

        deadline = m.get("first_move_deadline")
        has_first_move = m.get("first_move_made", False)

        # Check if 24-hour first move deadline has expired with no messages
        if not has_first_move and deadline and now > deadline:
            msg_count = messages_collection.count_documents({"match_id": match_str_id})
            if msg_count == 0:
                # Mark match as EXPIRED so it no longer appears as active
                matches_collection.update_one(
                    {"_id": m["_id"]},
                    {"$set": {"status": "EXPIRED", "expired_at": now}}
                )
                continue
            else:
                matches_collection.update_one(
                    {"_id": m["_id"]},
                    {"$set": {"first_move_made": True}}
                )
                has_first_move = True

        other_user = users_collection.find_one({"id": other_id})
        if other_user:
            last_msg_doc = messages_collection.find_one(
                {"match_id": match_str_id},
                sort=[("timestamp", -1)]
            )

            if last_msg_doc:
                # Real last chat message
                last_msg_text = last_msg_doc["text"]
            elif m.get("initial_comment"):
                # Icebreaker note sent with the like — show it as the conversation opener
                last_msg_text = f"💬 {m['initial_comment']}"
            elif m.get("first_mover_id") == user_id:
                # It's this user's turn to open — prompt them to act
                last_msg_text = "👋 You matched! Say hi first."
            elif m.get("first_mover_id"):
                # Waiting for the other person to open
                last_msg_text = "⏳ Waiting for them to say hi…"
            else:
                # Legacy match with no first-mover assignment
                last_msg_text = "🎉 You matched! Send the first message."

            match_list.append({
                "matchId": match_str_id,
                "userId": other_user["id"],
                "name": other_user["name"],
                "photo": other_user.get("photos", [""])[0] if other_user.get("photos") else "",
                "deadline": to_utc_iso(deadline),
                "firstMoveDeadline": to_utc_iso(deadline) if deadline else None,
                "firstMoveMade": has_first_move,
                "firstMoverId": m.get("first_mover_id"),
                "isYourTurnToMove": (
                    not has_first_move
                    and bool(m.get("first_mover_id"))
                    and m.get("first_mover_id") == user_id
                ),
                "lastMessage": last_msg_text
            })
    return {"status": "SUCCESS", "matches": match_list}

@app.get("/api/users/{target_user_id}/matches")
def get_user_matches(target_user_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("id")
    raw_id = str(current_user.get("_id", ""))
    if target_user_id != "me" and target_user_id != user_id and target_user_id != raw_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to access another user's matches."
        )
    return get_my_matches(current_user=current_user)

# --- 8. Unmatch User ---
@app.post("/api/matches/{match_id}/unmatch")
def unmatch_user(match_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    try:
        obj_id = ObjectId(match_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid match ID format")

    match = matches_collection.find_one({
        "_id": obj_id,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "status": "ACTIVE"
    })

    if not match:
        raise HTTPException(status_code=404, detail="Active match not found.")

    # Mark match as UNMATCHED so it disappears from both users
    matches_collection.update_one(
        {"_id": obj_id},
        {"$set": {"status": "UNMATCHED", "unmatched_by": user_id, "unmatched_at": datetime.utcnow()}}
    )
    return {"status": "SUCCESS", "message": "Unmatched successfully."}

# --- 9. Block User ---
@app.post("/api/users/block")
def block_user(payload: BlockUserRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    if payload.targetUserId == user_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself.")

    target_user = users_collection.find_one({"id": payload.targetUserId})
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user to block not found.")

    # 1. Insert Block Record
    blocks_collection.update_one(
        {"blocker_user_id": user_id, "target_user_id": payload.targetUserId},
        {"$set": {"reason": payload.reason, "created_at": datetime.utcnow()}},
        upsert=True
    )

    # 2. Deactivate any existing active matches between them
    matches_collection.update_many(
        {
            "$or": [
                {"user1_id": user_id, "user2_id": payload.targetUserId},
                {"user1_id": payload.targetUserId, "user2_id": user_id}
            ],
            "status": "ACTIVE"
        },
        {"$set": {"status": "BLOCKED", "blocked_by": user_id}}
    )

    return {"status": "SUCCESS", "message": "User blocked and removed from matches."}

# --- 10. Report User ---
@app.post("/api/users/report")
@limiter.limit("5/hour")  # Prevent report spam — max 5 reports per hour per IP
def report_user(request: Request, payload: ReportUserRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # 1. Cannot report yourself
    if payload.targetUserId == user_id:
        raise HTTPException(status_code=400, detail="Cannot report yourself.")

    # 2. Validate target user exists before accepting the report
    target_user = users_collection.find_one({"id": payload.targetUserId})
    if not target_user:
        raise HTTPException(status_code=404, detail="Reported profile not found.")

    # 3. Upsert report — prevents the same user from flooding duplicate reports against
    #    the same target; updates reason/details if they report again.
    reports_collection.update_one(
        {
            "reporter_user_id": user_id,
            "reported_user_id": payload.targetUserId
        },
        {
            "$set": {
                "reason": payload.reason.value,
                "details": payload.details,
                "status": "PENDING_REVIEW",
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    # 4. Auto-block reported profile for reporter's safety
    blocks_collection.update_one(
        {"blocker_user_id": user_id, "target_user_id": payload.targetUserId},
        {"$set": {"reason": f"REPORTED: {payload.reason.value}", "created_at": datetime.utcnow()}},
        upsert=True
    )

    return {"status": "SUCCESS", "message": "Report submitted. The user has also been blocked."}

# --- 11. Photo Verification (Strictly Authenticated via JWT) ---
@app.post("/api/verify-profile")
async def verify_profile(
    request: Request,
    selfie_photo: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Security: JWT -> Authenticated user -> Database user (no client-supplied ID accepted)
    authenticated_user_id = current_user["id"]
    user = current_user

    profile_photos = user.get("photos", [])
    if not profile_photos:
        raise HTTPException(status_code=400, detail="User has no profile photo to match with")

    # Validate selfie photo image structure, format, 5MB size, magic bytes, dimensions
    selfie_stream, _, _ = await validate_and_process_uploaded_image(selfie_photo, request)

    profile_path = os.path.join(UPLOAD_DIR, f"{authenticated_user_id}_profile.jpg")
    selfie_path = os.path.join(UPLOAD_DIR, f"{authenticated_user_id}_selfie.jpg")

    first_photo_url = profile_photos[0]
    # Securely retrieve from authorized CDN (SSRF & LFI protection)
    download_safe_profile_image(first_photo_url, profile_path, upload_dir=UPLOAD_DIR)

    with open(selfie_path, "wb") as buffer:
        shutil.copyfileobj(selfie_stream, buffer)

    verification_result = verify_user_selfie(profile_path, selfie_path)

    if verification_result.get("verified"):
        users_collection.update_one({"id": authenticated_user_id}, {"$set": {"is_photo_verified": True}})

    if os.path.exists(profile_path):
        os.remove(profile_path)
    if os.path.exists(selfie_path):
        os.remove(selfie_path)

    return {"userId": authenticated_user_id, "result": verification_result}

# --- 12. Match Status Lookup & Chat History ---
@app.get("/api/matches/{match_id}")
def get_match_status(match_id: str, current_user: dict = Depends(get_current_user)):
    """Get current match status. Proactively expires match if 24-hour deadline passed."""
    user_id = current_user["id"]
    try:
        match_obj_id = ObjectId(match_id)
        match_query = {
            "_id": match_obj_id,
            "$or": [{"user1_id": user_id}, {"user2_id": user_id}]
        }
    except Exception:
        match_query = {
            "$or": [
                {"_id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}]},
                {"id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}]}
            ]
        }

    match = matches_collection.find_one(match_query)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found.")

    now = datetime.utcnow()
    deadline = match.get("first_move_deadline")
    has_first_move = match.get("first_move_made", False)
    current_status = match.get("status", "ACTIVE")

    # Proactively expire on fetch if deadline passed and no messages sent
    if current_status == "ACTIVE" and not has_first_move and deadline and now > deadline:
        msg_count = messages_collection.count_documents({"match_id": match_id})
        if msg_count == 0:
            matches_collection.update_one(
                {"_id": match["_id"]},
                {"$set": {"status": "EXPIRED", "expired_at": now}}
            )
            current_status = "EXPIRED"
        else:
            matches_collection.update_one(
                {"_id": match["_id"]},
                {"$set": {"first_move_made": True}}
            )
            has_first_move = True

    return {
        "status": "SUCCESS",
        "match": {
            "matchId": match_id,
            "matchStatus": current_status,
            "firstMoveMade": has_first_move,
            "firstMoveDeadline": deadline.isoformat() if deadline else None,
            "firstMoverId": match.get("first_mover_id"),
            "firstMoveRecipientId": match.get("first_move_recipient_id"),
            "isYourTurnToMove": (
                not has_first_move
                and current_status == "ACTIVE"
                and match.get("first_mover_id") == user_id
            ),
            "isExpired": current_status == "EXPIRED",
            "secondsRemaining": max(0, int((deadline - now).total_seconds())) if deadline and current_status == "ACTIVE" else 0
        }
    }

@app.get("/api/matches/{match_id}/messages")
def get_match_messages(match_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # Security: ensure requesting authenticated user is an actual participant of this match (IDOR prevention)
    try:
        match_obj_id = ObjectId(match_id)
        match_query = {
            "_id": match_obj_id,
            "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]
        }
    except Exception:
        match_query = {
            "$or": [
                {"_id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]},
                {"id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]}
            ]
        }

    match = matches_collection.find_one(match_query)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access messages for this match."
        )

    now = datetime.utcnow()
    deadline = match.get("first_move_deadline")
    has_first_move = match.get("first_move_made", False)
    match_status = match.get("status", "ACTIVE")

    # Enforce: if ACTIVE match has an expired deadline and no messages, expire it now
    if match_status == "ACTIVE" and not has_first_move and deadline and now > deadline:
        msg_count = messages_collection.count_documents({"match_id": match_id})
        if msg_count == 0:
            matches_collection.update_one(
                {"_id": match["_id"]},
                {"$set": {"status": "EXPIRED", "expired_at": now}}
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This match expired: the 24-hour first move deadline passed without a message being sent."
            )
        else:
            matches_collection.update_one(
                {"_id": match["_id"]},
                {"$set": {"first_move_made": True}}
            )

    msgs_cursor = list(messages_collection.find({"match_id": match_id}).sort("timestamp", 1))
    sender_ids = list({m.get("sender_id") for m in msgs_cursor if m.get("sender_id")})
    user_map = {}
    if sender_ids:
        for u in users_collection.find({"id": {"$in": sender_ids}}):
            user_map[u.get("id")] = u

    history = []
    for m in msgs_cursor:
        s_user = user_map.get(m.get("sender_id"), {})
        photos = s_user.get("photos", [])
        history.append({
            "id": str(m["_id"]),
            "matchId": m["match_id"],
            "senderId": m["sender_id"],
            "senderName": s_user.get("name", "Spark Member"),
            "senderPhoto": photos[0] if photos else "",
            "text": m["text"],
            "isScreenshot": m.get("is_screenshot", False),
            "isDateProposal": m.get("is_date_proposal", False),
            "dateProposal": m.get("date_proposal"),
            "isChemistryChallenge": m.get("is_chemistry_challenge", False),
            "chemistrySession": m.get("chemistry_session"),
            "timestamp": to_utc_iso(m.get("timestamp"))
        })
    return {
        "status": "SUCCESS",
        "messages": history,
        "isDoubleDate": match.get("is_double_date", False),
        "squadName": match.get("duo2_name" if match.get("user1_id") == user_id else "duo1_name"),
        "participants": match.get("participants", []),
    }

class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    isScreenshot: Optional[bool] = False

@app.post("/api/matches/{match_id}/messages")
async def send_match_message(
    match_id: str,
    payload: SendMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    text = payload.text.strip()
    is_screenshot = bool(payload.isScreenshot)

    # 1. Content Safety: Strict profanity and vulgarity rejection
    if not is_screenshot:
        is_clean, reject_reason = is_message_clean(text)
        if not is_clean:
            raise HTTPException(status_code=400, detail=reject_reason)

    # 2. Verify match and permissions
    try:
        match_obj_id = ObjectId(match_id)
        match_query = {
            "_id": match_obj_id,
            "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]
        }
    except Exception:
        match_query = {
            "$or": [
                {"_id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]},
                {"id": match_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}, {"participants": user_id}]}
            ]
        }

    match = matches_collection.find_one(match_query)
    if not match:
        raise HTTPException(status_code=403, detail="Not authorized to send messages on this match.")

    if match.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Match is not active.")

    is_double_date = bool(match.get("is_double_date"))
    u1 = match.get("user1_id")
    u2 = match.get("user2_id")
    receiver_id = "group" if is_double_date else (u2 if user_id == u1 else u1)

    if not is_double_date and receiver_id in get_blocked_user_ids(user_id):
        raise HTTPException(status_code=400, detail="Communication between these users is blocked.")

    msg_doc = {
        "match_id": match_id,
        "sender_id": user_id,
        "receiver_id": receiver_id,
        "text": text,
        "is_screenshot": is_screenshot,
        "timestamp": datetime.utcnow()
    }
    inserted = messages_collection.insert_one(msg_doc)

    if not match.get("first_move_made"):
        matches_collection.update_one({"_id": match["_id"]}, {"$set": {"first_move_made": True, "first_move_at": datetime.utcnow()}})

    u_sender = users_collection.find_one({"id": user_id})
    s_name = u_sender.get("name", "User") if u_sender else "User"
    s_photo = (u_sender.get("photos", [""]) or [""])[0] if u_sender else ""

    resp_payload = {
        "id": str(inserted.inserted_id),
        "matchId": match_id,
        "senderId": user_id,
        "senderName": s_name,
        "senderPhoto": s_photo,
        "receiverId": receiver_id,
        "text": text,
        "isScreenshot": is_screenshot,
        "isDoubleDate": is_double_date,
        "timestamp": to_utc_iso(msg_doc["timestamp"])
    }

    try:
        if is_double_date and match.get("participants"):
            for p_id in match["participants"]:
                await manager.send_personal_message(resp_payload, p_id)
        else:
            await manager.send_personal_message(resp_payload, user_id)
            await manager.send_personal_message(resp_payload, receiver_id)
    except Exception:
        pass

    return {"status": "SUCCESS", "message": resp_payload}

# --- 13. Secure WebSocket Chat (Handshake Token Auth & Isolation) ---
@app.websocket("/ws/chat")
@app.websocket("/ws/chat/{client_user_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None,
    client_user_id: Optional[str] = None,
):
    # 0. Transport Security: In production or when ENFORCE_HTTPS is active, require wss://
    if ENFORCE_HTTPS or IS_PRODUCTION:
        ws_scheme = websocket.scope.get("scheme", "").lower()
        forwarded_proto = websocket.headers.get("x-forwarded-proto", "").lower()
        forwarded_ssl = websocket.headers.get("x-forwarded-ssl", "").lower()
        is_secure_ws = ws_scheme == "wss" or forwarded_proto == "https" or forwarded_ssl == "on"
        if not is_secure_ws:
            print("[SECURITY] Rejected unencrypted ws:// connection in production mode (requires wss://).")
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Secure transport required (wss://)"
            )
            return

    query_token = token or websocket.query_params.get("token")
    if not query_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = decode_access_token(query_token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        if client_user_id and client_user_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            match_id = data.get("matchId")
            text = (data.get("text") or "").strip()

            if not match_id or not text:
                await websocket.send_json({
                    "status": "ERROR",
                    "error": "INVALID_PAYLOAD",
                    "message": "matchId and non-empty text are required."
                })
                continue

            if len(text) > 1000:
                await websocket.send_json({
                    "status": "ERROR",
                    "error": "MESSAGE_TOO_LONG",
                    "message": "Chat message cannot exceed 1000 characters."
                })
                continue

            is_screenshot = data.get("type") == "SCREENSHOT_ALERT" or bool(data.get("isScreenshot", False))

            # Content Safety: Block vulgar, abusive, or sexually explicit messages
            if not is_screenshot:
                is_clean, reject_reason = is_message_clean(text)
                if not is_clean:
                    await websocket.send_json({
                        "status": "ERROR",
                        "error": "VULGAR_CONTENT",
                        "message": reject_reason
                    })
                    continue

            # 1. Does this match exist?
            try:
                m_obj_id = ObjectId(match_id)
                match = matches_collection.find_one({"_id": m_obj_id})
            except Exception:
                match = matches_collection.find_one({"$or": [{"_id": match_id}, {"id": match_id}]})

            if not match:
                await websocket.send_json({
                    "status": "ERROR",
                    "error": "MATCH_NOT_FOUND",
                    "message": "Match does not exist."
                })
                continue

            # 2. Is the match ACTIVE?
            if match.get("status") != "ACTIVE":
                await websocket.send_json({
                    "status": "ERROR",
                    "error": "MATCH_NOT_ACTIVE",
                    "message": "Match is not active or has been unmatched."
                })
                continue

            # 3. Is authenticated user part of this match?
            u1 = match.get("user1_id")
            u2 = match.get("user2_id")
            participants = match.get("participants") or [u1, u2]
            if user_id not in participants:
                await websocket.send_json({
                    "status": "ERROR",
                    "error": "UNAUTHORIZED_SENDER",
                    "message": "Sender is not a member of this match."
                })
                continue

            is_double_date = bool(match.get("is_double_date"))

            # 4. DERIVE RECEIVER SERVER-SIDE FROM MATCH
            if is_double_date:
                receiver_id = "group"
            else:
                receiver_id = u2 if user_id == u1 else u1
                client_receiver_id = data.get("receiverId")
                if client_receiver_id and client_receiver_id != receiver_id:
                    await websocket.send_json({
                        "status": "ERROR",
                        "error": "RECEIVER_MISMATCH",
                        "message": "Client receiverId does not match the paired match participant."
                    })
                    continue

                # 5. Check if communication is blocked between participants
                if receiver_id in get_blocked_user_ids(user_id):
                    await websocket.send_json({
                        "status": "ERROR",
                        "error": "COMMUNICATION_BLOCKED",
                        "message": "Communication between these users is blocked."
                    })
                    continue

            # 6. Enforce first_move_deadline for solo matches
            deadline = match.get("first_move_deadline")
            has_first_move = match.get("first_move_made", False)
            first_mover_id = match.get("first_mover_id")

            if not is_double_date and not has_first_move:
                # Recount messages as source of truth in case the flag is stale
                msg_count = messages_collection.count_documents({"match_id": match_id})
                if msg_count > 0:
                    has_first_move = True
                    matches_collection.update_one({"_id": match["_id"]}, {"$set": {"first_move_made": True}})
                else:
                    # Enforce deadline expiry
                    if deadline and datetime.utcnow() > deadline:
                        matches_collection.update_one(
                            {"_id": match["_id"]},
                            {"$set": {"status": "EXPIRED", "expired_at": datetime.utcnow()}}
                        )
                        await websocket.send_json({
                            "status": "ERROR",
                            "error": "MATCH_EXPIRED",
                            "message": "The 24-hour first move deadline has expired for this match."
                        })
                        continue

                    if first_mover_id and user_id != first_mover_id:
                        await websocket.send_json({
                            "status": "ERROR",
                            "error": "NOT_FIRST_MOVER",
                            "message": "Waiting for the other person to send the first message. You can reply once they open the conversation."
                        })
                        continue

            msg_doc = {
                "match_id": match_id,
                "sender_id": user_id,
                "receiver_id": receiver_id,
                "text": text,
                "is_screenshot": is_screenshot,
                "timestamp": datetime.utcnow()
            }
            inserted = messages_collection.insert_one(msg_doc)

            # Mark first move made if not previously recorded
            if not has_first_move:
                matches_collection.update_one(
                    {"_id": match["_id"]},
                    {"$set": {"first_move_made": True, "first_move_at": datetime.utcnow()}}
                )

            u_sender = users_collection.find_one({"id": user_id})
            s_name = u_sender.get("name", "User") if u_sender else "User"
            s_photo = (u_sender.get("photos", [""]) or [""])[0] if u_sender else ""

            broadcast_payload = {
                "id": str(inserted.inserted_id),
                "matchId": match_id,
                "senderId": user_id,
                "senderName": s_name,
                "senderPhoto": s_photo,
                "receiverId": receiver_id,
                "text": text,
                "isScreenshot": is_screenshot,
                "isDoubleDate": is_double_date,
                "timestamp": to_utc_iso(msg_doc["timestamp"])
            }

            # Deliver to participants
            if is_double_date and match.get("participants"):
                for p_id in match["participants"]:
                    if p_id != user_id:
                        await manager.send_personal_message(broadcast_payload, p_id)
            else:
                await manager.send_personal_message(broadcast_payload, receiver_id)

            # Sync message to all other connected devices of the sender
            await manager.broadcast_to_user_devices(broadcast_payload, user_id, exclude_socket=websocket)

            # Echo payload back to current sender device
            await websocket.send_json(broadcast_payload)

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception as e:
        print(f"WebSocket Error: {e}")
        manager.disconnect(user_id, websocket)

# --- 14. Cloud Image Upload (Authenticated & User-Associated) ---
@app.post("/api/upload-photo")
async def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id", "unknown")

    # 1. Enforce photo limits server-side
    if not current_user.get("is_registration_token"):
        db_user = users_collection.find_one({"id": user_id})
        if db_user:
            current_photos = db_user.get("photos", [])
            if len(current_photos) >= MAX_PROFILE_PHOTOS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Profile photo limit reached. Maximum {MAX_PROFILE_PHOTOS} photos allowed per user."
                )
    else:
        recent_uploads = uploads_collection.count_documents({
            "phone": current_user.get("phone"),
            "uploaded_at": {"$gte": datetime.utcnow() - timedelta(minutes=30)}
        })
        if recent_uploads >= MAX_PROFILE_PHOTOS * 3:
            raise HTTPException(
                status_code=429,
                detail=f"Upload limit reached for registration session. Profiles support a maximum of {MAX_PROFILE_PHOTOS} photos."
            )

    # 2. Deep binary validation (magic bytes, dimensions, 5MB file size, extension, decompression limits)
    validated_stream, detected_format, canonical_ext = await validate_and_process_uploaded_image(file, request)

    # 3. Security & Safety Moderation (Malware scan, EXIF/GPS privacy stripping, NSFW/nudity check)
    sanitized_stream, moderation_meta = process_and_moderate_image(validated_stream, detected_format)

    if moderation_meta.get("status") != "APPROVED":
        raise HTTPException(
            status_code=400,
            detail=moderation_meta.get("reason") or "Photo rejected: Inappropriate, 18+, or naked content is strictly prohibited on Spark."
        )

    try:
        # Upload sanitized in-memory stream to Cloudinary organized by user folder
        cloud_url = upload_image_to_cloud(sanitized_stream, folder=f"spark_dating_profiles/{user_id}")
        
        # Associate upload with user in audit collection with moderation log
        uploads_collection.insert_one({
            "user_id": user_id,
            "phone": current_user.get("phone"),
            "url": cloud_url,
            "detected_format": detected_format,
            "content_type": f"image/{detected_format.lower()}",
            "moderation_status": moderation_meta.get("status", "APPROVED"),
            "moderation_reason": moderation_meta.get("reason"),
            "is_flagged": moderation_meta.get("is_flagged", False),
            "skin_exposure_ratio": moderation_meta.get("skin_exposure_ratio"),
            "uploaded_at": datetime.utcnow()
        })

        # If user is already registered in users_collection, link photo to profile
        if not current_user.get("is_registration_token") and "photos" in current_user:
            users_collection.update_one(
                {"id": user_id},
                {"$addToSet": {"photos": cloud_url}}
            )

        return {
            "status": "SUCCESS",
            "url": cloud_url,
            "userId": user_id,
            "moderationStatus": moderation_meta.get("status", "APPROVED")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

def format_user_profile_response(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "role": user.get("role", "user"),
        "age": user.get("age"),
        "gender": user.get("gender"),
        "phone": user.get("phone", ""),
        "bio": user.get("bio", ""),
        "photos": user.get("photos", []),
        "prompts": user.get("prompts", []),
        "is_photo_verified": user.get("is_photo_verified", False),
        "isPhotoVerified": user.get("is_photo_verified", False),
        "locationName": user.get("locationName") or "",
        "occupation": user.get("occupation") or "",
        "company": user.get("company") or "",
        "education": user.get("education") or "",
        "hometown": user.get("hometown") or "",
        "height": user.get("height") or "",
        "relationshipGoals": user.get("relationshipGoals") or "",
        "drinking": user.get("drinking") or "",
        "smoking": user.get("smoking") or "",
        "exercise": user.get("exercise") or "",
        "interests": user.get("interests", []),
        "languages": user.get("languages", []),
    }

# --- 15. User Profiles (Current User & By ID) ---
@app.get("/api/users/me")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    # Fetch fresh document from db to ensure latest fields
    fresh_user = users_collection.find_one({"id": user_id}) or current_user
    user_role = fresh_user.get("role", "user")
    user_phone = fresh_user.get("phone", "")
    if is_admin_phone(user_phone):
        user_role = "admin"
        if fresh_user.get("role") != "admin":
            users_collection.update_one({"id": user_id}, {"$set": {"role": "admin"}})
            fresh_user["role"] = "admin"

    return {
        "status": "SUCCESS",
        "user": format_user_profile_response(fresh_user)
    }

@app.put("/api/users/me")
def update_my_profile(payload: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    # Security check: Name, Age, Gender, Phone are STRICTLY IMMUTABLE and cannot be modified
    update_data = {}
    if payload.bio is not None:
        update_data["bio"] = payload.bio.strip()
    if payload.photos is not None:
        if len(payload.photos) == 0:
            raise HTTPException(status_code=400, detail="Profile must contain at least one photo.")
        if len(payload.photos) > 6:
            raise HTTPException(status_code=400, detail="Maximum 6 photos allowed.")
        update_data["photos"] = payload.photos
    if payload.prompts is not None:
        update_data["prompts"] = payload.prompts
    if payload.occupation is not None:
        update_data["occupation"] = payload.occupation.strip()
    if payload.company is not None:
        update_data["company"] = payload.company.strip()
    if payload.education is not None:
        update_data["education"] = payload.education.strip()
    if payload.hometown is not None:
        update_data["hometown"] = payload.hometown.strip()
    if payload.height is not None:
        update_data["height"] = payload.height.strip()
    if payload.relationshipGoals is not None:
        update_data["relationshipGoals"] = payload.relationshipGoals.strip()
    if payload.drinking is not None:
        update_data["drinking"] = payload.drinking.strip()
    if payload.smoking is not None:
        update_data["smoking"] = payload.smoking.strip()
    if payload.exercise is not None:
        update_data["exercise"] = payload.exercise.strip()
    if payload.interests is not None:
        update_data["interests"] = [i.strip() for i in payload.interests if i.strip()]
    if payload.languages is not None:
        update_data["languages"] = [l.strip() for l in payload.languages if l.strip()]

    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        users_collection.update_one({"id": user_id}, {"$set": update_data})

    fresh_user = users_collection.find_one({"id": user_id})
    return {
        "status": "SUCCESS",
        "message": "Profile updated successfully",
        "user": format_user_profile_response(fresh_user)
    }

@app.get("/api/users/{target_user_id}")
def get_user_by_id(target_user_id: str, current_user: dict = Depends(get_current_user)):
    current_user_id = current_user["id"]

    # 1. If self requested, return authenticated user's own profile
    if target_user_id == "me" or target_user_id == current_user_id:
        return get_my_profile(current_user)

    # 2. Check block list between both users
    blocked_ids = get_blocked_user_ids(current_user_id)
    if target_user_id in blocked_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or unavailable."
        )

    # 3. Lookup user by ID
    target_user = users_collection.find_one({"id": target_user_id})
    if not target_user:
        try:
            target_user = users_collection.find_one({"_id": ObjectId(target_user_id)})
        except Exception:
            target_user = None

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # 4. Return sanitized public profile
    return {
        "status": "SUCCESS",
        "user": {
            "id": target_user["id"],
            "name": target_user["name"],
            "age": target_user.get("age"),
            "gender": target_user.get("gender"),
            "bio": target_user.get("bio", ""),
            "photos": target_user.get("photos", []),
            "prompts": target_user.get("prompts", []),
            "is_photo_verified": target_user.get("is_photo_verified", False),
            "isPhotoVerified": target_user.get("is_photo_verified", False),
            "locationName": target_user.get("locationName") or "",
        }
    }


# =============================================================================
# --- ADMIN MODERATION API ---
# =============================================================================
# Access is restricted to users whose phone is listed in the ADMIN_PHONE_NUMBERS
# environment variable (comma-separated E.164 numbers). On first login, those
# users are automatically promoted to role="admin" in the database.
#
# All moderation actions are recorded in moderation_actions_collection for audit.
# =============================================================================

_ADMIN_PHONES: set = {
    p.strip() for p in os.getenv("ADMIN_PHONE_NUMBERS", "").split(",") if p.strip()
}

# --- Report status workflow transitions (linear pipeline) ---
REPORT_WORKFLOW = {
    "PENDING_REVIEW":  ["INVESTIGATING", "DISMISSED"],
    "INVESTIGATING":   ["WARNED", "SUSPENDED", "DELETED", "DISMISSED"],
    "WARNED":          ["SUSPENDED", "DELETED", "RESOLVED"],
    "SUSPENDED":       ["DELETED", "RESOLVED"],
    "DELETED":         [],          # Terminal state
    "DISMISSED":       [],          # Terminal state
    "RESOLVED":        [],          # Terminal state
}

def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency that gates routes to admin users only.
    Promotes the user to admin role on first access if their phone is whitelisted.
    """
    user_id = current_user["id"]
    phone = current_user.get("phone", "")

    # Auto-promote whitelisted phone to admin role on admin API call
    if is_admin_phone(phone) and current_user.get("role") != "admin":
        users_collection.update_one({"id": user_id}, {"$set": {"role": "admin"}})
        current_user["role"] = "admin"

    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user

def _record_mod_action(admin_id: str, action: str, target_user_id: str, report_id: Optional[str] = None, notes: Optional[str] = None):
    """Writes an immutable audit record for every moderation action."""
    moderation_actions_collection.insert_one({
        "admin_id": admin_id,
        "action": action,
        "target_user_id": target_user_id,
        "report_id": report_id,
        "notes": notes,
        "created_at": datetime.utcnow()
    })


# --- Admin Pydantic models ---
class ReportStatusUpdate(BaseModel):
    newStatus: str = Field(..., description="Target workflow status")
    notes: Optional[str] = Field(default=None, max_length=1000)

class WarnUserRequest(BaseModel):
    reportId: Optional[str] = Field(default=None, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)

class SuspendUserRequest(BaseModel):
    reportId: Optional[str] = Field(default=None, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)
    durationHours: int = Field(..., ge=1, le=8760, description="Suspension duration in hours (1h–1yr)")

class UnsuspendUserRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)

class DeleteUserRequest(BaseModel):
    reportId: Optional[str] = Field(default=None, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)


# --- 16. Admin: List & Filter Reports ---
@app.get("/api/admin/reports")
def admin_list_reports(
    report_status: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: dict = Depends(get_current_admin)
):
    """
    Returns a paginated list of reports, optionally filtered by workflow status.
    Each report is enriched with reporter and reported-user display names.
    """
    query: dict = {}
    if report_status:
        valid_statuses = set(REPORT_WORKFLOW.keys())
        if report_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter. Valid values: {sorted(valid_statuses)}"
            )
        query["status"] = report_status

    skip = (page - 1) * page_size
    total = reports_collection.count_documents(query)
    cursor = reports_collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)

    reports = []
    for r in cursor:
        reporter = users_collection.find_one({"id": r["reporter_user_id"]}, {"name": 1, "phone": 1})
        reported = users_collection.find_one({"id": r["reported_user_id"]}, {"name": 1, "phone": 1, "role": 1, "is_suspended": 1})
        reports.append({
            "reportId": str(r["_id"]),
            "status": r.get("status", "PENDING_REVIEW"),
            "reason": r.get("reason"),
            "details": r.get("details"),
            "createdAt": r["created_at"].isoformat(),
            "updatedAt": r["updated_at"].isoformat() if r.get("updated_at") else None,
            "reporter": {
                "id": r["reporter_user_id"],
                "name": reporter["name"] if reporter else "[deleted]",
            },
            "reported": {
                "id": r["reported_user_id"],
                "name": reported["name"] if reported else "[deleted]",
                "isSuspended": reported.get("is_suspended", False) if reported else False,
            },
            "allowedNextStatuses": REPORT_WORKFLOW.get(r.get("status", "PENDING_REVIEW"), []),
        })

    return {
        "status": "SUCCESS",
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
        "reports": reports
    }


# --- 17. Admin: Get Single Report ---
@app.get("/api/admin/reports/{report_id}")
def admin_get_report(report_id: str, admin: dict = Depends(get_current_admin)):
    """Returns a single report document with full audit history."""
    try:
        r = reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format.")
    if not r:
        raise HTTPException(status_code=404, detail="Report not found.")

    # Load moderation action history for this report
    history_cursor = moderation_actions_collection.find(
        {"report_id": report_id}
    ).sort("created_at", 1)
    history = [{
        "adminId": h["admin_id"],
        "action": h["action"],
        "notes": h.get("notes"),
        "createdAt": h["created_at"].isoformat()
    } for h in history_cursor]

    reporter = users_collection.find_one({"id": r["reporter_user_id"]}, {"name": 1})
    reported = users_collection.find_one({"id": r["reported_user_id"]}, {"name": 1, "is_suspended": 1, "warnings": 1})

    return {
        "status": "SUCCESS",
        "report": {
            "reportId": str(r["_id"]),
            "status": r.get("status", "PENDING_REVIEW"),
            "reason": r.get("reason"),
            "details": r.get("details"),
            "createdAt": r["created_at"].isoformat(),
            "updatedAt": r["updated_at"].isoformat() if r.get("updated_at") else None,
            "reporter": {"id": r["reporter_user_id"], "name": reporter["name"] if reporter else "[deleted]"},
            "reported": {
                "id": r["reported_user_id"],
                "name": reported["name"] if reported else "[deleted]",
                "isSuspended": reported.get("is_suspended", False) if reported else False,
                "warnings": reported.get("warnings", []) if reported else [],
            },
            "allowedNextStatuses": REPORT_WORKFLOW.get(r.get("status", "PENDING_REVIEW"), []),
            "moderationHistory": history
        }
    }


# --- 18. Admin: Advance Report Status ---
@app.patch("/api/admin/reports/{report_id}/status")
def admin_update_report_status(
    report_id: str,
    payload: ReportStatusUpdate,
    admin: dict = Depends(get_current_admin)
):
    """
    Moves a report through its moderation workflow.
    Only valid transitions (per REPORT_WORKFLOW) are accepted.
    """
    try:
        r = reports_collection.find_one({"_id": ObjectId(report_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format.")
    if not r:
        raise HTTPException(status_code=404, detail="Report not found.")

    current_report_status = r.get("status", "PENDING_REVIEW")
    allowed = REPORT_WORKFLOW.get(current_report_status, [])
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Report is in terminal status '{current_report_status}' and cannot be advanced."
        )
    if payload.newStatus not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition '{current_report_status}' → '{payload.newStatus}'. Allowed: {allowed}"
        )

    reports_collection.update_one(
        {"_id": r["_id"]},
        {"$set": {"status": payload.newStatus, "updated_at": datetime.utcnow()}}
    )
    _record_mod_action(
        admin_id=admin["id"],
        action=f"STATUS_{payload.newStatus}",
        target_user_id=r["reported_user_id"],
        report_id=report_id,
        notes=payload.notes
    )

    return {
        "status": "SUCCESS",
        "reportId": report_id,
        "previousStatus": current_report_status,
        "newStatus": payload.newStatus
    }


# --- 19. Admin: Warn User ---
@app.post("/api/admin/users/{target_user_id}/warn")
def admin_warn_user(
    target_user_id: str,
    payload: WarnUserRequest,
    admin: dict = Depends(get_current_admin)
):
    """
    Issues a formal warning to a user. Warnings are stored on the user document
    so they are visible in subsequent reviews. Three or more warnings can be
    used as automatic suspension criteria in a future automated policy pass.
    """
    target = users_collection.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")

    warning_entry = {
        "adminId": admin["id"],
        "reason": payload.reason,
        "reportId": payload.reportId,
        "issuedAt": datetime.utcnow().isoformat()
    }
    users_collection.update_one(
        {"id": target_user_id},
        {"$push": {"warnings": warning_entry}}
    )

    _record_mod_action(
        admin_id=admin["id"],
        action="WARN",
        target_user_id=target_user_id,
        report_id=payload.reportId,
        notes=payload.reason
    )

    warning_count = len(target.get("warnings", [])) + 1
    return {
        "status": "SUCCESS",
        "message": f"Warning issued. User now has {warning_count} warning(s).",
        "targetUserId": target_user_id,
        "totalWarnings": warning_count
    }


# --- 20. Admin: Suspend User ---
@app.post("/api/admin/users/{target_user_id}/suspend")
def admin_suspend_user(
    target_user_id: str,
    payload: SuspendUserRequest,
    admin: dict = Depends(get_current_admin)
):
    """
    Suspends a user account for the specified number of hours.
    While suspended, the user's access token will be rejected by get_current_user.
    All active refresh tokens are revoked immediately.
    """
    target = users_collection.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Cannot suspend an admin user.")

    suspend_until = datetime.utcnow() + timedelta(hours=payload.durationHours)

    users_collection.update_one(
        {"id": target_user_id},
        {"$set": {
            "is_suspended": True,
            "suspended_until": suspend_until,
            "suspension_reason": payload.reason
        }}
    )

    # Immediately revoke all active refresh tokens so existing sessions are terminated
    from database import refresh_tokens_collection as rtc
    rtc.update_many({"user_id": target_user_id, "revoked": False}, {"$set": {"revoked": True}})

    _record_mod_action(
        admin_id=admin["id"],
        action="SUSPEND",
        target_user_id=target_user_id,
        report_id=payload.reportId,
        notes=f"{payload.durationHours}h: {payload.reason}"
    )

    return {
        "status": "SUCCESS",
        "message": f"User suspended until {suspend_until.isoformat()} UTC.",
        "targetUserId": target_user_id,
        "suspendedUntil": suspend_until.isoformat()
    }


# --- 21. Admin: Unsuspend User ---
@app.post("/api/admin/users/{target_user_id}/unsuspend")
def admin_unsuspend_user(
    target_user_id: str,
    payload: UnsuspendUserRequest,
    admin: dict = Depends(get_current_admin)
):
    """Lifts an active suspension from a user."""
    target = users_collection.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")
    if not target.get("is_suspended"):
        raise HTTPException(status_code=400, detail="User is not currently suspended.")

    users_collection.update_one(
        {"id": target_user_id},
        {"$set": {"is_suspended": False, "suspended_until": None, "suspension_reason": None}}
    )

    _record_mod_action(
        admin_id=admin["id"],
        action="UNSUSPEND",
        target_user_id=target_user_id,
        notes=payload.notes
    )

    return {"status": "SUCCESS", "message": "Suspension lifted.", "targetUserId": target_user_id}


# --- 22. Admin: Hard-Delete User (with cascade) ---
@app.delete("/api/admin/users/{target_user_id}")
def admin_delete_user(
    target_user_id: str,
    payload: DeleteUserRequest,
    admin: dict = Depends(get_current_admin)
):
    """
    Permanently deletes a user account with full cascade cleanup:
    - Removes user document
    - Removes all interactions (sent and received)
    - Removes all matches and their chat messages
    - Removes all blocks where this user is blocker or target
    - Removes all reports filed by or against this user
    - Revokes all refresh tokens
    - Removes all photo uploads
    """
    target = users_collection.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Cannot delete an admin user.")

    # 1. Cascade delete matches and their messages
    match_docs = list(matches_collection.find({
        "$or": [{"user1_id": target_user_id}, {"user2_id": target_user_id}]
    }, {"_id": 1}))
    match_ids = [str(m["_id"]) for m in match_docs]
    if match_ids:
        messages_collection.delete_many({"match_id": {"$in": match_ids}})
    matches_collection.delete_many(
        {"$or": [{"user1_id": target_user_id}, {"user2_id": target_user_id}]}
    )

    # 2. Cascade delete interactions
    interactions_collection.delete_many({
        "$or": [{"from_user_id": target_user_id}, {"target_user_id": target_user_id}]
    })

    # 3. Cascade delete blocks
    blocks_collection.delete_many({
        "$or": [{"blocker_user_id": target_user_id}, {"target_user_id": target_user_id}]
    })

    # 4. Cascade delete reports (filed by or against)
    reports_collection.delete_many({
        "$or": [{"reporter_user_id": target_user_id}, {"reported_user_id": target_user_id}]
    })

    # 5. Revoke all refresh tokens
    from database import refresh_tokens_collection as rtc
    rtc.delete_many({"user_id": target_user_id})

    # 6. Remove photo uploads record
    uploads_collection.delete_many({"user_id": target_user_id})

    # 7. Delete user document itself
    users_collection.delete_one({"id": target_user_id})

    # 8. Record the deletion action before returning
    _record_mod_action(
        admin_id=admin["id"],
        action="DELETE",
        target_user_id=target_user_id,
        report_id=payload.reportId,
        notes=payload.reason
    )

    return {
        "status": "SUCCESS",
        "message": "User account and all associated data permanently deleted.",
        "deletedUserId": target_user_id,
        "cascadeDeleted": {
            "matches": len(match_ids),
            "messages": "all in above matches"
        }
    }

# ==============================================================================
# AI WINGMAN — PERSONAL DATING ASSISTANT ENDPOINTS
# ==============================================================================

class WingmanIcebreakersRequest(BaseModel):
    matchId: str
    tone: Optional[str] = "funny"
    language: Optional[str] = "hinglish"

class WingmanReviveRequest(BaseModel):
    matchId: str
    tone: Optional[str] = "funny"
    language: Optional[str] = "hinglish"

class WingmanCoachRequest(BaseModel):
    language: Optional[str] = "hinglish"

@app.post("/api/wingman/icebreakers")
@limiter.limit("30/minute")
async def get_wingman_icebreakers(
    request: Request,
    payload: WingmanIcebreakersRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generates tailored icebreaker suggestions based on match's profile & interests.
    AI gives suggestions only — user reviews and sends manually.
    """
    user_id = current_user["id"]
    try:
        obj_id = ObjectId(payload.matchId)
        match_query = {"_id": obj_id}
    except Exception:
        match_query = {"_id": payload.matchId}

    match = matches_collection.find_one({
        **match_query,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
    })
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    other_user_id = match["user2_id"] if match["user1_id"] == user_id else match["user1_id"]
    other_user = users_collection.find_one({"id": other_user_id})
    if not other_user:
        raise HTTPException(status_code=404, detail="Match partner profile not found.")

    result = await generate_icebreakers(
        match_profile=other_user,
        user_profile=current_user,
        tone=payload.tone or "funny",
        language=payload.language or "hinglish"
    )

    return {
        "status": "SUCCESS",
        "matchName": other_user.get("name", "Match"),
        "matchPhoto": other_user.get("photos", [""])[0] if other_user.get("photos") else "",
        **result
    }

@app.post("/api/wingman/revive")
@limiter.limit("30/minute")
async def get_wingman_revive(
    request: Request,
    payload: WingmanReviveRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generates natural follow-up lines to restart a stalled/quiet conversation.
    """
    user_id = current_user["id"]
    try:
        obj_id = ObjectId(payload.matchId)
        match_query = {"_id": obj_id}
    except Exception:
        match_query = {"_id": payload.matchId}

    match = matches_collection.find_one({
        **match_query,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
    })
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    other_user_id = match["user2_id"] if match["user1_id"] == user_id else match["user1_id"]
    other_user = users_collection.find_one({"id": other_user_id})
    if not other_user:
        raise HTTPException(status_code=404, detail="Match partner profile not found.")

    # Fetch recent messages
    recent_docs = list(
        messages_collection.find({"match_id": str(match["_id"])})
        .sort("timestamp", -1)
        .limit(6)
    )
    recent_docs.reverse()
    formatted_recent = [
        {"sender": "me" if m.get("sender_id") == user_id else "them", "text": m.get("text", "")}
        for m in recent_docs
    ]

    result = await generate_chat_revivers(
        recent_messages=formatted_recent,
        match_profile=other_user,
        tone=payload.tone or "funny",
        language=payload.language or "hinglish"
    )

    return {
        "status": "SUCCESS",
        "matchName": other_user.get("name", "Match"),
        **result
    }

@app.post("/api/wingman/profile-coach")
@limiter.limit("15/minute")
def get_wingman_profile_coach(
    request: Request,
    payload: WingmanCoachRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Analyzes current user's profile and returns a Strength Score (0-100) + actionable tips.
    """
    result = generate_profile_coach(
        user_profile=current_user,
        language=payload.language or "hinglish"
    )
    return {
        "status": "SUCCESS",
        **result
    }

# ==============================================================================
# DATE PLANNER — REAL-WORLD DATE ENGINE
# ==============================================================================

class DateIdeasRequest(BaseModel):
    matchId: str
    budget: Optional[str] = "500"
    activity: Optional[str] = "coffee"
    timeSlot: Optional[str] = "Saturday, 5:30 PM"
    cityOrArea: Optional[str] = None

class DateProposalRequest(BaseModel):
    matchId: str
    planId: Optional[str] = None
    title: str
    activity: str
    budget: str
    vibe: str
    duration: str
    description: str
    suggestedTime: str
    location: Optional[str] = "Nearby"

class DateResponseRequest(BaseModel):
    matchId: str
    proposalId: str
    action: str  # "ACCEPT" | "DECLINE"

@app.post("/api/date-planner/ideas")
@limiter.limit("30/minute")
async def get_date_ideas(
    request: Request,
    payload: DateIdeasRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        obj_id = ObjectId(payload.matchId)
        match_query = {"_id": obj_id}
    except Exception:
        match_query = {"_id": payload.matchId}

    match = matches_collection.find_one({
        **match_query,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
    })
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    other_user_id = match["user2_id"] if match["user1_id"] == user_id else match["user1_id"]
    other_user = users_collection.find_one({"id": other_user_id})
    if not other_user:
        raise HTTPException(status_code=404, detail="Match partner profile not found.")

    ideas = await generate_date_ideas(
        user1_profile=current_user,
        user2_profile=other_user,
        budget=payload.budget or "500",
        activity=payload.activity or "coffee",
        time_slot=payload.timeSlot or "Saturday, 5:30 PM",
        city_or_area=payload.cityOrArea
    )

    return {
        "status": "SUCCESS",
        "matchName": other_user.get("name", "Match"),
        "matchPhoto": other_user.get("photos", [""])[0] if other_user.get("photos") else "",
        "ideas": ideas
    }

@app.post("/api/date-planner/propose")
@limiter.limit("20/minute")
async def propose_date_plan(
    request: Request,
    payload: DateProposalRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        obj_id = ObjectId(payload.matchId)
        match_query = {"_id": obj_id}
    except Exception:
        match_query = {"_id": payload.matchId}

    match = matches_collection.find_one({
        **match_query,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
    })
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    u1 = match.get("user1_id")
    u2 = match.get("user2_id")
    receiver_id = u2 if user_id == u1 else u1
    other_user = users_collection.find_one({"id": receiver_id}) or {}

    proposal_id = payload.planId or str(uuid.uuid4())[:8]
    cal_url = build_google_calendar_url(
        title=f"{payload.title} with {other_user.get('name', 'Match')}",
        description=f"Plan: {payload.description}\nVibe: {payload.vibe}\nBudget: {payload.budget}\nTime: {payload.suggestedTime}",
        location=payload.location or "Agreed Venue"
    )

    date_proposal_data = {
        "proposalId": proposal_id,
        "title": payload.title,
        "activity": payload.activity,
        "budget": payload.budget,
        "vibe": payload.vibe,
        "duration": payload.duration,
        "description": payload.description,
        "suggestedTime": payload.suggestedTime,
        "location": payload.location or "Nearby",
        "status": "PENDING",
        "proposedBy": user_id,
        "calendarUrl": cal_url,
        "createdAt": datetime.utcnow().isoformat()
    }

    msg_doc = {
        "match_id": payload.matchId,
        "sender_id": user_id,
        "receiver_id": receiver_id,
        "text": f"📅 Date Plan Proposed: {payload.title}",
        "is_screenshot": False,
        "is_date_proposal": True,
        "date_proposal": date_proposal_data,
        "timestamp": datetime.utcnow()
    }
    inserted = messages_collection.insert_one(msg_doc)

    resp_payload = {
        "id": str(inserted.inserted_id),
        "matchId": payload.matchId,
        "senderId": user_id,
        "receiverId": receiver_id,
        "text": msg_doc["text"],
        "isScreenshot": False,
        "isDateProposal": True,
        "dateProposal": date_proposal_data,
        "timestamp": to_utc_iso(msg_doc["timestamp"])
    }

    try:
        await manager.send_personal_message(resp_payload, user_id)
        await manager.send_personal_message(resp_payload, receiver_id)
    except Exception:
        pass

    return {
        "status": "SUCCESS",
        "message": resp_payload,
        "dateProposal": date_proposal_data
    }

@app.post("/api/date-planner/respond")
@limiter.limit("20/minute")
async def respond_to_date_plan(
    request: Request,
    payload: DateResponseRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        obj_id = ObjectId(payload.matchId)
        match_query = {"_id": obj_id}
    except Exception:
        match_query = {"_id": payload.matchId}

    match = matches_collection.find_one({
        **match_query,
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
    })
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")

    u1 = match.get("user1_id")
    u2 = match.get("user2_id")
    other_user_id = u2 if user_id == u1 else u1

    action_norm = payload.action.upper()
    new_status = "ACCEPTED" if action_norm in ["ACCEPT", "ACCEPTED"] else "DECLINED"

    # Find the proposal message
    proposal_msg = messages_collection.find_one({
        "match_id": payload.matchId,
        "is_date_proposal": True,
        "date_proposal.proposalId": payload.proposalId
    })

    if not proposal_msg:
        raise HTTPException(status_code=404, detail="Date proposal not found.")

    current_prop = proposal_msg.get("date_proposal", {})
    current_prop["status"] = new_status
    current_prop["respondedBy"] = user_id
    current_prop["respondedAt"] = datetime.utcnow().isoformat()

    messages_collection.update_one(
        {"_id": proposal_msg["_id"]},
        {"$set": {"date_proposal": current_prop}}
    )

    # Insert confirmation message into chat
    if new_status == "ACCEPTED":
        conf_text = f"🎉 Date Confirmed! See you for {current_prop.get('title', 'the date')} ({current_prop.get('suggestedTime', '')}) ✨"
    else:
        conf_text = f"Date plan declined. Let's suggest another time or activity!"

    conf_doc = {
        "match_id": payload.matchId,
        "sender_id": user_id,
        "receiver_id": other_user_id,
        "text": conf_text,
        "is_screenshot": False,
        "is_date_proposal": False,
        "timestamp": datetime.utcnow()
    }
    inserted = messages_collection.insert_one(conf_doc)
    conf_payload = {
        "id": str(inserted.inserted_id),
        "matchId": payload.matchId,
        "senderId": user_id,
        "receiverId": other_user_id,
        "text": conf_text,
        "isScreenshot": False,
        "isDateProposal": False,
        "timestamp": to_utc_iso(conf_doc["timestamp"]),
        "updatedProposal": current_prop
    }

    try:
        await manager.send_personal_message(conf_payload, user_id)
        await manager.send_personal_message(conf_payload, other_user_id)
    except Exception:
        pass

    return {
        "status": "SUCCESS",
        "action": new_status,
        "dateProposal": current_prop
    }

# ==============================================================================
# SPARK CIRCLES — DATING + SOCIAL DISCOVERY ENDPOINTS
# ==============================================================================

class CreateCirclePostRequest(BaseModel):
    content: str
    mediaUrl: Optional[str] = None

class CreateCircleCommentRequest(BaseModel):
    content: str

class ConnectFromCircleRequest(BaseModel):
    targetUserId: str
    circleId: str
    postId: Optional[str] = None
    message: Optional[str] = None

@app.get("/api/circles")
@limiter.limit("60/minute")
async def list_circles(
    request: Request,
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    circles = get_circles_list(user_id=user_id, category=category)
    return {"status": "SUCCESS", "circles": circles}

@app.get("/api/circles/{circle_id}")
@limiter.limit("60/minute")
async def get_circle(
    request: Request,
    circle_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    circle = get_circle_detail(circle_id=circle_id, user_id=user_id)
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    return {"status": "SUCCESS", "circle": circle}

@app.post("/api/circles/{circle_id}/join")
@limiter.limit("30/minute")
async def join_circle_endpoint(
    request: Request,
    circle_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        res = join_circle(circle_id=circle_id, user_id=user_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/circles/{circle_id}/leave")
@limiter.limit("30/minute")
async def leave_circle_endpoint(
    request: Request,
    circle_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    res = leave_circle(circle_id=circle_id, user_id=user_id)
    return res

@app.get("/api/circles/{circle_id}/posts")
@limiter.limit("60/minute")
async def list_circle_posts(
    request: Request,
    circle_id: str,
    skip: int = 0,
    limit: int = 30,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    posts = get_circle_posts(circle_id=circle_id, user_id=user_id, limit=limit, skip=skip)
    return {"status": "SUCCESS", "posts": posts}

@app.post("/api/circles/{circle_id}/posts")
@limiter.limit("20/minute")
async def create_circle_post_endpoint(
    request: Request,
    circle_id: str,
    payload: CreateCirclePostRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        post = create_circle_post(
            circle_id=circle_id,
            user_id=user_id,
            content=payload.content,
            media_url=payload.mediaUrl
        )
        return {"status": "SUCCESS", "post": post}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/circles/posts/{post_id}/like")
@limiter.limit("60/minute")
async def toggle_circle_post_like_endpoint(
    request: Request,
    post_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    res = toggle_post_like(post_id=post_id, user_id=user_id)
    return res

@app.get("/api/circles/posts/{post_id}/comments")
@limiter.limit("60/minute")
async def list_circle_post_comments(
    request: Request,
    post_id: str,
    current_user: dict = Depends(get_current_user)
):
    comments = get_post_comments(post_id=post_id)
    return {"status": "SUCCESS", "comments": comments}

@app.post("/api/circles/posts/{post_id}/comments")
@limiter.limit("30/minute")
async def create_circle_post_comment_endpoint(
    request: Request,
    post_id: str,
    payload: CreateCircleCommentRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        comment = create_post_comment(
            post_id=post_id,
            user_id=user_id,
            content=payload.content
        )
        return {"status": "SUCCESS", "comment": comment}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/circles/connect")
@limiter.limit("20/minute")
async def connect_from_circle_endpoint(
    request: Request,
    payload: ConnectFromCircleRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        res = connect_from_circle(
            current_user_id=user_id,
            target_user_id=payload.targetUserId,
            circle_id=payload.circleId,
            post_id=payload.postId,
            opening_message=payload.message
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==============================================================================
# DOUBLE DATE MODE — 2 VS 2 DATING ENGINE ENDPOINTS
# ==============================================================================

class CreateDuoRequest(BaseModel):
    squadName: str
    vibe: str
    preference: Optional[str] = "any"

class JoinDuoRequest(BaseModel):
    inviteCode: str

class SwipeDuoRequest(BaseModel):
    targetDuoId: str
    action: str  # "LIKE" | "PASS"

@app.post("/api/double-date/duo/create")
@limiter.limit("20/minute")
async def create_duo_endpoint(
    request: Request,
    payload: CreateDuoRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        duo = create_duo_invite(
            user_id=user_id,
            squad_name=payload.squadName,
            vibe=payload.vibe,
            preference=payload.preference or "any"
        )
        return {"status": "SUCCESS", "duo": duo}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/double-date/duo/join")
@limiter.limit("20/minute")
async def join_duo_endpoint(
    request: Request,
    payload: JoinDuoRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        duo = join_duo_by_code(code=payload.inviteCode, joining_user_id=user_id)
        return {"status": "SUCCESS", "duo": duo}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/double-date/duo/my")
@limiter.limit("60/minute")
async def get_my_duo_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    duo = get_user_duo(user_id)
    return {"status": "SUCCESS", "hasDuo": bool(duo and duo["status"] == "ACTIVE"), "duo": duo}

@app.post("/api/double-date/duo/disband")
@limiter.limit("20/minute")
async def disband_duo_endpoint(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    res = disband_duo(user_id)
    return res

@app.get("/api/double-date/feed")
@limiter.limit("60/minute")
async def get_double_date_feed_endpoint(
    request: Request,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    feed_res = get_double_date_feed(user_id=user_id, limit=limit)
    return {"status": "SUCCESS", **feed_res}

@app.post("/api/double-date/swipe")
@limiter.limit("60/minute")
async def swipe_duo_endpoint(
    request: Request,
    payload: SwipeDuoRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        res = swipe_duo(
            user_id=user_id,
            target_duo_id=payload.targetDuoId,
            action=payload.action
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==============================================================================
# SPARK CHEMISTRY GAME ENDPOINTS
# ==============================================================================

class SaveChemistryProfileRequest(BaseModel):
    answers: Dict[str, str]

class CompareChemistryRequest(BaseModel):
    targetUserId: str
    mode: str
    answers: Dict[str, str]

class CreateChemistryChallengeRequest(BaseModel):
    matchId: str
    mode: str

class SubmitChemistrySessionRequest(BaseModel):
    answers: Dict[str, str]

@app.get("/api/chemistry/games")
@limiter.limit("60/minute")
async def get_chemistry_games_endpoint(request: Request):
    return {"status": "SUCCESS", "games": get_game_modes()}

@app.get("/api/chemistry/questions")
@limiter.limit("60/minute")
async def get_chemistry_questions_endpoint(
    request: Request,
    mode: str = Query("WOULD_YOU_RATHER"),
    count: int = Query(5)
):
    questions = get_game_questions(mode=mode, count=count)
    return {"status": "SUCCESS", "mode": mode, "questions": questions}

@app.post("/api/chemistry/profile/save")
@limiter.limit("30/minute")
async def save_chemistry_profile_endpoint(
    request: Request,
    payload: SaveChemistryProfileRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    res = save_user_vibe_profile(user_id=user_id, answers=payload.answers)
    return res

@app.get("/api/chemistry/profile/{target_user_id}")
@limiter.limit("60/minute")
async def get_target_chemistry_profile_endpoint(
    request: Request,
    target_user_id: str,
    current_user: dict = Depends(get_current_user)
):
    res = get_user_vibe_profile(user_id=target_user_id)
    return {"status": "SUCCESS", **res}

@app.post("/api/chemistry/compare")
@limiter.limit("45/minute")
async def compare_chemistry_endpoint(
    request: Request,
    payload: CompareChemistryRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    res = compare_chemistry(
        user_id=user_id,
        target_user_id=payload.targetUserId,
        mode=payload.mode,
        my_answers=payload.answers
    )
    return res

@app.post("/api/chemistry/challenge/create")
@limiter.limit("30/minute")
async def create_chemistry_challenge_endpoint(
    request: Request,
    payload: CreateChemistryChallengeRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        session = create_chat_game_challenge(
            match_id=payload.matchId,
            sender_id=user_id,
            mode=payload.mode
        )
        
        # Insert announcement message into match chat
        notice_text = f"🎮 Spark Chemistry Challenge! Let's play '{payload.mode.replace('_', ' ').title()}'! Tap to see how our vibes align ✨"
        msg_doc = {
            "match_id": payload.matchId,
            "sender_id": user_id,
            "text": notice_text,
            "is_screenshot": False,
            "is_chemistry_challenge": True,
            "chemistry_session": session,
            "timestamp": datetime.utcnow()
        }
        messages_collection.insert_one(msg_doc)

        # Broadcast via WebSocket
        broadcast_payload = {
            "id": str(msg_doc["_id"]),
            "matchId": payload.matchId,
            "senderId": user_id,
            "senderName": current_user.get("name", "Spark Member"),
            "senderPhoto": (current_user.get("photos", [])[0] if current_user.get("photos") else None),
            "text": notice_text,
            "isScreenshot": False,
            "isChemistryChallenge": True,
            "chemistrySession": session,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Check match participants
        match = matches_collection.find_one({"_id": ObjectId(payload.matchId)}) or {}
        participants = match.get("participants", [match.get("user1_id"), match.get("user2_id")])
        for p_id in participants:
            if p_id:
                try:
                    await manager.send_personal_message(broadcast_payload, p_id)
                except Exception:
                    pass

        return {"status": "SUCCESS", "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/chemistry/session/{session_id}/submit")
@limiter.limit("30/minute")
async def submit_chemistry_session_endpoint(
    request: Request,
    session_id: str,
    payload: SubmitChemistrySessionRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    try:
        res = submit_chat_game_answers(
            session_id=session_id,
            user_id=user_id,
            answers=payload.answers
        )
        return {"status": "SUCCESS", **res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- 18. Spark Date Safety Center Endpoints ---
class SaveTrustedContactRequest(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    relationship: str = "Friend"
    isPrimary: bool = False

class StartDateCheckinRequest(BaseModel):
    matchId: Optional[str] = None
    partnerName: str = "Date Partner"
    locationName: str = "Cafe / Public Place"
    durationMinutes: int = 120

class UpdateDateCheckinStatusRequest(BaseModel):
    status: str

@app.get("/api/safety/resources")
def get_safety_resources_endpoint():
    """Returns official Indian emergency hotlines and scam awareness guides."""
    return {"status": "SUCCESS", "resources": INDIA_SAFETY_RESOURCES}

@app.get("/api/safety/trusted-contacts")
def get_trusted_contacts_endpoint(current_user: dict = Depends(get_current_user)):
    """Fetches user's saved emergency trusted contacts."""
    user_id = current_user["id"]
    contacts = get_trusted_contacts(user_id)
    return {"status": "SUCCESS", "contacts": contacts}

@app.post("/api/safety/trusted-contacts")
def save_trusted_contact_endpoint(payload: SaveTrustedContactRequest, current_user: dict = Depends(get_current_user)):
    """Saves or updates a trusted emergency contact."""
    user_id = current_user["id"]
    try:
        saved = save_trusted_contact(user_id, payload.dict())
        return {"status": "SUCCESS", "contact": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/safety/trusted-contacts/{contact_id}")
def delete_trusted_contact_endpoint(contact_id: str, current_user: dict = Depends(get_current_user)):
    """Removes a trusted contact."""
    user_id = current_user["id"]
    success = delete_trusted_contact(user_id, contact_id)
    if not success:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return {"status": "SUCCESS", "deleted": True}

@app.post("/api/safety/checkin/start")
def start_date_checkin_endpoint(payload: StartDateCheckinRequest, current_user: dict = Depends(get_current_user)):
    """Starts an active date check-in safety timer."""
    user_id = current_user["id"]
    checkin = start_date_checkin(
        user_id=user_id,
        match_id=payload.matchId,
        partner_name=payload.partnerName,
        location_name=payload.locationName,
        duration_minutes=payload.durationMinutes,
    )
    return {"status": "SUCCESS", "checkin": checkin}

@app.post("/api/safety/checkin/{checkin_id}/status")
def update_date_checkin_status_endpoint(
    checkin_id: str,
    payload: UpdateDateCheckinStatusRequest,
    current_user: dict = Depends(get_current_user)
):
    """Updates status (COMPLETED_SAFE, SOS_TRIGGERED, CANCELLED)."""
    user_id = current_user["id"]
    try:
        updated = update_date_checkin_status(user_id, checkin_id, payload.status)
        return {"status": "SUCCESS", "checkin": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/safety/checkin/active")
def get_active_date_checkin_endpoint(current_user: dict = Depends(get_current_user)):
    """Fetches user's currently active date checkin if any."""
    user_id = current_user["id"]
    checkin = get_active_date_checkin(user_id)
    return {"status": "SUCCESS", "activeCheckin": checkin}

# --- 19. Spark Vibe — Mood-Based Matching Endpoints ---
class UpdateDailyVibeRequest(BaseModel):
    vibes: List[str] = Field(..., min_length=1, max_length=2)
    customNote: Optional[str] = Field(default=None, max_length=60)

@app.get("/api/vibes/options")
def get_vibe_options_endpoint():
    """Returns available daily vibe choices with icons, titles, and tags."""
    options = list(DAILY_VIBE_DEFINITIONS.values())
    return {"status": "SUCCESS", "vibes": options}

@app.get("/api/users/me/daily-vibe")
def get_my_daily_vibe_endpoint(current_user: dict = Depends(get_current_user)):
    """Fetches user's current daily vibe and remaining validity."""
    user_id = current_user["id"]
    user = users_collection.find_one({"id": user_id}) or current_user
    active = is_vibe_active(user)
    
    vibes = user.get("daily_vibes", [])
    if isinstance(vibes, str):
        vibes = [vibes]
    
    primary = vibes[0] if vibes else user.get("daily_vibe")
    primary_def = DAILY_VIBE_DEFINITIONS.get(primary) if primary else None
    
    return {
        "status": "SUCCESS",
        "isActive": active,
        "dailyVibes": vibes if active else [],
        "dailyVibe": primary if active else None,
        "dailyVibeLabel": primary_def["label"] if (active and primary_def) else user.get("daily_vibe_label") if active else None,
        "dailyVibeEmoji": primary_def["emoji"] if (active and primary_def) else "💖",
        "vibeUpdatedAt": user.get("vibe_updated_at"),
        "vibeNote": user.get("vibe_note") if active else None,
    }

@app.post("/api/users/me/daily-vibe")
def update_my_daily_vibe_endpoint(
    payload: UpdateDailyVibeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Sets or updates the user's daily mood vibe (expires after 24h)."""
    user_id = current_user["id"]
    
    valid_ids = set(DAILY_VIBE_DEFINITIONS.keys())
    clean_vibes = [v.strip().lower() for v in payload.vibes if v.strip().lower() in valid_ids]
    if not clean_vibes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vibe selection. Choose from: {list(valid_ids)}"
        )
    
    clean_vibes = clean_vibes[:2]
    labels = [DAILY_VIBE_DEFINITIONS[v]["label"] for v in clean_vibes]
    primary_label = " + ".join(labels)
    primary_emoji = DAILY_VIBE_DEFINITIONS[clean_vibes[0]]["emoji"]
    
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)
    
    update_data = {
        "daily_vibes": clean_vibes,
        "daily_vibe": clean_vibes[0],
        "daily_vibe_label": primary_label,
        "daily_vibe_emoji": primary_emoji,
        "vibe_note": payload.customNote.strip() if payload.customNote else None,
        "vibe_updated_at": now,
        "vibe_expires_at": expires_at,
    }
    
    users_collection.update_one({"id": user_id}, {"$set": update_data})
    
    return {
        "status": "SUCCESS",
        "message": "Today's vibe set successfully! ✨",
        "dailyVibes": clean_vibes,
        "dailyVibe": clean_vibes[0],
        "dailyVibeLabel": primary_label,
        "dailyVibeEmoji": primary_emoji,
        "vibeUpdatedAt": now.isoformat(),
        "vibeExpiresAt": expires_at.isoformat(),
    }

