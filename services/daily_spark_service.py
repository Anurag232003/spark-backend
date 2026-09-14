# backend/services/daily_spark_service.py
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from database import (
    daily_sparks_collection,
    spark_challenges_collection,
    users_collection,
    interactions_collection,
    matches_collection,
    messages_collection,
)
from services.notification_service import create_notification

# Default 3 Progressive Challenge Activities
CURATED_CHALLENGE_ACTIVITIES = [
    {
        "level": 1,
        "title": "Rapid Fire Icebreaker 🎯",
        "tagline": "Break the ice with zero awkwardness",
        "question": "If you had 2 free flight tickets right now, where are we landing first?",
        "options": ["Kyoto, Japan 🌸", "Swiss Alps 🏔️", "Goa beach sunset 🏖️", "Northern Lights 🌌"],
    },
    {
        "level": 2,
        "title": "Dilemma Duel ⚖️",
        "tagline": "Discover how each other's mind works",
        "question": "Late-night deep rooftop conversations OR spontaneous road trip with great music?",
        "options": ["Rooftop & deep talks ✨", "Spontaneous road trip 🚗", "Why not both? 😉"],
    },
    {
        "level": 3,
        "title": "Spark Perspective 📸",
        "tagline": "The final milestone to lock in your chemistry",
        "question": "What is the #1 quality or vibe that immediately catches your attention in a person?",
        "options": ["Sense of humour & quick wit 😄", "Emotional maturity & empathy ❤️", "Passion & ambition 🚀", "Unapologetic authenticity 💫"],
    },
]

def _compute_match_reasons(user: Dict[str, Any], candidate: Dict[str, Any]) -> List[str]:
    """
    Generates 2 to 3 compelling, human-friendly reasons explaining why this curated drop matches.
    """
    reasons = []

    # 1. Daily Vibe comparison
    u_vibes = user.get("daily_vibes", [])
    c_vibes = candidate.get("daily_vibes", [])
    common_vibes = set(u_vibes).intersection(set(c_vibes))
    if common_vibes:
        reasons.append("Both shared the same mood & vibe today")
    elif c_vibes:
        c_label = candidate.get("daily_vibe_label") or "High Energy"
        reasons.append(f"Resonates with your vibe · {c_label}")

    # 2. Interests / Passions
    u_interests = set(user.get("interests", []))
    c_interests = set(candidate.get("interests", []))
    common_interests = list(u_interests.intersection(c_interests))
    if common_interests:
        reasons.append(f"Mutual love for {', '.join(common_interests[:2])}")

    # 3. Trust & Verification
    if candidate.get("is_photo_verified") or candidate.get("isPhotoVerified"):
        reasons.append("100% Selfie-verified authentic profile")

    # 4. Proximity fallback
    if len(reasons) < 2:
        reasons.append("Top compatibility score in your area today")

    return reasons[:3]

def generate_or_get_daily_sparks(user_id: str) -> Dict[str, Any]:
    """
    Returns today's 1-3 curated profiles for the user.
    If today's drops haven't been generated yet, runs algorithmic curation and saves them.
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    now = datetime.utcnow()

    # 1. Check existing daily sparks
    existing = daily_sparks_collection.find_one({"user_id": user_id, "drop_date": today_str})
    if existing:
        candidate_ids = [p["candidate_id"] for p in existing.get("profiles", [])]
        candidates_map = {}
        for c in users_collection.find({"id": {"$in": candidate_ids}}):
            candidates_map[c["id"]] = c

        profiles_out = []
        for p in existing.get("profiles", []):
            cid = p["candidate_id"]
            user_doc = candidates_map.get(cid)
            if not user_doc:
                continue

            photos = user_doc.get("photos", [])
            profiles_out.append({
                "candidateId": cid,
                "name": user_doc.get("name", "Spark Member"),
                "age": user_doc.get("age", 24),
                "bio": user_doc.get("bio", ""),
                "photos": photos,
                "prompts": user_doc.get("prompts", []),
                "isPhotoVerified": bool(user_doc.get("is_photo_verified") or user_doc.get("isPhotoVerified")),
                "dailyVibeLabel": user_doc.get("daily_vibe_label"),
                "dailyVibeEmoji": user_doc.get("daily_vibe_emoji") or "✨",
                "compatibilityScore": p.get("compatibility_score", 92),
                "matchReasons": p.get("match_reasons", ["High Chemistry Match"]),
                "hasSwiped": p.get("has_swiped", False),
                "action": p.get("action"),
            })

        expires_at = existing.get("expires_at", now + timedelta(hours=24))
        seconds_left = max(0, int((expires_at - now).total_seconds()))

        return {
            "status": "SUCCESS",
            "dropDate": today_str,
            "expiresAt": expires_at.isoformat(),
            "secondsRemaining": seconds_left,
            "hoursRemaining": round(seconds_left / 3600, 1),
            "profiles": profiles_out,
            "totalDrops": len(profiles_out),
            "unviewedCount": sum(1 for p in profiles_out if not p["hasSwiped"]),
        }

    # 2. Curate 1 to 3 new profiles
    user = users_collection.find_one({"id": user_id})
    if not user:
        return {
            "status": "ERROR",
            "message": "User not found",
            "profiles": [],
            "totalDrops": 0,
        }

    # Exclude users already swiped, matched, or blocked
    swiped_ids = interactions_collection.distinct("target_user_id", {"from_user_id": user_id})
    blocked_ids = set()
    for b in user.get("blocked_users", []):
        blocked_ids.add(b)

    exclude_ids = set(swiped_ids).union(blocked_ids)
    exclude_ids.add(user_id)

    # Gender Preference filtering
    query: Dict[str, Any] = {"id": {"$nin": list(exclude_ids)}}
    gender_pref = user.get("gender_preference") or user.get("genderPreference")
    if gender_pref and gender_pref not in ["all", "both"]:
        query["gender"] = gender_pref

    # Fetch candidate pool (up to 50 candidates)
    candidates = list(users_collection.find(query).limit(50))

    # Scoring candidates
    user_vibes = set(user.get("daily_vibes", []))
    scored_candidates = []

    for c in candidates:
        score = 80  # Base resonance
        c_vibes = set(c.get("daily_vibes", []))
        if user_vibes and c_vibes and user_vibes.intersection(c_vibes):
            score += 12  # Vibe match bonus
        if c.get("is_photo_verified") or c.get("isPhotoVerified"):
            score += 5   # Verified trust bonus
        if len(c.get("photos", [])) >= 3:
            score += 2   # High quality profile bonus

        score = min(99, max(75, score))
        scored_candidates.append((score, c))

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    # Take top 1 to 3
    selected_curated = scored_candidates[:3] if scored_candidates else []

    expires_at = now + timedelta(hours=24)
    profiles_to_store = []
    profiles_out = []

    for score, cand in selected_curated:
        cid = cand["id"]
        reasons = _compute_match_reasons(user, cand)
        profiles_to_store.append({
            "candidate_id": cid,
            "compatibility_score": score,
            "match_reasons": reasons,
            "has_swiped": False,
            "action": None,
            "swiped_at": None,
        })
        photos = cand.get("photos", [])
        profiles_out.append({
            "candidateId": cid,
            "name": cand.get("name", "Spark Member"),
            "age": cand.get("age", 24),
            "bio": cand.get("bio", ""),
            "photos": photos,
            "prompts": cand.get("prompts", []),
            "isPhotoVerified": bool(cand.get("is_photo_verified") or cand.get("isPhotoVerified")),
            "dailyVibeLabel": cand.get("daily_vibe_label"),
            "dailyVibeEmoji": cand.get("daily_vibe_emoji") or "✨",
            "compatibilityScore": score,
            "matchReasons": reasons,
            "hasSwiped": False,
            "action": None,
        })

    # Save to daily_sparks_collection
    daily_sparks_collection.update_one(
        {"user_id": user_id, "drop_date": today_str},
        {
            "$set": {
                "user_id": user_id,
                "drop_date": today_str,
                "expires_at": expires_at,
                "profiles": profiles_to_store,
                "created_at": now,
            }
        },
        upsert=True,
    )

    return {
        "status": "SUCCESS",
        "dropDate": today_str,
        "expiresAt": expires_at.isoformat(),
        "secondsRemaining": int((expires_at - now).total_seconds()),
        "hoursRemaining": 24.0,
        "profiles": profiles_out,
        "totalDrops": len(profiles_out),
        "unviewedCount": len(profiles_out),
    }

def interact_daily_spark(
    user_id: str,
    candidate_id: str,
    action: str  # "LIKE" | "PASS"
) -> Dict[str, Any]:
    """
    Handles user interaction with a 24-Hour Spark drop.
    If both users like, creates an active 24-Hour Spark Match and unlocks the Conversation Challenge!
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    now = datetime.utcnow()
    action = action.upper()

    # 1. Update daily_sparks record for user
    daily_sparks_collection.update_one(
        {"user_id": user_id, "drop_date": today_str, "profiles.candidate_id": candidate_id},
        {
            "$set": {
                "profiles.$.has_swiped": True,
                "profiles.$.action": action,
                "profiles.$.swiped_at": now,
            }
        }
    )

    # 2. Record in main interactions collection
    interactions_collection.update_one(
        {"from_user_id": user_id, "target_user_id": candidate_id},
        {"$set": {"type": action, "timestamp": now, "is_daily_spark": True}},
        upsert=True
    )

    if action != "LIKE":
        return {"status": "SUCCESS", "isMatch": False, "message": "Profile passed"}

    # 3. Check mutual like
    reciprocal = interactions_collection.find_one({
        "from_user_id": candidate_id,
        "target_user_id": user_id,
        "type": "LIKE"
    })

    # For testing and exciting UX, if candidate is a daily spark or reciprocal like, create match
    is_match = bool(reciprocal)
    # If no interaction from other side yet, check if other user also had them as a spark drop
    if not is_match:
        # Check if candidate has already swiped
        pass

    # Create match if mutual
    if is_match:
        pair_key = "_".join(sorted([user_id, candidate_id]))
        deadline = now + timedelta(hours=24)
        
        match_doc = matches_collection.find_one_and_update(
            {"pair_key": pair_key},
            {
                "$set": {
                    "pair_key": pair_key,
                    "user1_id": user_id,
                    "user2_id": candidate_id,
                    "status": "ACTIVE",
                    "is_24h_spark": True,
                    "first_move_deadline": deadline,
                    "first_move_made": False,
                    "created_at": now,
                }
            },
            upsert=True,
            return_document=True
        )
        match_id = str(match_doc["_id"])

        # 4. Initialize 24-Hour Conversation Challenge
        challenge_doc = {
            "match_id": match_id,
            "user1_id": user_id,
            "user2_id": candidate_id,
            "created_at": now,
            "expires_at": deadline,
            "is_completed": False,
            "current_level": 1,
            "activities": CURATED_CHALLENGE_ACTIVITIES,
            "responses": {
                user_id: {},
                candidate_id: {},
            },
        }
        spark_challenges_collection.update_one(
            {"match_id": match_id},
            {"$set": challenge_doc},
            upsert=True
        )

        # 5. In-App Notifications for both
        u_sender = users_collection.find_one({"id": user_id})
        s_name = u_sender.get("name", "Someone") if u_sender else "Someone"
        create_notification(
            user_id=candidate_id,
            notif_type="MATCH",
            title="⚡ 24-Hour Spark Unlocked!",
            body=f"You and {s_name} connected on today's Curated Spark! 24-Hour Challenge is LIVE.",
            sender_id=user_id,
            sender_name=s_name,
            match_id=match_id
        )

        return {
            "status": "SUCCESS",
            "isMatch": True,
            "matchId": match_id,
            "expiresAt": deadline.isoformat(),
            "challenge": {
                "matchId": match_id,
                "currentLevel": 1,
                "isCompleted": False,
                "activities": CURATED_CHALLENGE_ACTIVITIES,
            }
        }

    return {"status": "SUCCESS", "isMatch": False, "message": "Like registered"}

def get_spark_challenge(match_id: str, user_id: str) -> Dict[str, Any]:
    """
    Fetches the 24-Hour Conversation Challenge progress and questions for a match.
    """
    now = datetime.utcnow()
    challenge = spark_challenges_collection.find_one({"match_id": match_id})
    if not challenge:
        # Check if match is 24h spark
        return {"status": "NOT_FOUND", "is24HourSpark": False}

    expires_at = challenge.get("expires_at", now + timedelta(hours=24))
    seconds_left = max(0, int((expires_at - now).total_seconds()))
    is_completed = challenge.get("is_completed", False)
    responses = challenge.get("responses", {})

    # If messages sent in chat >= 4, consider level completed or auto-promote
    msg_count = messages_collection.count_documents({"match_id": match_id})
    if msg_count >= 6 and not is_completed:
        is_completed = True
        spark_challenges_collection.update_one({"match_id": match_id}, {"$set": {"is_completed": True}})
        matches_collection.update_one({"_id": ObjectId(match_id)}, {"$set": {"is_permanent": True}})

    return {
        "status": "SUCCESS",
        "matchId": match_id,
        "is24HourSpark": True,
        "isCompleted": is_completed,
        "currentLevel": challenge.get("current_level", 1),
        "expiresAt": expires_at.isoformat(),
        "secondsRemaining": seconds_left,
        "hoursRemaining": round(seconds_left / 3600, 1),
        "activities": challenge.get("activities", CURATED_CHALLENGE_ACTIVITIES),
        "myResponses": responses.get(user_id, {}),
        "messageCount": msg_count,
    }

def submit_challenge_answer(
    match_id: str,
    user_id: str,
    level: int,
    answer: str
) -> Dict[str, Any]:
    """
    Submits an answer for one of the 3 challenge levels.
    """
    challenge = spark_challenges_collection.find_one({"match_id": match_id})
    if not challenge:
        return {"status": "ERROR", "message": "Challenge not found"}

    now = datetime.utcnow()
    key = f"responses.{user_id}.level_{level}"

    spark_challenges_collection.update_one(
        {"match_id": match_id},
        {
            "$set": {
                key: {"answer": answer, "answered_at": now},
            }
        }
    )

    # Post message into match chat so both see the answer interactively
    u = users_collection.find_one({"id": user_id})
    s_name = u.get("name", "You") if u else "You"
    s_photo = (u.get("photos", [""]) or [""])[0] if u else ""

    act = next((a for a in CURATED_CHALLENGE_ACTIVITIES if a["level"] == level), None)
    act_title = act["title"] if act else f"Level {level}"

    formatted_text = f"⚡ 24h Spark Challenge [{act_title}]\n👉 {answer}"
    msg_doc = {
        "match_id": match_id,
        "sender_id": user_id,
        "receiver_id": challenge["user2_id"] if user_id == challenge["user1_id"] else challenge["user1_id"],
        "text": formatted_text,
        "is_challenge_answer": True,
        "timestamp": now,
    }
    messages_collection.insert_one(msg_doc)

    # Check completion: if level 3 answered or all levels reached
    next_level = min(3, level + 1)
    is_completed = level >= 3

    spark_challenges_collection.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "current_level": next_level,
                "is_completed": is_completed,
            }
        }
    )

    if is_completed:
        matches_collection.update_one({"_id": ObjectId(match_id)}, {"$set": {"is_permanent": True}})

    return {
        "status": "SUCCESS",
        "level": level,
        "nextLevel": next_level,
        "isCompleted": is_completed,
    }
