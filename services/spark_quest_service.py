# backend/services/spark_quest_service.py
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

from database import (
    spark_quests_collection,
    matches_collection,
    users_collection,
    messages_collection,
)
from services.notification_service import create_notification

CURATED_DATE_IDEAS = [
    {
        "id": "cozy_coffee",
        "title": "Cozy Coffee & Walk",
        "emoji": "☕🍂",
        "description": "Catch up at an aesthetic specialty cafe, then stroll through a nearby park.",
        "vibe": "Relaxed & Conversational"
    },
    {
        "id": "street_food_crawl",
        "title": "Street Food Safari",
        "emoji": "🍲🌶️",
        "description": "Hop through bustling food lanes and rate the best pani puri, momos, or chaat together.",
        "vibe": "Adventurous & Fun"
    },
    {
        "id": "board_games_chai",
        "title": "Board Games & Chai",
        "emoji": "🎲♟️",
        "description": "Friendly banter over Catan, Scrabble, or Uno at a gaming lounge with hot chai.",
        "vibe": "Playful & Competitive"
    },
    {
        "id": "sunset_rooftop",
        "title": "Sunset Rooftop Chill",
        "emoji": "🌅🍹",
        "description": "Catch golden hour views with refreshing drinks and soft ambient music.",
        "vibe": "Romantic & Scenic"
    },
    {
        "id": "bookstore_art",
        "title": "Art Gallery & Indie Bookstore",
        "emoji": "🎨📚",
        "description": "Browse quiet shelves, pick books for each other, and explore contemporary art.",
        "vibe": "Intellectual & Cozy"
    },
    {
        "id": "midnight_dessert",
        "title": "Late-Night Ice Cream Run",
        "emoji": "🍦✨",
        "description": "Sweet cravings post-dinner, waffles or gelato while chatting under streetlights.",
        "vibe": "Spontaneous & Sweet"
    },
]

LEVEL_BLUEPRINTS = {
    1: {
        "level": 1,
        "title": "Share Your Favourite Song 🎵",
        "hindiTitle": "Apni favourite song share karo",
        "shortDesc": "Music reveals your inner vibe! Share a track that is on repeat.",
        "actionType": "song",
        "placeholder": "e.g. Kesariya, Starboy, Pasoori...",
        "icon": "Music",
    },
    2: {
        "level": 2,
        "title": "Send a Funny Photo 📸",
        "hindiTitle": "Ek funny photo bhejo",
        "shortDesc": "Break the ice with laughter! Share a funny meme, pet photo, or silly selfie.",
        "actionType": "photo",
        "placeholder": "Funny photo / meme URL or caption",
        "icon": "Camera",
    },
    3: {
        "level": 3,
        "title": "5-Minute Voice Chat 🎙️",
        "hindiTitle": "5-minute voice chat",
        "shortDesc": "Hear the genuine warmth in their voice. Have a quick 5-min call or exchange voice notes.",
        "actionType": "voice",
        "placeholder": "Hop on a quick voice call or send a voice memo",
        "icon": "Mic",
    },
    4: {
        "level": 4,
        "title": "Choose a Date Idea ☕",
        "hindiTitle": "Ek date idea choose karo",
        "shortDesc": "Pick your ideal first meetup aesthetic from our curated collection.",
        "actionType": "date_idea",
        "placeholder": "Select one of 6 date themes",
        "icon": "Compass",
    },
    5: {
        "level": 5,
        "title": "Optional Real-Life Date 🌟",
        "hindiTitle": "Optional real-life date",
        "shortDesc": "Ready to take the spark offline? Agree on a safe, public hangout spot. Zero pressure!",
        "actionType": "real_date",
        "placeholder": "Ready to meet in real life (optional)",
        "icon": "Sparkles",
    },
}

def get_curated_date_ideas() -> List[Dict[str, Any]]:
    return CURATED_DATE_IDEAS

def get_or_create_quest(match_id: str, current_user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves or initializes a 5-level Spark Quest document for a verified active match.
    """
    # 1. Fetch match document
    match_doc = None
    try:
        match_doc = matches_collection.find_one({"_id": ObjectId(match_id)})
    except Exception:
        match_doc = matches_collection.find_one({"_id": match_id})
    
    if not match_doc:
        match_doc = matches_collection.find_one({"pair_key": match_id})

    if not match_doc:
        return None

    user1_id = match_doc.get("user1_id")
    user2_id = match_doc.get("user2_id")

    # If it's a double date or group match, grab first two participants
    if not user1_id or not user2_id:
        parts = match_doc.get("participants", [])
        if len(parts) >= 2:
            user1_id = parts[0]
            user2_id = parts[1]
        else:
            return None

    # Ensure current user is part of this match
    if current_user_id not in [user1_id, user2_id] and current_user_id not in match_doc.get("participants", []):
        return None

    # 2. Look for existing quest
    quest = spark_quests_collection.find_one({"match_id": str(match_doc["_id"])})
    if not quest:
        # Initialize default 5 levels
        levels_state = {}
        for lvl in range(1, 6):
            levels_state[str(lvl)] = {
                "level": lvl,
                "user1_completed": False,
                "user1_submission": None,
                "user2_completed": False,
                "user2_submission": None,
                "status": "in_progress" if lvl == 1 else "locked",
                "completed_at": None,
            }

        quest = {
            "match_id": str(match_doc["_id"]),
            "user1_id": user1_id,
            "user2_id": user2_id,
            "current_level": 1,
            "is_completed": False,
            "badge_unlocked": False,
            "badge_unlocked_at": None,
            "levels": levels_state,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        res = spark_quests_collection.insert_one(quest)
        quest["_id"] = res.inserted_id

    return format_quest_for_user(quest, current_user_id, match_doc)

def format_quest_for_user(quest: Dict[str, Any], current_user_id: str, match_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the raw DB quest into a rich, user-centric structure with opponent info.
    """
    user1_id = quest.get("user1_id")
    user2_id = quest.get("user2_id")
    
    is_user1 = (current_user_id == user1_id)
    opponent_id = user2_id if is_user1 else user1_id

    opponent_user = users_collection.find_one({"id": opponent_id}) or {}
    opponent_name = opponent_user.get("name", "Match Partner")
    opponent_photos = opponent_user.get("photos", [])
    opponent_photo = opponent_photos[0] if opponent_photos else ""

    levels_list = []
    completed_levels_count = 0

    for lvl_idx in range(1, 6):
        lvl_key = str(lvl_idx)
        raw_lvl = quest.get("levels", {}).get(lvl_key, {})
        blueprint = LEVEL_BLUEPRINTS.get(lvl_idx, {})

        my_completed = raw_lvl.get("user1_completed") if is_user1 else raw_lvl.get("user2_completed")
        my_submission = raw_lvl.get("user1_submission") if is_user1 else raw_lvl.get("user2_submission")

        partner_completed = raw_lvl.get("user2_completed") if is_user1 else raw_lvl.get("user1_completed")
        partner_submission = raw_lvl.get("user2_submission") if is_user1 else raw_lvl.get("user1_submission")

        is_both_done = bool(my_completed and partner_completed)
        if is_both_done:
            completed_levels_count += 1
            computed_status = "completed"
        elif quest.get("current_level", 1) > lvl_idx:
            computed_status = "completed"
            completed_levels_count += 1
        elif quest.get("current_level", 1) == lvl_idx:
            if my_completed and not partner_completed:
                computed_status = "waiting_for_partner"
            elif not my_completed and partner_completed:
                computed_status = "partner_waiting_for_you"
            else:
                computed_status = "in_progress"
        else:
            computed_status = "locked"

        levels_list.append({
            "level": lvl_idx,
            "title": blueprint.get("title", f"Level {lvl_idx}"),
            "hindiTitle": blueprint.get("hindiTitle", ""),
            "shortDesc": blueprint.get("shortDesc", ""),
            "actionType": blueprint.get("actionType", ""),
            "placeholder": blueprint.get("placeholder", ""),
            "icon": blueprint.get("icon", "Sparkles"),
            "status": computed_status,
            "myCompleted": bool(my_completed),
            "mySubmission": my_submission,
            "partnerCompleted": bool(partner_completed),
            "partnerSubmission": partner_submission if is_both_done or partner_completed else None,
            "isBothCompleted": is_both_done,
        })

    progress_percent = int((completed_levels_count / 5.0) * 100)

    return {
        "questId": str(quest.get("_id", "")),
        "matchId": quest.get("match_id"),
        "currentLevel": quest.get("current_level", 1),
        "completedLevelsCount": completed_levels_count,
        "totalLevels": 5,
        "progressPercent": progress_percent,
        "isCompleted": bool(quest.get("is_completed", False)),
        "badgeUnlocked": bool(quest.get("badge_unlocked", False)),
        "badgeUnlockedAt": quest.get("badge_unlocked_at").isoformat() if quest.get("badge_unlocked_at") else None,
        "opponent": {
            "id": opponent_id,
            "name": opponent_name,
            "photo": opponent_photo,
        },
        "levels": levels_list,
        "curatedDateIdeas": CURATED_DATE_IDEAS,
        "disclaimer": "💡 Spark Quest is a fun icebreaker challenge to build chemistry — no pressure, just good vibes!",
    }

def get_user_quests_summary(user_id: str) -> List[Dict[str, Any]]:
    """
    Fetches all active Spark Quests for the user across their active matches.
    """
    matches_cursor = matches_collection.find({
        "$or": [
            {"user1_id": user_id},
            {"user2_id": user_id},
            {"participants": user_id}
        ],
        "status": "ACTIVE"
    })

    quests_summary = []
    for m in matches_cursor:
        m_id = str(m["_id"])
        formatted = get_or_create_quest(m_id, user_id)
        if formatted:
            quests_summary.append({
                "matchId": formatted["matchId"],
                "questId": formatted["questId"],
                "opponent": formatted["opponent"],
                "currentLevel": formatted["currentLevel"],
                "completedLevelsCount": formatted["completedLevelsCount"],
                "progressPercent": formatted["progressPercent"],
                "isCompleted": formatted["isCompleted"],
                "badgeUnlocked": formatted["badgeUnlocked"],
            })

    # Sort: In-progress/active first, completed later
    quests_summary.sort(key=lambda q: (1 if q["isCompleted"] else 0, -q["progressPercent"]))
    return quests_summary

def submit_level_action(
    match_id: str,
    user_id: str,
    level: int,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Submits user's action for a specific level.
    If both complete the level:
    - Advances quest to next level.
    - If level == 5, unlocks Spark Quest badge for both profiles.
    - Sends celebratory notifications and chat system messages.
    """
    if level < 1 or level > 5:
        raise ValueError("Invalid level number. Must be between 1 and 5.")

    quest = spark_quests_collection.find_one({"match_id": match_id})
    if not quest:
        get_or_create_quest(match_id, user_id)
        quest = spark_quests_collection.find_one({"match_id": match_id})

    if not quest:
        raise ValueError("Spark Quest not found for this match.")

    user1_id = quest.get("user1_id")
    user2_id = quest.get("user2_id")

    if user_id not in [user1_id, user2_id]:
        raise PermissionError("You are not a participant in this Spark Quest.")

    is_user1 = (user_id == user1_id)
    partner_id = user2_id if is_user1 else user1_id
    lvl_key = str(level)

    current_lvl = quest.get("current_level", 1)
    if level > current_lvl and not quest.get("is_completed"):
        raise ValueError(f"Level {level} is currently locked. Complete Level {current_lvl} first.")

    # Prepare user submission
    submission_data = {
        "action_type": LEVEL_BLUEPRINTS[level]["actionType"],
        "submitted_at": datetime.utcnow().isoformat(),
        **payload,
    }

    user_completed_field = f"levels.{lvl_key}.user1_completed" if is_user1 else f"levels.{lvl_key}.user2_completed"
    user_sub_field = f"levels.{lvl_key}.user1_submission" if is_user1 else f"levels.{lvl_key}.user2_submission"

    update_ops = {
        "$set": {
            user_completed_field: True,
            user_sub_field: submission_data,
            "updated_at": datetime.utcnow(),
        }
    }

    spark_quests_collection.update_one({"_id": quest["_id"]}, update_ops)

    # Re-fetch updated quest doc
    quest = spark_quests_collection.find_one({"_id": quest["_id"]})
    lvl_doc = quest.get("levels", {}).get(lvl_key, {})

    both_done = lvl_doc.get("user1_completed") and lvl_doc.get("user2_completed")
    partner_user = users_collection.find_one({"id": partner_id}) or {}
    partner_name = partner_user.get("name", "Your match")
    current_user_doc = users_collection.find_one({"id": user_id}) or {}
    my_name = current_user_doc.get("name", "Someone")

    if both_done:
        now = datetime.utcnow()
        next_level = min(5, level + 1)
        quest_completed = (level == 5)

        level_complete_ops = {
            "$set": {
                f"levels.{lvl_key}.status": "completed",
                f"levels.{lvl_key}.completed_at": now,
                "current_level": next_level if not quest_completed else 5,
                "is_completed": quest_completed,
                "badge_unlocked": quest_completed,
                "badge_unlocked_at": now if quest_completed else None,
            }
        }
        if next_level <= 5 and not quest_completed:
            level_complete_ops["$set"][f"levels.{str(next_level)}.status"] = "in_progress"

        spark_quests_collection.update_one({"_id": quest["_id"]}, level_complete_ops)

        # Notify both users of Level completion
        level_name = LEVEL_BLUEPRINTS[level]["title"]
        if quest_completed:
            # 🏆 Award Spark Quest Badge to both user profiles
            users_collection.update_one({"id": user1_id}, {"$addToSet": {"badges": "spark_quest_badge"}})
            users_collection.update_one({"id": user2_id}, {"$addToSet": {"badges": "spark_quest_badge"}})

            # Chat system announcement
            msg_doc = {
                "match_id": match_id,
                "sender_id": "system",
                "text": "🏆 Spark Quest Completed! You both completed all 5 dating challenges. Your exclusive Spark Quest Badges are now unlocked!",
                "type": "SPARK_QUEST_CELEBRATION",
                "timestamp": now,
            }
            messages_collection.insert_one(msg_doc)

            # Notifications to both
            create_notification(
                user_id=user1_id,
                notif_type="SPARK_QUEST_UPDATE",
                title="Spark Quest Completed! 🏆",
                body=f"Congratulations! You and {partner_name} conquered all 5 challenges and unlocked the Spark Quest Badge! ✨",
                sender_id=user2_id,
                sender_name=partner_name,
                sender_photo=partner_user.get("photos", [""])[0] if partner_user.get("photos") else "",
                match_id=match_id,
                extra_data={"badgeUnlocked": True, "level": 5}
            )
            create_notification(
                user_id=user2_id,
                notif_type="SPARK_QUEST_UPDATE",
                title="Spark Quest Completed! 🏆",
                body=f"Congratulations! You and {my_name} conquered all 5 challenges and unlocked the Spark Quest Badge! ✨",
                sender_id=user_id,
                sender_name=my_name,
                sender_photo=current_user_doc.get("photos", [""])[0] if current_user_doc.get("photos") else "",
                match_id=match_id,
                extra_data={"badgeUnlocked": True, "level": 5}
            )
        else:
            # Intermediate Level completion notification
            next_lvl_name = LEVEL_BLUEPRINTS[next_level]["title"]
            create_notification(
                user_id=partner_id,
                notif_type="SPARK_QUEST_UPDATE",
                title=f"Level {level} Complete! 🎉",
                body=f"{my_name} completed Level {level} with you! {next_lvl_name} is now unlocked 🚀",
                sender_id=user_id,
                sender_name=my_name,
                sender_photo=current_user_doc.get("photos", [""])[0] if current_user_doc.get("photos") else "",
                match_id=match_id,
                extra_data={"level": next_level}
            )
            create_notification(
                user_id=user_id,
                notif_type="SPARK_QUEST_UPDATE",
                title=f"Level {level} Complete! 🎉",
                body=f"Both of you completed {level_name}! {next_lvl_name} is now unlocked 🚀",
                sender_id=partner_id,
                sender_name=partner_name,
                sender_photo=partner_user.get("photos", [""])[0] if partner_user.get("photos") else "",
                match_id=match_id,
                extra_data={"level": next_level}
            )
            # In-chat announcement
            messages_collection.insert_one({
                "match_id": match_id,
                "sender_id": "system",
                "text": f"Level {level} Complete! You both completed '{level_name}'. Next up: Level {next_level} ({next_lvl_name})!",
                "type": "SPARK_QUEST_UPDATE",
                "timestamp": now,
            })
    else:
        # Only one person completed so far -> Send a friendly nudge to the partner
        level_name = LEVEL_BLUEPRINTS[level]["title"]
        create_notification(
            user_id=partner_id,
            notif_type="SPARK_QUEST_UPDATE",
            title=f"Spark Quest: Level {level} ⚡",
            body=f"{my_name} submitted their part for '{level_name}'. Complete yours to unlock the next level!",
            sender_id=user_id,
            sender_name=my_name,
            sender_photo=current_user_doc.get("photos", [""])[0] if current_user_doc.get("photos") else "",
            match_id=match_id,
            extra_data={"level": level}
        )

    return get_or_create_quest(match_id, user_id)
