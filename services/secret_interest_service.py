# backend/services/secret_interest_service.py
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bson import ObjectId

from database import (
    secret_interests_collection,
    secret_matches_collection,
    users_collection,
    matches_collection,
    messages_collection,
    blocks_collection,
)
from services.notification_service import create_notification

CYCLE_DURATION_DAYS = 5

# Curated catalog of expressive hidden/secret interests
SECRET_INTERESTS_CATALOG: List[Dict[str, str]] = [
    # Sports & Gaming
    {"id": "cricket", "name": "Cricket", "emoji": "🏏", "category": "Gaming & Sports"},
    {"id": "gaming", "name": "Gaming", "emoji": "🎮", "category": "Gaming & Sports"},
    {"id": "chess", "name": "Chess", "emoji": "♟️", "category": "Gaming & Sports"},
    {"id": "football", "name": "Football / F1", "emoji": "⚽", "category": "Gaming & Sports"},
    {"id": "badminton", "name": "Badminton", "emoji": "🏸", "category": "Gaming & Sports"},
    {"id": "board_games", "name": "Board Games", "emoji": "🎲", "category": "Gaming & Sports"},

    # Pop Culture & Fandoms
    {"id": "harry_potter", "name": "Harry Potter", "emoji": "⚡", "category": "Fandoms"},
    {"id": "anime", "name": "Anime & Manga", "emoji": "🍥", "category": "Fandoms"},
    {"id": "marvel_dc", "name": "Marvel & DC", "emoji": "🦸", "category": "Fandoms"},
    {"id": "kpop_kdrama", "name": "K-Pop & K-Drama", "emoji": "🫰", "category": "Fandoms"},
    {"id": "sci_fi", "name": "Sci-Fi & Space", "emoji": "🌌", "category": "Fandoms"},

    # Food & Nightlife
    {"id": "street_food", "name": "Street Food", "emoji": "🍲", "category": "Food & Night"},
    {"id": "late_night_drives", "name": "Late Night Drives", "emoji": "🌃", "category": "Food & Night"},
    {"id": "coffee_cafes", "name": "Coffee & Hidden Cafes", "emoji": "☕", "category": "Food & Night"},
    {"id": "cooking_baking", "name": "Cooking & Baking", "emoji": "🍳", "category": "Food & Night"},
    {"id": "speakeasies", "name": "Hidden Speakeasies", "emoji": "🍸", "category": "Food & Night"},

    # Lifestyle & Passions
    {"id": "travel", "name": "Travel & Roadtrips", "emoji": "✈️", "category": "Lifestyle"},
    {"id": "astronomy", "name": "Astronomy & Stargazing", "emoji": "🔭", "category": "Lifestyle"},
    {"id": "indie_music", "name": "Indie Music & Vinyl", "emoji": "🎸", "category": "Lifestyle"},
    {"id": "poetry_writing", "name": "Poetry & Writing", "emoji": "✍️", "category": "Lifestyle"},
    {"id": "photography", "name": "Film Photography", "emoji": "📸", "category": "Lifestyle"},
    {"id": "thrift_fashion", "name": "Thrift & Vintage", "emoji": "🛍️", "category": "Lifestyle"},
    {"id": "tech_coding", "name": "Tech & Coding", "emoji": "💻", "category": "Lifestyle"},
    {"id": "standup_comedy", "name": "Standup Comedy", "emoji": "🎙️", "category": "Lifestyle"},
]

CATALOG_BY_ID = {item["id"]: item for item in SECRET_INTERESTS_CATALOG}
CATALOG_BY_NAME = {item["name"].lower(): item for item in SECRET_INTERESTS_CATALOG}

def get_secret_interests_catalog() -> List[Dict[str, str]]:
    return SECRET_INTERESTS_CATALOG

def normalize_interest_name(raw: str) -> str:
    """Returns canonical display name with emoji if possible."""
    low = raw.strip().lower()
    if low in CATALOG_BY_ID:
        return CATALOG_BY_ID[low]["name"]
    if low in CATALOG_BY_NAME:
        return CATALOG_BY_NAME[low]["name"]
    for item in SECRET_INTERESTS_CATALOG:
        if item["name"].lower() in low or low in item["name"].lower():
            return item["name"]
    return raw.strip()

def get_user_secret_interests(user_id: str) -> Dict[str, Any]:
    """Fetches user's saved secret interests and 5-day cycle drop timer."""
    record = secret_interests_collection.find_one({"user_id": user_id}) or {}
    interests = record.get("interests", [])
    last_drop_at = record.get("last_drop_at")
    
    now = datetime.utcnow()
    cycle_duration_seconds = CYCLE_DURATION_DAYS * 86400
    
    if last_drop_at:
        elapsed = (now - last_drop_at).total_seconds()
        remaining_seconds = max(0, int(cycle_duration_seconds - elapsed))
        next_drop_at = (last_drop_at + timedelta(days=CYCLE_DURATION_DAYS)).isoformat()
    else:
        remaining_seconds = 0
        next_drop_at = now.isoformat()
        
    return {
        "interests": interests,
        "count": len(interests),
        "max_allowed": 5,
        "is_ready_for_drop": remaining_seconds == 0,
        "next_drop_in_seconds": remaining_seconds,
        "next_drop_at": next_drop_at,
        "cycle_days": CYCLE_DURATION_DAYS
    }

def save_user_secret_interests(user_id: str, raw_interests: List[str]) -> Dict[str, Any]:
    """
    Saves up to 5 secret interests for user.
    If 5-day cycle is ready, automatically triggers discovery scan.
    """
    cleaned: List[str] = []
    for item in raw_interests[:5]:
        norm = normalize_interest_name(item)
        if norm and norm not in cleaned:
            cleaned.append(norm)

    now = datetime.utcnow()
    secret_interests_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "interests": cleaned,
                "updated_at": now
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now,
                "last_drop_at": None
            }
        },
        upsert=True
    )

    # Trigger scan if eligible
    trigger_secret_match_scan(user_id)
    return get_user_secret_interests(user_id)

def trigger_secret_match_scan(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Enforces 5-day cadence:
    If user already has an active, unexpired 5-day match, reuse it.
    Otherwise finds the best nearby partner sharing 2+ (ideally 3+) interests.
    """
    now = datetime.utcnow()
    
    # 1. Check existing active cycle match for user
    active_match = secret_matches_collection.find_one({
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "cycle_expires_at": {"$gt": now},
        "status": {"$in": ["PENDING", "HALF_REVEALED", "REVEALED"]}
    })
    if active_match:
        return active_match

    # 2. Check 5-day cycle timer on secret_interests
    user_interest_doc = secret_interests_collection.find_one({"user_id": user_id}) or {}
    my_interests = user_interest_doc.get("interests", [])
    if len(my_interests) < 2:
        return None  # Needs at least 2 interests chosen

    last_drop = user_interest_doc.get("last_drop_at")
    if last_drop and (now - last_drop).total_seconds() < CYCLE_DURATION_DAYS * 86400:
        return None  # Still waiting for 5-day cooldown

    # 3. Retrieve user profile for location/gender preferences
    current_user = users_collection.find_one({"id": user_id}) or {}
    blocked_ids = set()
    for b in blocks_collection.find({"$or": [{"blocker_id": user_id}, {"blocked_id": user_id}]}):
        blocked_ids.add(b.get("blocker_id"))
        blocked_ids.add(b.get("blocked_id"))

    # Candidates with secret interests
    cand_cursor = secret_interests_collection.find({
        "user_id": {"$ne": user_id, "$nin": list(blocked_ids)}
    })

    best_candidate_id = None
    best_common: List[str] = []

    for cand_doc in cand_cursor:
        cand_id = cand_doc.get("user_id")
        cand_interests = cand_doc.get("interests", [])
        common = [i for i in my_interests if i in cand_interests]
        if len(common) >= 2:
            if len(common) > len(best_common):
                best_common = common
                best_candidate_id = cand_id

    if not best_candidate_id or len(best_common) < 2:
        return None

    # 4. Create secret match record with 5-day expiration
    pair_key = f"{min(user_id, best_candidate_id)}_{max(user_id, best_candidate_id)}"
    expires_at = now + timedelta(days=CYCLE_DURATION_DAYS)

    match_doc = {
        "pair_key": pair_key,
        "user1_id": user_id,
        "user2_id": best_candidate_id,
        "common_interests": best_common,
        "common_count": len(best_common),
        "user1_consented": False,
        "user2_consented": False,
        "is_revealed": False,
        "status": "PENDING",
        "match_id": None,
        "cycle_started_at": now,
        "cycle_expires_at": expires_at,
        "created_at": now
    }

    # Upsert to prevent duplicate pair records
    secret_matches_collection.update_one(
        {"pair_key": pair_key},
        {"$set": match_doc},
        upsert=True
    )

    # Update last_drop_at for user
    secret_interests_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_drop_at": now}}
    )

    # 5. Dispatch Anonymous Teaser In-App Notification to BOTH users
    # "You and someone nearby share 3 interests. Want to discover who?"
    tease_body = f"You and someone nearby share {len(best_common)} interests. Want to discover who? 🤫"
    for uid in (user_id, best_candidate_id):
        try:
            create_notification(
                user_id=uid,
                notif_type="SECRET_MATCH",
                title="Secret Interest Match 🤫",
                body=tease_body,
                sender_id=None,
                sender_name="Someone nearby",
                sender_photo="",
                extra_data={
                    "pair_key": pair_key,
                    "shared_count": len(best_common),
                    "common_interests": best_common
                }
            )
        except Exception as e:
            print(f"[SECRET_INTERESTS] Notification dispatch error: {e}")

    return match_doc

def get_secret_matches_for_user(user_id: str) -> Dict[str, Any]:
    """
    Returns active 5-day secret match for user with STRICT ANONYMIZATION.
    Zero personal identity is exposed unless is_revealed is True!
    """
    now = datetime.utcnow()
    active = secret_matches_collection.find_one({
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "cycle_expires_at": {"$gt": now},
        "status": {"$in": ["PENDING", "HALF_REVEALED", "REVEALED"]}
    })

    user_info = get_user_secret_interests(user_id)

    if not active:
        return {
            "has_active_match": False,
            "match": None,
            "next_drop_in_seconds": user_info["next_drop_in_seconds"],
            "next_drop_at": user_info["next_drop_at"],
            "interests": user_info["interests"]
        }

    is_user1 = active["user1_id"] == user_id
    opponent_id = active["user2_id"] if is_user1 else active["user1_id"]
    my_consent = active["user1_consented"] if is_user1 else active["user2_consented"]
    their_consent = active["user2_consented"] if is_user1 else active["user1_consented"]
    is_revealed = active.get("is_revealed", False)
    
    expires_at = active.get("cycle_expires_at", now + timedelta(days=CYCLE_DURATION_DAYS))
    remaining_seconds = max(0, int((expires_at - now).total_seconds()))

    common = active.get("common_interests", [])
    
    # Map emoji to common interests
    formatted_interests = []
    for c in common:
        matched_item = CATALOG_BY_NAME.get(c.lower())
        emoji = matched_item["emoji"] if matched_item else "✨"
        formatted_interests.append({"name": c, "emoji": emoji})

    # STRICT ANONYMIZATION:
    if not is_revealed:
        opponent_data = {
            "id": "anonymous_spark",
            "name": "Secret Spark ✨",
            "age": None,
            "bio": "Shared interests detected nearby. Both must consent to reveal identities.",
            "photos": [],
            "location_name": "Nearby",
            "is_anonymized": True
        }
    else:
        # Fully revealed: load actual user profile
        opp_user = users_collection.find_one({"id": opponent_id}) or {}
        opponent_data = {
            "id": opp_user.get("id"),
            "name": opp_user.get("name", "Spark Member"),
            "age": opp_user.get("age"),
            "bio": opp_user.get("bio", ""),
            "photos": opp_user.get("photos", []),
            "location_name": opp_user.get("locationName", "Nearby"),
            "is_anonymized": False
        }

    return {
        "has_active_match": True,
        "match": {
            "id": str(active["_id"]),
            "pair_key": active["pair_key"],
            "shared_count": len(common),
            "common_interests": common,
            "formatted_interests": formatted_interests,
            "my_consent": my_consent,
            "their_consent": their_consent,
            "is_revealed": is_revealed,
            "status": active.get("status", "PENDING"),
            "match_id": active.get("match_id"),
            "remaining_seconds": remaining_seconds,
            "expires_at": expires_at.isoformat(),
            "opponent": opponent_data
        },
        "next_drop_in_seconds": remaining_seconds,
        "next_drop_at": expires_at.isoformat(),
        "interests": user_info["interests"]
    }

def consent_to_reveal(user_id: str, match_record_id: str) -> Dict[str, Any]:
    """
    Opt-in consent for reveal.
    If both consent -> is_revealed=True, creates official match and opens chat.
    If only one -> updates state to HALF_REVEALED and notifies partner anonymously.
    """
    now = datetime.utcnow()
    try:
        obj_id = ObjectId(match_record_id)
        active = secret_matches_collection.find_one({"_id": obj_id})
    except Exception:
        active = secret_matches_collection.find_one({"pair_key": match_record_id})

    if not active:
        raise ValueError("Secret match record not found or expired.")

    is_user1 = active["user1_id"] == user_id
    opponent_id = active["user2_id"] if is_user1 else active["user1_id"]

    consent_field = "user1_consented" if is_user1 else "user2_consented"
    other_consented = active["user2_consented"] if is_user1 else active["user1_consented"]

    # If already revealed, return current state
    if active.get("is_revealed"):
        return get_secret_matches_for_user(user_id)

    # Check if this consent makes it mutual
    if other_consented:
        # MUTUAL CONSENT ACHIEVED! Reveal both profiles and create permanent match
        match_pair_key = f"{min(user_id, opponent_id)}_{max(user_id, opponent_id)}"
        
        # 1. Create or get match in matches_collection
        existing_match = matches_collection.find_one({"pair_key": match_pair_key})
        if not existing_match:
            new_match = {
                "pair_key": match_pair_key,
                "user1_id": active["user1_id"],
                "user2_id": active["user2_id"],
                "source": "SECRET_INTERESTS",
                "matched_at": now,
                "created_at": now,
                "is_permanent": True,
                "first_move_made": True
            }
            inserted = matches_collection.insert_one(new_match)
            official_match_id = str(inserted.inserted_id)
        else:
            official_match_id = str(existing_match["_id"])

        # 2. Insert opening icebreaker message
        common_text = ", ".join(active.get("common_interests", []))
        icebreaker = f"✨ You both unlocked each other through Secret Interests: {common_text}! Say hi and discover what else you have in common! 🎉"
        messages_collection.insert_one({
            "match_id": official_match_id,
            "sender_id": "system",
            "receiver_id": "both",
            "text": icebreaker,
            "type": "SECRET_REVEAL",
            "created_at": now
        })

        # 3. Update secret_matches_collection
        secret_matches_collection.update_one(
            {"_id": active["_id"]},
            {
                "$set": {
                    consent_field: True,
                    "is_revealed": True,
                    "status": "REVEALED",
                    "match_id": official_match_id,
                    "revealed_at": now
                }
            }
        )

        # 4. Notify both users about mutual reveal
        for uid in (user_id, opponent_id):
            try:
                other_uid = opponent_id if uid == user_id else user_id
                other_u = users_collection.find_one({"id": other_uid}) or {}
                create_notification(
                    user_id=uid,
                    notif_type="MATCH",
                    title="Mutual Secret Match Unlocked! 🎉",
                    body=f"You and {other_u.get('name', 'your match')} both agreed to reveal! Start chatting now.",
                    sender_id=other_uid,
                    sender_name=other_u.get("name", "Your Match"),
                    sender_photo=other_u.get("photos", [""])[0] if other_u.get("photos") else "",
                    match_id=official_match_id
                )
            except Exception as e:
                print(f"[SECRET_INTERESTS] Mutual reveal notification error: {e}")

    else:
        # Only one consented so far
        secret_matches_collection.update_one(
            {"_id": active["_id"]},
            {
                "$set": {
                    consent_field: True,
                    "status": "HALF_REVEALED"
                }
            }
        )

        # Anonymously nudge opponent
        try:
            create_notification(
                user_id=opponent_id,
                notif_type="SECRET_MATCH",
                title="Someone Wants to Reveal! 🔓",
                body=f"Someone sharing {len(active.get('common_interests', []))} secret interests with you agreed to reveal! Tap to unlock.",
                sender_id=None,
                sender_name="Someone nearby",
                sender_photo="",
                extra_data={"pair_key": active["pair_key"]}
            )
        except Exception as e:
            print(f"[SECRET_INTERESTS] Consent nudge error: {e}")

    return get_secret_matches_for_user(user_id)

def decline_secret_match(user_id: str, match_record_id: str) -> Dict[str, Any]:
    """Declines candidate and marks status DECLINED."""
    try:
        obj_id = ObjectId(match_record_id)
        query = {"_id": obj_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}]}
    except Exception:
        query = {"pair_key": match_record_id, "$or": [{"user1_id": user_id}, {"user2_id": user_id}]}

    secret_matches_collection.update_one(
        query,
        {"$set": {"status": "DECLINED"}}
    )
    return get_secret_matches_for_user(user_id)
