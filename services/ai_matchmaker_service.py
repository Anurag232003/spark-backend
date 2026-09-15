# backend/services/ai_matchmaker_service.py
"""
Spark AI Matchmaker Service
A 6-layer intelligence matchmaking engine:
1. User Preferences (Age, gender, distance, intent)
2. Personality Quiz (Sunday vibe, communication style, first date, core vibe)
3. Deterministic Compatibility Engine (Formula: 0.25*I + 0.25*D + 0.15*L + 0.15*C + 0.10*P + 0.10*V)
4. Explainable Recommendations ("Why You Might Click" & Dynamic AI Icebreakers)
5. Curation Buckets: Daily 5 Sparks, Hidden Gem, Opposite Vibe
6. Monetization & VIP Subscription Controls
"""

import math
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from bson import ObjectId

from database import (
    users_collection,
    interactions_collection,
    blocks_collection,
    matchmaker_profiles_collection,
    matchmaker_feedbacks_collection,
    vip_subscriptions_collection,
)

# ---------------------------------------------------------------------
# 1. Spark Personality Quiz Schema
# ---------------------------------------------------------------------
PERSONALITY_QUIZ_SCHEMA = {
    "version": "1.0",
    "questions": [
        {
            "id": "sunday_vibe",
            "title": "Your Perfect Sunday? ☀️",
            "subtitle": "How do you recharge your batteries?",
            "factor": "L",  # Lifestyle
            "options": [
                {"id": "gaming_home", "label": "Gaming or relaxing at home", "emoji": "🎮"},
                {"id": "cafe_hopping", "label": "Cafe hopping & aesthetic coffee", "emoji": "☕"},
                {"id": "party_friends", "label": "Partying & hanging with friends", "emoji": "🎉"},
                {"id": "exploring_new", "label": "Exploring somewhere new / road trips", "emoji": "🗺️"},
            ],
        },
        {
            "id": "communication_style",
            "title": "Communication Style? 💬",
            "subtitle": "How do you prefer staying in touch?",
            "factor": "C",  # Communication
            "options": [
                {"id": "texting", "label": "Consistent texting & memes", "emoji": "💬"},
                {"id": "voice_calls", "label": "Late-night calls & voice notes", "emoji": "🎙️"},
                {"id": "mix", "label": "Healthy mix of both text & calls", "emoji": "🔄"},
            ],
        },
        {
            "id": "first_date",
            "title": "Ideal First Date? 🥂",
            "subtitle": "What setting lets you be yourself?",
            "factor": "V",  # Date Vibe
            "options": [
                {"id": "coffee", "label": "Cozy coffee & deep conversation", "emoji": "☕"},
                {"id": "movie", "label": "Movie night + dessert after", "emoji": "🎬"},
                {"id": "adventure", "label": "Fun & adventurous (arcade/bowling/trek)", "emoji": "🎯"},
                {"id": "food_walk", "label": "Street food walk & night market", "emoji": "🍜"},
            ],
        },
        {
            "id": "vibe",
            "title": "Your Core Vibe? ✨",
            "subtitle": "How would your friends describe you?",
            "factor": "P",  # Personality
            "options": [
                {"id": "funny", "label": "Funny, witty & playful", "emoji": "😄"},
                {"id": "calm", "label": "Calm, introverted & thoughtful", "emoji": "🌿"},
                {"id": "ambitious", "label": "Ambitious, driven & passionate", "emoji": "🚀"},
                {"id": "adventurous", "label": "Spontaneous, bold & energetic", "emoji": "⚡"},
            ],
        },
        {
            "id": "relationship_intent",
            "title": "What are you looking for? ❤️",
            "subtitle": "Clear intentions prevent misunderstandings",
            "factor": "D",  # Dating Intent
            "options": [
                {"id": "serious", "label": "Serious relationship & long-term bond", "emoji": "💍"},
                {"id": "casual", "label": "Casual dating & seeing where it goes", "emoji": "✨"},
                {"id": "friendship", "label": "Friendship first with real chemistry", "emoji": "🤝"},
                {"id": "exploring", "label": "Open to exploring & taking things slow", "emoji": "🌊"},
            ],
        },
    ]
}

# ---------------------------------------------------------------------
# 2. Compatibility Engine & Scoring Formula
# ---------------------------------------------------------------------
# Formula: Score = 0.25*I + 0.25*D + 0.15*L + 0.15*C + 0.10*P + 0.10*V

def _calc_shared_interests_score(user_interests: List[str], candidate_interests: List[str]) -> Tuple[float, List[str]]:
    """Calculates interests score (0-100) and returns common interest labels."""
    u_set = {i.strip().lower() for i in (user_interests or []) if i}
    c_set = {i.strip().lower() for i in (candidate_interests or []) if i}
    if not u_set or not c_set:
        return 50.0, []

    common = list(u_set.intersection(c_set))
    union_len = max(min(len(u_set), len(c_set)), 1)
    ratio = min(len(common) / union_len, 1.0)
    # Scale from 40 (baseline) to 100 based on overlap
    score = 40.0 + (ratio * 60.0)
    return round(score, 1), common


def _calc_dating_intent_score(u_intent: Optional[str], c_intent: Optional[str]) -> float:
    """Calculates dating intention compatibility score (0-100)."""
    if not u_intent or not c_intent:
        return 70.0
    u = u_intent.lower()
    c = c_intent.lower()
    if u == c:
        return 100.0
    # Complementary / flexible combinations
    flexible_pairs = {
        ("serious", "exploring"),
        ("exploring", "serious"),
        ("casual", "exploring"),
        ("exploring", "casual"),
        ("friendship", "exploring"),
        ("exploring", "friendship"),
    }
    if (u, c) in flexible_pairs:
        return 75.0
    if (u, c) in {("serious", "friendship"), ("friendship", "serious")}:
        return 60.0
    if (u, c) in {("serious", "casual"), ("casual", "serious")}:
        return 25.0
    return 50.0


def _calc_lifestyle_score(u_sunday: Optional[str], c_sunday: Optional[str]) -> float:
    """Calculates Sunday vibe / lifestyle score (0-100)."""
    if not u_sunday or not c_sunday:
        return 65.0
    if u_sunday == c_sunday:
        return 100.0
    # Compatible adjacent lifestyles
    compatible = {
        ("gaming_home", "cafe_hopping"),
        ("cafe_hopping", "gaming_home"),
        ("party_friends", "exploring_new"),
        ("exploring_new", "party_friends"),
        ("cafe_hopping", "exploring_new"),
        ("exploring_new", "cafe_hopping"),
    }
    if (u_sunday, c_sunday) in compatible:
        return 75.0
    return 45.0


def _calc_communication_score(u_comm: Optional[str], c_comm: Optional[str]) -> float:
    """Calculates communication style score (0-100)."""
    if not u_comm or not c_comm:
        return 70.0
    if u_comm == c_comm or u_comm == "mix" or c_comm == "mix":
        return 95.0
    # Texting vs Voice calls
    return 55.0


def _calc_personality_score(u_vibe: Optional[str], c_vibe: Optional[str]) -> float:
    """Calculates core vibe / personality synergy score (0-100)."""
    if not u_vibe or not c_vibe:
        return 70.0
    if u_vibe == c_vibe:
        return 95.0
    synergy_matrix = {
        ("funny", "calm"): 90.0,
        ("calm", "funny"): 90.0,
        ("funny", "adventurous"): 92.0,
        ("adventurous", "funny"): 92.0,
        ("calm", "ambitious"): 85.0,
        ("ambitious", "calm"): 85.0,
        ("ambitious", "adventurous"): 88.0,
        ("adventurous", "ambitious"): 88.0,
    }
    return synergy_matrix.get((u_vibe, c_vibe), 65.0)


def _calc_date_vibe_score(u_date: Optional[str], c_date: Optional[str]) -> float:
    """Calculates first date preference compatibility (0-100)."""
    if not u_date or not c_date:
        return 70.0
    if u_date == c_date:
        return 100.0
    pairs = {
        ("coffee", "food_walk"): 88.0,
        ("food_walk", "coffee"): 88.0,
        ("coffee", "movie"): 80.0,
        ("movie", "coffee"): 80.0,
        ("adventure", "food_walk"): 82.0,
        ("food_walk", "adventure"): 82.0,
    }
    return pairs.get((u_date, c_date), 60.0)


def compute_compatibility_breakdown(
    user_doc: Dict[str, Any],
    user_quiz: Dict[str, Any],
    candidate_doc: Dict[str, Any],
    candidate_quiz: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes total score and individual factor scores using the exact product formula:
    Score = 0.25*I + 0.25*D + 0.15*L + 0.15*C + 0.10*P + 0.10*V
    """
    # 1. Interests (25%)
    i_score, common_interests = _calc_shared_interests_score(
        user_doc.get("interests", []),
        candidate_doc.get("interests", []),
    )

    # 2. Intent (25%)
    u_intent = user_quiz.get("relationship_intent") or user_doc.get("relationshipGoals")
    c_intent = candidate_quiz.get("relationship_intent") or candidate_doc.get("relationshipGoals")
    d_score = _calc_dating_intent_score(u_intent, c_intent)

    # 3. Lifestyle (15%)
    l_score = _calc_lifestyle_score(user_quiz.get("sunday_vibe"), candidate_quiz.get("sunday_vibe"))

    # 4. Communication (15%)
    c_score = _calc_communication_score(user_quiz.get("communication_style"), candidate_quiz.get("communication_style"))

    # 5. Personality (10%)
    p_score = _calc_personality_score(user_quiz.get("vibe"), candidate_quiz.get("vibe"))

    # 6. Date Vibe (10%)
    v_score = _calc_date_vibe_score(user_quiz.get("first_date"), candidate_quiz.get("first_date"))

    total_score = (
        (0.25 * i_score)
        + (0.25 * d_score)
        + (0.15 * l_score)
        + (0.15 * c_score)
        + (0.10 * p_score)
        + (0.10 * v_score)
    )
    total_score = round(min(max(total_score, 10.0), 99.0), 1)

    return {
        "totalScore": int(round(total_score)),
        "factors": {
            "sharedInterests": int(round(i_score)),
            "datingIntent": int(round(d_score)),
            "lifestyle": int(round(l_score)),
            "communication": int(round(c_score)),
            "personality": int(round(p_score)),
            "dateVibe": int(round(v_score)),
        },
        "weights": {
            "sharedInterests": "25%",
            "datingIntent": "25%",
            "lifestyle": "15%",
            "communication": "15%",
            "personality": "10%",
            "dateVibe": "10%",
        },
        "commonInterests": common_interests,
        "uIntent": u_intent,
        "cIntent": c_intent,
        "uVibe": user_quiz.get("vibe"),
        "cVibe": candidate_quiz.get("vibe"),
        "uDate": user_quiz.get("first_date"),
        "cDate": candidate_quiz.get("first_date"),
        "uComm": user_quiz.get("communication_style"),
        "cComm": candidate_quiz.get("communication_style"),
    }


# ---------------------------------------------------------------------
# 3. "Why You Might Click" & Dynamic Icebreaker Generator
# ---------------------------------------------------------------------
def generate_click_reasons(breakdown: Dict[str, Any], candidate_doc: Dict[str, Any]) -> List[str]:
    """Generates transparent, human-friendly reasons explaining why the recommendation fits."""
    reasons = []

    # Intent match
    if breakdown["factors"]["datingIntent"] >= 75:
        intent_label = breakdown.get("cIntent") or "meaningful connection"
        if intent_label == "serious":
            reasons.append("Both looking for a serious, long-term bond ❤️")
        elif intent_label == "casual":
            reasons.append("Both looking for relaxed & casual dating ✨")
        elif intent_label == "friendship":
            reasons.append("Both value building friendship & comfort first 🤝")
        else:
            reasons.append("Both aligned on dating intentions & pace 🌊")

    # Shared interests
    common_interests = breakdown.get("commonInterests", [])
    if common_interests:
        top_interests = ", ".join(common_interests[:2]).title()
        reasons.append(f"Mutual passion for {top_interests} 🎯")

    # Communication & date alignment
    if breakdown["factors"]["communication"] >= 80:
        c_style = breakdown.get("cComm") or "flexible"
        if c_style == "texting":
            reasons.append("Both prefer comfortable texting & meme sharing 💬")
        elif c_style == "voice_calls":
            reasons.append("Both enjoy warm late-night calls & voice notes 🎙️")
        else:
            reasons.append("Balanced communication style (text + calls) 🔄")

    if breakdown["factors"]["dateVibe"] >= 80:
        d_vibe = breakdown.get("cDate")
        if d_vibe == "coffee":
            reasons.append("Both pick relaxed coffee dates with great talks ☕")
        elif d_vibe == "movie":
            reasons.append("Both love movie nights + desserts 🎬")
        elif d_vibe == "adventure":
            reasons.append("Both crave high-energy adventure & arcade dates 🎯")
        elif d_vibe == "food_walk":
            reasons.append("Both excited by late-night street food walks 🍜")

    # Verified badge reason
    if candidate_doc.get("is_photo_verified") or candidate_doc.get("isPhotoVerified"):
        reasons.append("100% Selfie-verified authentic profile 🛡️")

    # Fallback to general high compatibility
    if len(reasons) < 2:
        reasons.append(f"Strong {breakdown['totalScore']}% overall vibe synergy in your city 🚀")

    return reasons[:4]


def generate_ai_icebreaker(
    user_doc: Dict[str, Any],
    candidate_doc: Dict[str, Any],
    breakdown: Dict[str, Any]
) -> str:
    """Creates a charming, non-creepy conversation starter based on real mutual affinities."""
    c_name = candidate_doc.get("name", "there").split()[0]
    common_interests = breakdown.get("commonInterests", [])
    c_date = breakdown.get("cDate")
    c_vibe = breakdown.get("cVibe")

    if common_interests:
        interest = common_interests[0].title()
        starters = [
            f"Hey {c_name}! Spark said we both love {interest}. What got you into it?",
            f"Hey {c_name}, saw we both have {interest} in common! Dealbreaker question: what's your #1 favourite part about it?",
            f"Hey {c_name}! Fellow {interest} enthusiast spotted 👀 What's your current obsession in it?",
        ]
        return random.choice(starters)

    if c_date == "coffee":
        return f"Hey {c_name}! Spark Matchmaker thinks we'd vibe over coffee. Are you team iced latte or strong cappuccino? ☕"
    elif c_date == "food_walk":
        return f"Hey {c_name}! Food walk date showdown: what's the one street food you can never say no to? 🍜"
    elif c_date == "adventure":
        return f"Hey {c_name}! Bowling or arcade showdown on our first date? Loser buys the milkshakes! 🎳"
    elif c_date == "movie":
        return f"Hey {c_name}! If we did a movie night, thriller mystery or cozy comfort watch? 🎬"

    if c_vibe == "funny":
        return f"Hey {c_name}! Spark rated our humor synergy high. What's the best dad joke you know? 😂"

    return f"Hey {c_name}! Spark Matchmaker flagged our vibes as a rare match. How's your week treating you? ✨"


# ---------------------------------------------------------------------
# 4. VIP Subscription Status Helper
# ---------------------------------------------------------------------
def check_user_vip_status(user_id: str) -> Dict[str, Any]:
    """Checks if the user has an active Spark VIP / Matchmaker subscription."""
    user = users_collection.find_one({"id": user_id})
    if not user:
        return {"isVip": False, "tier": "free", "expiresAt": None}

    if user.get("is_vip"):
        return {
            "isVip": True,
            "tier": user.get("vip_tier", "spark_vip_annual"),
            "expiresAt": user.get("vip_expires_at"),
            "features": [
                "Daily 5 AI Sparks",
                "Hidden Gem & Opposite Vibe curation",
                "Full 6-factor Compatibility breakdown",
                "Instant AI Icebreaker starters",
                "Feedback-driven recommendation tuning",
            ],
        }

    # Check active subscription document in DB
    sub = vip_subscriptions_collection.find_one({
        "user_id": user_id,
        "is_active": True,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    if sub:
        return {
            "isVip": True,
            "tier": sub.get("tier", "spark_vip_monthly"),
            "expiresAt": sub.get("expires_at").isoformat() if isinstance(sub.get("expires_at"), datetime) else str(sub.get("expires_at")),
            "features": [
                "Daily 5 AI Sparks",
                "Hidden Gem & Opposite Vibe curation",
                "Full 6-factor Compatibility breakdown",
                "Instant AI Icebreaker starters",
            ],
        }

    return {
        "isVip": False,
        "tier": "free",
        "expiresAt": None,
        "freeSparksAllowed": 1,
    }


def activate_user_vip(user_id: str, tier: str = "spark_vip_monthly", days: int = 30) -> Dict[str, Any]:
    """Activates Spark VIP for the user (used for in-app upgrade / demo upgrade)."""
    now = datetime.utcnow()
    expires_at = now + timedelta(days=days)

    users_collection.update_one(
        {"id": user_id},
        {"$set": {
            "is_vip": True,
            "vip_tier": tier,
            "vip_expires_at": expires_at.isoformat(),
            "updated_at": now
        }}
    )

    vip_subscriptions_collection.insert_one({
        "user_id": user_id,
        "tier": tier,
        "is_active": True,
        "started_at": now,
        "expires_at": expires_at,
        "created_at": now,
    })

    return check_user_vip_status(user_id)


# ---------------------------------------------------------------------
# 5. Core Recommendations Generator
# ---------------------------------------------------------------------
def get_matchmaker_recommendations(user_id: str) -> Dict[str, Any]:
    """
    Main matchmaking discovery generator:
    - Verifies user profile and quiz answers.
    - Applies hard filters (self, blocked, passed).
    - Runs deterministic compatibility formula.
    - Curates: Daily 5 Sparks, Hidden Gem, Opposite Vibe.
    - Enforces VIP access gating (free users get 1 preview spark with paywall prompt).
    """
    user_doc = users_collection.find_one({"id": user_id})
    if not user_doc:
        return {"error": "User not found"}

    user_quiz_doc = matchmaker_profiles_collection.find_one({"user_id": user_id}) or {}
    user_quiz = user_quiz_doc.get("answers", {})

    vip_status = check_user_vip_status(user_id)
    is_vip = vip_status.get("isVip", False)

    # 1. Hard filters: get excluded user IDs
    blocked_ids = set()
    for b in blocks_collection.find({"$or": [{"blocker_id": user_id}, {"blocked_id": user_id}]}):
        blocked_ids.add(b.get("blocker_id"))
        blocked_ids.add(b.get("blocked_id"))

    passed_ids = set()
    for i in interactions_collection.find({"from_user_id": user_id}):
        passed_ids.add(i.get("target_user_id"))

    # Also exclude users user disliked via matchmaker feedback
    for fb in matchmaker_feedbacks_collection.find({"user_id": user_id, "feedback": {"$in": ["not_my_type", "wrong_intent"]}}):
        passed_ids.add(fb.get("candidate_id"))

    excluded_ids = blocked_ids.union(passed_ids)
    excluded_ids.add(user_id)

    # Gender filter
    user_gender_pref = user_doc.get("gender_preference", ["female"])
    gender_query: Dict[str, Any] = {}
    if user_gender_pref and "all" not in user_gender_pref and "both" not in user_gender_pref:
        gender_query["gender"] = {"$in": user_gender_pref}

    query = {
        "id": {"$nin": list(excluded_ids)},
        "is_active": True,
        "is_suspended": {"$ne": True},
        **gender_query,
    }

    candidate_docs = list(users_collection.find(query).limit(50))
    if not candidate_docs:
        # Fallback without strict gender filter if database has few seed users
        query.pop("gender", None)
        candidate_docs = list(users_collection.find(query).limit(50))

    # Fetch quizzes for all candidates in bulk
    candidate_ids = [c["id"] for c in candidate_docs]
    candidate_quizzes_map = {}
    for q in matchmaker_profiles_collection.find({"user_id": {"$in": candidate_ids}}):
        candidate_quizzes_map[q["user_id"]] = q.get("answers", {})

    # Compute scores
    scored_candidates = []
    for cand in candidate_docs:
        cand_quiz = candidate_quizzes_map.get(cand["id"], {})
        breakdown = compute_compatibility_breakdown(user_doc, user_quiz, cand, cand_quiz)
        reasons = generate_click_reasons(breakdown, cand)
        icebreaker = generate_ai_icebreaker(user_doc, cand, breakdown)

        scored_candidates.append({
            "candidate": cand,
            "quiz": cand_quiz,
            "breakdown": breakdown,
            "reasons": reasons,
            "icebreaker": icebreaker,
            "totalScore": breakdown["totalScore"],
        })

    # Sort descending by total compatibility score
    scored_candidates.sort(key=lambda x: x["totalScore"], reverse=True)

    def _format_candidate_card(item: Dict[str, Any], badge_tag: Optional[str] = None) -> Dict[str, Any]:
        c = item["candidate"]
        photos = c.get("photos", [])
        return {
            "candidateId": c.get("id"),
            "name": c.get("name", "Spark Member"),
            "age": c.get("age", 23),
            "bio": c.get("bio", ""),
            "locationName": c.get("locationName", "Nearby"),
            "photos": photos if photos else ["https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=800&q=80"],
            "interests": c.get("interests", []),
            "prompts": c.get("prompts", []),
            "isPhotoVerified": bool(c.get("is_photo_verified") or c.get("isPhotoVerified")),
            "totalScore": item["totalScore"],
            "factors": item["breakdown"]["factors"],
            "reasons": item["reasons"],
            "aiIcebreaker": item["icebreaker"],
            "badgeTag": badge_tag or f"{item['totalScore']}% Synergy ✨",
            "relationshipIntent": item["breakdown"].get("cIntent", "Serious relationship"),
            "coreVibe": item["breakdown"].get("cVibe", "Calm"),
        }

    # 1. Daily 5 Sparks
    top_5_items = scored_candidates[:5]
    daily_sparks = [_format_candidate_card(it) for it in top_5_items]

    # 2. Hidden Gem: candidate with high score (>=70) but slightly further down or rare interests
    hidden_gem = None
    if len(scored_candidates) > 2:
        # Choose candidate from indices 2 to 6 with high interests score or verified
        for candidate_item in scored_candidates[2:]:
            if candidate_item["breakdown"]["factors"]["sharedInterests"] >= 70:
                hidden_gem = _format_candidate_card(candidate_item, badge_tag="Hidden Gem 💎")
                break
        if not hidden_gem and len(scored_candidates) > 1:
            hidden_gem = _format_candidate_card(scored_candidates[1], badge_tag="Hidden Gem 💎")

    # 3. Opposite Vibe: candidate with different core vibe but good intent/shared interests
    opposite_vibe = None
    u_vibe = user_quiz.get("vibe")
    for candidate_item in scored_candidates:
        c_vibe = candidate_item["quiz"].get("vibe")
        if u_vibe and c_vibe and u_vibe != c_vibe and candidate_item["totalScore"] >= 65:
            opposite_vibe = _format_candidate_card(candidate_item, badge_tag="Opposite Vibe ⚡")
            break

    # If user is FREE tier, gate: provide 1 preview spark, lock the rest
    if not is_vip:
        preview_spark = daily_sparks[0] if daily_sparks else None
        return {
            "isVip": False,
            "hasCompletedQuiz": bool(user_quiz),
            "previewSpark": preview_spark,
            "dailySparks": [preview_spark] if preview_spark else [],
            "hiddenGem": None,
            "oppositeVibe": None,
            "totalAvailable": len(daily_sparks),
            "lockedCount": max(len(daily_sparks) - 1, 0),
            "paywallMessage": "Upgrade to Spark VIP to unlock all Daily 5 Sparks, Hidden Gems, AI Icebreakers & deep Compatibility breakdowns!",
        }

    return {
        "isVip": True,
        "hasCompletedQuiz": bool(user_quiz),
        "dailySparks": daily_sparks,
        "hiddenGem": hidden_gem,
        "oppositeVibe": opposite_vibe,
        "totalAvailable": len(daily_sparks),
        "lockedCount": 0,
    }


# ---------------------------------------------------------------------
# 6. User Feedback & Preferences Tuning
# ---------------------------------------------------------------------
def record_matchmaker_feedback(
    user_id: str,
    candidate_id: str,
    feedback: str,
    note: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves user feedback on a matchmaker candidate:
    Feedback options: 'interested', 'not_my_type', 'too_far', 'wrong_intent', 'more_like_this'
    """
    now = datetime.utcnow()
    matchmaker_feedbacks_collection.update_one(
        {"user_id": user_id, "candidate_id": candidate_id},
        {"$set": {
            "user_id": user_id,
            "candidate_id": candidate_id,
            "feedback": feedback,
            "note": note,
            "updated_at": now
        }},
        upsert=True
    )
    return {"status": "SUCCESS", "message": "Feedback recorded. Future Sparks will reflect this preference!"}


def reset_user_matchmaker_profile(user_id: str) -> Dict[str, Any]:
    """Resets user's personality quiz and feedback preferences."""
    matchmaker_profiles_collection.delete_one({"user_id": user_id})
    matchmaker_feedbacks_collection.delete_many({"user_id": user_id})
    return {"status": "SUCCESS", "message": "Matchmaker profile & learning preferences have been reset."}
