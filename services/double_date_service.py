# backend/services/double_date_service.py
"""
Spark Double Date Mode — 2 vs 2 Dating Engine.
Enables friends to pair up into Squads/Duos, discover other friend pairs,
swipe together, match into 4-person group chats, and plan double dates.
"""

import random
import string
from datetime import datetime
from bson import ObjectId
from typing import Optional, List, Dict, Any

from database import (
    duos_collection,
    duo_interactions_collection,
    users_collection,
    matches_collection,
    messages_collection,
)

def _generate_duo_invite_code() -> str:
    """Generates a clean, readable 6-character squad code like SPARK-DUO-7K9A"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=4))
    return f"SPARK-DUO-{code}"

def _format_user_summary(user: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts a clean public profile summary for duo display"""
    photos = user.get("photos", [])
    photo = photos[0] if photos else ""
    return {
        "id": user.get("id", ""),
        "name": user.get("name", "Spark Member"),
        "age": user.get("age", 22),
        "bio": user.get("bio", ""),
        "photo": photo,
        "photos": photos,
        "isPhotoVerified": user.get("is_photo_verified") or user.get("isPhotoVerified") or False,
        "occupation": user.get("occupation", ""),
        "interests": user.get("interests", []),
        "locationName": user.get("locationName", ""),
    }

def get_user_duo(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Finds any ACTIVE or PENDING squad/duo for the given user.
    """
    duo = duos_collection.find_one({
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "status": {"$in": ["PENDING", "ACTIVE"]}
    })
    if not duo:
        return None

    u1 = users_collection.find_one({"id": duo.get("user1_id")})
    u2 = users_collection.find_one({"id": duo.get("user2_id")}) if duo.get("user2_id") else None

    return {
        "id": str(duo["_id"]),
        "inviteCode": duo.get("invite_code", ""),
        "squadName": duo.get("squad_name", "Dynamic Duo"),
        "vibe": duo.get("vibe", "Chill & Fun"),
        "preference": duo.get("preference", "any"),
        "status": duo.get("status", "PENDING"),
        "isCreator": duo.get("user1_id") == user_id,
        "createdAt": duo.get("created_at", datetime.utcnow()).isoformat(),
        "user1": _format_user_summary(u1) if u1 else None,
        "user2": _format_user_summary(u2) if u2 else None,
    }

def create_duo_invite(
    user_id: str,
    squad_name: str,
    vibe: str,
    preference: str = "any"
) -> Dict[str, Any]:
    """
    Creates a new Double Date squad and returns the invite code for a friend.
    """
    existing = get_user_duo(user_id)
    if existing:
        if existing["status"] == "ACTIVE":
            raise ValueError(f"You already have an active squad: {existing['squadName']}. Disband it before creating a new one.")
        elif existing["status"] == "PENDING" and existing["isCreator"]:
            # Update existing pending squad
            duos_collection.update_one(
                {"_id": ObjectId(existing["id"])},
                {"$set": {
                    "squad_name": squad_name.strip() or "Dynamic Duo",
                    "vibe": vibe.strip() or "Chill & Fun",
                    "preference": preference,
                    "updated_at": datetime.utcnow()
                }}
            )
            return get_user_duo(user_id) or {}

    invite_code = _generate_duo_invite_code()
    # Ensure uniqueness
    while duos_collection.find_one({"invite_code": invite_code, "status": "PENDING"}):
        invite_code = _generate_duo_invite_code()

    duo_doc = {
        "invite_code": invite_code,
        "squad_name": squad_name.strip() or "Dynamic Duo",
        "vibe": vibe.strip() or "Chill & Fun",
        "preference": preference,
        "user1_id": user_id,
        "user2_id": None,
        "status": "PENDING",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    inserted = duos_collection.insert_one(duo_doc)
    duo_doc["_id"] = inserted.inserted_id

    return get_user_duo(user_id) or {}

def join_duo_by_code(code: str, joining_user_id: str) -> Dict[str, Any]:
    """
    Friend enters the invite code to join the squad and activate the duo.
    """
    clean_code = code.strip().upper()
    duo = duos_collection.find_one({"invite_code": clean_code, "status": "PENDING"})
    if not duo:
        raise ValueError("Invalid or expired Duo Invite Code. Please check with your friend.")

    if duo.get("user1_id") == joining_user_id:
        raise ValueError("You cannot join your own squad with your own invite code!")

    # Check if joining user is in another squad
    existing = get_user_duo(joining_user_id)
    if existing:
        raise ValueError(f"You are already in squad '{existing['squadName']}'. Please leave it first.")

    duos_collection.update_one(
        {"_id": duo["_id"]},
        {"$set": {
            "user2_id": joining_user_id,
            "status": "ACTIVE",
            "activated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }}
    )

    return get_user_duo(joining_user_id) or {}

def disband_duo(user_id: str) -> Dict[str, Any]:
    """
    Leaves or disbands user's active/pending squad.
    """
    duo = duos_collection.find_one({
        "$or": [{"user1_id": user_id}, {"user2_id": user_id}],
        "status": {"$in": ["PENDING", "ACTIVE"]}
    })
    if not duo:
        return {"status": "SUCCESS", "message": "No active squad to disband."}

    duos_collection.update_one(
        {"_id": duo["_id"]},
        {"$set": {"status": "DISBANDED", "disbanded_at": datetime.utcnow()}}
    )
    return {"status": "SUCCESS", "message": "Squad disbanded successfully."}

def get_double_date_feed(user_id: str, limit: int = 20) -> Dict[str, Any]:
    """
    Returns candidate Duos for the 2 vs 2 swipe feed.
    """
    my_duo = get_user_duo(user_id)
    if not my_duo or my_duo["status"] != "ACTIVE":
        return {
            "hasDuo": False,
            "duo": my_duo,
            "candidates": [],
            "message": "You need an active Wingman/Wingwoman duo to explore 2 vs 2 Double Dating!"
        }

    my_duo_id = my_duo["id"]
    u1_id = my_duo["user1"]["id"]
    u2_id = my_duo["user2"]["id"]

    # Preload swiped target duos
    swiped = duo_interactions_collection.find({"from_duo_id": my_duo_id})
    swiped_ids = {str(s.get("target_duo_id")) for s in swiped}

    # Query active candidate duos
    query: Dict[str, Any] = {
        "status": "ACTIVE",
        "_id": {"$ne": ObjectId(my_duo_id)},
        "user1_id": {"$nin": [u1_id, u2_id]},
        "user2_id": {"$nin": [u1_id, u2_id]},
    }

    all_duos = list(duos_collection.find(query).limit(limit * 2))
    candidates = []

    for d in all_duos:
        d_id = str(d["_id"])
        if d_id in swiped_ids:
            continue

        cand_u1 = users_collection.find_one({"id": d.get("user1_id")})
        cand_u2 = users_collection.find_one({"id": d.get("user2_id")})

        if not cand_u1 or not cand_u2:
            continue

        candidates.append({
            "duoId": d_id,
            "squadName": d.get("squad_name", "Dynamic Duo"),
            "vibe": d.get("vibe", "Chill & Fun"),
            "preference": d.get("preference", "any"),
            "users": [
                _format_user_summary(cand_u1),
                _format_user_summary(cand_u2),
            ]
        })

        if len(candidates) >= limit:
            break

    return {
        "hasDuo": True,
        "duo": my_duo,
        "candidates": candidates,
    }

def swipe_duo(user_id: str, target_duo_id: str, action: str) -> Dict[str, Any]:
    """
    Performs a duo swipe (LIKE or PASS) on a candidate duo.
    If reciprocal LIKE exists, creates a 4-person match and group chat!
    """
    my_duo = get_user_duo(user_id)
    if not my_duo or my_duo["status"] != "ACTIVE":
        raise ValueError("You must be in an active squad to swipe on double dates.")

    my_duo_id = my_duo["id"]
    action_clean = action.strip().upper()
    if action_clean not in ["LIKE", "PASS"]:
        raise ValueError("Invalid swipe action. Must be LIKE or PASS.")

    # Record interaction
    duo_interactions_collection.update_one(
        {"from_duo_id": my_duo_id, "target_duo_id": target_duo_id},
        {"$set": {
            "from_duo_id": my_duo_id,
            "target_duo_id": target_duo_id,
            "action": action_clean,
            "swiped_by": user_id,
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )

    if action_clean == "PASS":
        return {"status": "SUCCESS", "isMatch": False}

    # Check for reciprocal LIKE
    reciprocal = duo_interactions_collection.find_one({
        "from_duo_id": target_duo_id,
        "target_duo_id": my_duo_id,
        "action": "LIKE"
    })

    if reciprocal:
        # Fetch target duo details
        target_duo = duos_collection.find_one({"_id": ObjectId(target_duo_id)})
        if not target_duo:
            return {"status": "SUCCESS", "isMatch": False}

        u1 = my_duo["user1"]["id"]
        u2 = my_duo["user2"]["id"]
        u3 = target_duo.get("user1_id")
        u4 = target_duo.get("user2_id")
        all_participants = sorted([u1, u2, u3, u4])

        pair_key = f"DOUBLE_{min(my_duo_id, target_duo_id)}_{max(my_duo_id, target_duo_id)}"
        existing_match = matches_collection.find_one({"pair_key": pair_key})

        if not existing_match:
            squad1_name = my_duo.get("squadName", "Duo 1")
            squad2_name = target_duo.get("squad_name", "Duo 2")

            match_doc = {
                "pair_key": pair_key,
                "is_double_date": True,
                "duo1_id": my_duo_id,
                "duo2_id": target_duo_id,
                "duo1_name": squad1_name,
                "duo2_name": squad2_name,
                "participants": all_participants,
                "user1_id": u1,
                "user2_id": u3,
                "status": "ACTIVE",
                "matched_via": "DOUBLE_DATE",
                "first_move_made": True,
                "created_at": datetime.utcnow(),
            }
            inserted = matches_collection.insert_one(match_doc)
            match_id = str(inserted.inserted_id)

            # Insert opening group celebration message
            conf_text = f"🎉 Double Date Match! {squad1_name} and {squad2_name} have matched! Say hi and plan a 2v2 hangout! 🎳🍕"
            first_msg = {
                "match_id": match_id,
                "sender_id": user_id,
                "receiver_id": u3,
                "participants": all_participants,
                "text": conf_text,
                "is_screenshot": False,
                "is_date_proposal": False,
                "timestamp": datetime.utcnow(),
            }
            messages_collection.insert_one(first_msg)

            target_u1 = users_collection.find_one({"id": u3})
            target_u2 = users_collection.find_one({"id": u4})

            return {
                "status": "MATCHED",
                "isMatch": True,
                "matchId": match_id,
                "squadName": squad2_name,
                "participants": all_participants,
                "targetDuo": {
                    "duoId": target_duo_id,
                    "squadName": squad2_name,
                    "vibe": target_duo.get("vibe", "Fun"),
                    "users": [
                        _format_user_summary(target_u1) if target_u1 else None,
                        _format_user_summary(target_u2) if target_u2 else None,
                    ]
                },
                "message": f"🎉 IT’S A DOUBLE DATE MATCH! {squad1_name} & {squad2_name} are ready to connect!"
            }

    return {
        "status": "LIKED",
        "isMatch": False,
        "message": "Duo Like sent! If they like your squad back, you'll be connected in a 4-person group chat!"
    }
