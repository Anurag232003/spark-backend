"""
MongoDB Document Models & Schemas for Spark Dating Backend.
Pure MongoDB / BSON Architecture (No SQLite / SQLAlchemy).

This module defines the canonical typed MongoDB document schemas, subdocuments,
and domain models stored across the MongoDB Atlas collections.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Annotated
from enum import Enum
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer


# Custom type for handling MongoDB BSON ObjectId seamlessly with Pydantic v2
def validate_object_id(v: Any) -> str:
    if isinstance(v, str):
        return v
    return str(v)

PyObjectId = Annotated[
    str,
    BeforeValidator(validate_object_id),
    PlainSerializer(lambda x: str(x), return_type=str)
]


# =====================================================================
# Enums
# =====================================================================

class GenderEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class InteractionType(str, Enum):
    LIKE = "LIKE"
    PASS = "PASS"


class MatchStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNMATCHED = "UNMATCHED"


class ReportReason(str, Enum):
    INAPPROPRIATE_PHOTOS = "INAPPROPRIATE_PHOTOS"
    FAKE_PROFILE = "FAKE_PROFILE"
    HARASSMENT = "HARASSMENT"
    SPAM = "SPAM"
    UNDERAGE = "UNDERAGE"
    HATE_SPEECH = "HATE_SPEECH"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    INVESTIGATING = "INVESTIGATING"
    WARNED = "WARNED"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"
    DISMISSED = "DISMISSED"
    RESOLVED = "RESOLVED"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class ModerationActionType(str, Enum):
    WARN = "WARN"
    SUSPEND = "SUSPEND"
    UNSUSPEND = "UNSUSPEND"
    DELETE = "DELETE"
    DISMISS = "DISMISS"
    RESOLVE = "RESOLVE"


# =====================================================================
# Subdocuments & GeoJSON
# =====================================================================

class GeoPoint(BaseModel):
    """GeoJSON Point geometry for 2dsphere indexing and geospatial distance ranking."""
    type: str = "Point"
    coordinates: List[float] = Field(
        ...,
        description="[longitude, latitude] pair in decimal degrees"
    )


class PromptItem(BaseModel):
    """Interactive profile prompt question & answer."""
    id: Optional[str] = Field(default=None, max_length=50)
    question: str = Field(..., min_length=1, max_length=200)
    answer: str = Field(..., min_length=1, max_length=300)


class UserWarning(BaseModel):
    """Moderation warning recorded on a user profile."""
    warning_id: str
    admin_id: str
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =====================================================================
# MongoDB Collection Document Schemas
# =====================================================================

class UserDocument(BaseModel):
    """
    MongoDB Document Schema for 'users' collection.
    Indexes:
      - phone: unique, sparse
      - location: 2dsphere, sparse
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    phone: str
    name: str
    age: int
    gender: str
    gender_preference: List[str] = Field(default_factory=lambda: ["female"])
    bio: str = ""
    photos: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    prompts: List[PromptItem] = Field(default_factory=list)
    location: Optional[GeoPoint] = None
    locationName: Optional[str] = None
    verified: bool = False
    is_active: bool = True
    role: str = "user"
    warnings: List[UserWarning] = Field(default_factory=list)
    is_suspended: bool = False
    suspension_reason: Optional[str] = None
    suspended_until: Optional[datetime] = None
    last_active: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class OTPStoreDocument(BaseModel):
    """
    MongoDB Document Schema for 'otp_store' collection.
    Stores cryptographically salted/hashed OTPs with expiry and attempt rate limiting.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    phone: str
    otp_hash: str
    attempts: int = 0
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class InteractionDocument(BaseModel):
    """
    MongoDB Document Schema for 'interactions' collection.
    Indexes:
      - (from_user_id, target_user_id): unique
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    from_user_id: str
    target_user_id: str
    type: InteractionType
    target_item_type: Optional[str] = None
    target_item_id: Optional[str] = None
    comment: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class MatchDocument(BaseModel):
    """
    MongoDB Document Schema for 'matches' collection.
    Indexes:
      - pair_key: unique, sparse
      - (user1_id, status)
      - (user2_id, status)
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user1_id: str
    user2_id: str
    pair_key: str
    status: MatchStatus = MatchStatus.ACTIVE
    matched_at: datetime = Field(default_factory=datetime.utcnow)
    first_move_by: Optional[str] = None
    first_move_deadline: Optional[datetime] = None
    first_move_made: bool = False
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
    }


class MessageDocument(BaseModel):
    """
    MongoDB Document Schema for 'messages' collection.
    Indexes:
      - (match_id, timestamp)
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    match_id: str
    sender_id: str
    recipient_id: str
    content: str
    read: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class BlockDocument(BaseModel):
    """
    MongoDB Document Schema for 'blocks' collection.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    blocker_id: str
    blocked_id: str
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class ReportDocument(BaseModel):
    """
    MongoDB Document Schema for 'reports' collection.
    Indexes:
      - (status, created_at DESC)
      - reported_user_id
      - (reporter_user_id, reported_user_id): unique
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    reporter_user_id: str
    reported_user_id: str
    reason: ReportReason
    details: Optional[str] = None
    status: ReportStatus = ReportStatus.PENDING_REVIEW
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class ModerationActionDocument(BaseModel):
    """
    MongoDB Document Schema for 'moderation_actions' collection.
    Audit log of all actions taken by administrators.
    Indexes:
      - report_id
      - target_user_id
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    report_id: Optional[str] = None
    admin_id: str
    target_user_id: str
    action: ModerationActionType
    notes: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class RefreshTokenDocument(BaseModel):
    """
    MongoDB Document Schema for 'refresh_tokens' collection.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    token_hash: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
    }


class UpdateDailyVibeRequest(BaseModel):
    """
    Request model to update user's daily vibe (mood-based matching).
    """
    vibes: List[str] = Field(..., min_length=1, max_length=2, description="List of 1 or 2 selected daily vibe IDs")
    customNote: Optional[str] = Field(default=None, max_length=60, description="Optional brief daily mood thought")

