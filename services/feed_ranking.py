"""
Feed Ranking Engine
Multi-Factor Dating Profile Scoring & Ranking Service
Evaluates candidates across 6 dimensions:
1. Location Proximity & Distance Decay (25%)
2. Preferences: Gender & Age Compatibility (20%)
3. Activity & Freshness Recency (15%)
4. Compatibility & Profile Completeness (15%)
5. Previous Interactions & Incoming Likes Priority Boost (15%)
6. Verification & Trust Badges (10%)
"""
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Tuple

# Default Scoring Weights (sum = 1.0)
WEIGHT_LOCATION = 0.20
WEIGHT_PREFERENCES = 0.15
WEIGHT_ACTIVITY = 0.15
WEIGHT_COMPATIBILITY = 0.15
WEIGHT_INTERACTION = 0.15
WEIGHT_VERIFICATION = 0.10
WEIGHT_VIBE = 0.10

DAILY_VIBE_DEFINITIONS = {
    "chill_coffee": {
        "id": "chill_coffee",
        "title": "Chill & coffee",
        "emoji": "☕",
        "label": "Chill & coffee ☕",
        "tagline": "Cozy cafe dates, latte art & relaxing afternoon strolls",
        "compatible_with": ["talkative", "movie_night", "friendship"]
    },
    "adventure": {
        "id": "adventure",
        "title": "Adventure mode",
        "emoji": "🌄",
        "label": "Adventure mode 🌄",
        "tagline": "Scenic hikes, road trips, spontaneous drives & thrills",
        "compatible_with": ["movie_night", "serious_relationship"]
    },
    "talkative": {
        "id": "talkative",
        "title": "Talkative today",
        "emoji": "💬",
        "label": "Talkative today 💬",
        "tagline": "Endless late-night banter, deep thoughts & lively stories",
        "compatible_with": ["chill_coffee", "friendship", "serious_relationship"]
    },
    "friendship": {
        "id": "friendship",
        "title": "Just friendship",
        "emoji": "🤝",
        "label": "Just friendship 🤝",
        "tagline": "Good company, mutual hobbies & zero dating pressure",
        "compatible_with": ["chill_coffee", "talkative", "movie_night"]
    },
    "serious_relationship": {
        "id": "serious_relationship",
        "title": "Serious relationship",
        "emoji": "❤️",
        "label": "Serious relationship ❤️",
        "tagline": "Intentional dating, emotional depth & building a future",
        "compatible_with": ["talkative", "adventure"]
    },
    "movie_night": {
        "id": "movie_night",
        "title": "Movie night",
        "emoji": "🎬",
        "label": "Movie night 🎬",
        "tagline": "Popcorn, multiplex screenings & binge-watching indie films",
        "compatible_with": ["chill_coffee", "friendship", "adventure"]
    }
}

def compute_location_score(distance_km: Optional[float]) -> float:
    """
    Computes location proximity score using half-life exponential decay.
    Close candidates (< 15 km) score 0.8-1.0; 50 km scores ~0.19.
    Returns 0.30 neutral baseline when distance is undetermined.
    """
    if distance_km is None:
        return 0.30
    if distance_km <= 0.0:
        return 1.0
    # Half-life exponential decay with characteristic scale of 30 km
    score = math.exp(-distance_km / 30.0)
    return max(0.0, min(1.0, score))

def compute_preferences_score(
    candidate: dict,
    current_user: dict,
    query_prefs: Optional[dict] = None
) -> float:
    """
    Computes preference alignment for gender and age.
    """
    prefs = query_prefs or current_user.get("preferences") or {}
    
    # --- 1. Gender Matching ---
    viewer_gender = str(current_user.get("gender", "")).lower()
    candidate_gender = str(candidate.get("gender", "")).lower()
    
    # Desired gender preference
    preferred_gender = prefs.get("genderPreference") or prefs.get("gender_preference")
    if not preferred_gender:
        # Default heuristic: opposite gender or all
        if viewer_gender == "male":
            preferred_gender = "female"
        elif viewer_gender == "female":
            preferred_gender = "male"
        else:
            preferred_gender = "all"
    else:
        preferred_gender = str(preferred_gender).lower()

    if preferred_gender in ["all", "both", "any"]:
        gender_score = 1.0
    elif candidate_gender == preferred_gender:
        gender_score = 1.0
    else:
        gender_score = 0.15

    # --- 2. Age Matching ---
    viewer_age = current_user.get("age", 25)
    candidate_age = candidate.get("age", 25)
    
    min_age = prefs.get("minAge") or prefs.get("min_age")
    max_age = prefs.get("maxAge") or prefs.get("max_age")
    
    if min_age is None:
        min_age = max(18, viewer_age - 5)
    if max_age is None:
        max_age = viewer_age + 6

    if min_age <= candidate_age <= max_age:
        age_score = 1.0
    else:
        delta = min(abs(candidate_age - min_age), abs(candidate_age - max_age))
        # Gaussian decay around preferred range boundaries
        age_score = math.exp(-(delta ** 2) / 18.0)

    return max(0.0, min(1.0, (0.60 * gender_score) + (0.40 * age_score)))

def compute_activity_score(candidate: dict) -> float:
    """
    Computes activity freshness score based on last_active_at or created_at.
    Active users drive real responses and instant conversations.
    """
    ts = candidate.get("last_active_at") or candidate.get("created_at")
    if not ts:
        return 0.25

    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return 0.25

    now = datetime.now(timezone.utc) if ts.tzinfo else datetime.utcnow()
    diff = now - ts
    hours_elapsed = max(0.0, diff.total_seconds() / 3600.0)

    if hours_elapsed <= 2.0:
        return 1.0
    elif hours_elapsed <= 24.0:
        return 0.85
    elif hours_elapsed <= 72.0:   # 3 days
        return 0.65
    elif hours_elapsed <= 168.0:  # 7 days
        return 0.45
    elif hours_elapsed <= 720.0:  # 30 days
        return 0.20
    else:
        return 0.05

def compute_compatibility_score(candidate: dict, current_user: dict) -> float:
    """
    Computes profile quality and compatibility based on photo richness,
    bio depth, and answered prompt similarity.
    """
    # 1. Photos depth (up to 0.4)
    photos = candidate.get("photos", [])
    if len(photos) >= 3:
        photo_score = 0.40
    elif len(photos) == 2:
        photo_score = 0.25
    elif len(photos) == 1:
        photo_score = 0.10
    else:
        photo_score = 0.0

    # 2. Bio depth (up to 0.3)
    bio = candidate.get("bio", "").strip()
    if len(bio) >= 30:
        bio_score = 0.30
    elif len(bio) > 0:
        bio_score = 0.15
    else:
        bio_score = 0.0

    # 3. Prompts completeness (up to 0.3)
    c_prompts = candidate.get("prompts", [])
    if len(c_prompts) >= 3:
        prompt_score = 0.30
    elif len(c_prompts) == 2:
        prompt_score = 0.20
    elif len(c_prompts) == 1:
        prompt_score = 0.10
    else:
        prompt_score = 0.0

    base_score = photo_score + bio_score + prompt_score

    # 4. Shared Prompt Questions Bonus (+0.15)
    user_prompt_questions = {
        p.get("question", "").strip().lower() 
        for p in current_user.get("prompts", []) 
        if p.get("question")
    }
    candidate_prompt_questions = {
        p.get("question", "").strip().lower() 
        for p in c_prompts 
        if p.get("question")
    }
    
    if user_prompt_questions and (user_prompt_questions & candidate_prompt_questions):
        base_score += 0.15

    return max(0.0, min(1.0, base_score))

def compute_interaction_score(candidate_id: str, incoming_likes_set: Set[str]) -> float:
    """
    Boosts profiles of candidates who have already liked the current user.
    Creates immediate instant match opportunities.
    """
    if candidate_id in incoming_likes_set:
        return 1.0
    return 0.30

def is_vibe_active(user_obj: dict) -> bool:
    """Checks if the user's daily vibe was set within the last 24 hours."""
    ts = user_obj.get("vibe_updated_at")
    if not ts:
        return False
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return False
    now = datetime.now(timezone.utc) if ts.tzinfo else datetime.utcnow()
    diff = now - ts
    return diff.total_seconds() <= 86400.0  # 24 hours

def compute_vibe_score(candidate: dict, current_user: dict) -> Tuple[float, Optional[dict]]:
    """
    Computes real-time mood & vibe alignment.
    Returns (vibe_score_0_to_1, vibe_match_info_dict).
    """
    user_active = is_vibe_active(current_user)
    cand_active = is_vibe_active(candidate)

    user_vibes = current_user.get("daily_vibes") or []
    cand_vibes = candidate.get("daily_vibes") or []

    if isinstance(user_vibes, str):
        user_vibes = [user_vibes]
    if isinstance(cand_vibes, str):
        cand_vibes = [cand_vibes]

    cand_primary_vibe = cand_vibes[0] if cand_vibes else candidate.get("daily_vibe")
    cand_vibe_def = DAILY_VIBE_DEFINITIONS.get(cand_primary_vibe) if cand_primary_vibe else None

    vibe_match_info = {
        "isVibeMatch": False,
        "matchedVibe": None,
        "matchedVibes": [],
        "candidateVibe": cand_primary_vibe,
        "candidateVibeLabel": cand_vibe_def["label"] if cand_vibe_def else candidate.get("daily_vibe_label"),
        "candidateVibeEmoji": cand_vibe_def["emoji"] if cand_vibe_def else "💖",
        "matchPercentage": None
    }

    if user_active and cand_active and user_vibes and cand_vibes:
        shared = set(user_vibes) & set(cand_vibes)
        if shared:
            matched_id = list(shared)[0]
            matched_def = DAILY_VIBE_DEFINITIONS.get(matched_id, {})
            vibe_match_info["isVibeMatch"] = True
            vibe_match_info["matchedVibe"] = matched_def.get("label") or matched_id
            vibe_match_info["matchedVibes"] = list(shared)
            vibe_match_info["matchPercentage"] = 92 if len(shared) > 1 else 88
            return 1.0, vibe_match_info

        is_compatible = False
        compatible_pair_name = None
        for u_v in user_vibes:
            u_compat = DAILY_VIBE_DEFINITIONS.get(u_v, {}).get("compatible_with", [])
            for c_v in cand_vibes:
                if c_v in u_compat:
                    is_compatible = True
                    u_def = DAILY_VIBE_DEFINITIONS.get(u_v, {})
                    c_def = DAILY_VIBE_DEFINITIONS.get(c_v, {})
                    compatible_pair_name = f"{u_def.get('title', '')} + {c_def.get('title', '')}"
                    break
            if is_compatible:
                break

        if is_compatible:
            vibe_match_info["isVibeMatch"] = True
            vibe_match_info["matchedVibe"] = compatible_pair_name or "Compatible Vibes"
            vibe_match_info["matchedVibes"] = list(set(user_vibes + cand_vibes))
            vibe_match_info["matchPercentage"] = 82
            return 0.80, vibe_match_info

        return 0.40, vibe_match_info

    if cand_active and cand_vibes:
        return 0.50, vibe_match_info

    return 0.25, vibe_match_info

def compute_verification_score(candidate: dict) -> float:
    """
    Rewards authentic, verified profiles (photo selfie verification & phone verification).
    """
    score = 0.0
    if candidate.get("is_photo_verified") or candidate.get("isPhotoVerified"):
        score += 0.70
    if candidate.get("is_phone_verified"):
        score += 0.30
    return max(0.0, min(1.0, score))

def compute_candidate_score(
    candidate: dict,
    current_user: dict,
    incoming_likes_set: Set[str],
    distance_km: Optional[float],
    query_prefs: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Computes all component sub-scores and overall composite score.
    Returns composite score and detailed breakdown.
    """
    loc_score = compute_location_score(distance_km)
    pref_score = compute_preferences_score(candidate, current_user, query_prefs)
    act_score = compute_activity_score(candidate)
    compat_score = compute_compatibility_score(candidate, current_user)
    interact_score = compute_interaction_score(candidate["id"], incoming_likes_set)
    verify_score = compute_verification_score(candidate)
    vibe_score, vibe_info = compute_vibe_score(candidate, current_user)

    composite = (
        (WEIGHT_LOCATION * loc_score) +
        (WEIGHT_PREFERENCES * pref_score) +
        (WEIGHT_ACTIVITY * act_score) +
        (WEIGHT_COMPATIBILITY * compat_score) +
        (WEIGHT_INTERACTION * interact_score) +
        (WEIGHT_VERIFICATION * verify_score) +
        (WEIGHT_VIBE * vibe_score)
    )
    
    composite = round(max(0.0, min(1.0, composite)), 4)
    match_score = round(composite * 100.0, 1)

    return {
        "composite_score": composite,
        "match_score": match_score,
        "vibe_match": vibe_info,
        "breakdown": {
            "location": round(loc_score, 3),
            "preferences": round(pref_score, 3),
            "activity": round(act_score, 3),
            "compatibility": round(compat_score, 3),
            "interaction": round(interact_score, 3),
            "verification": round(verify_score, 3),
            "vibe": round(vibe_score, 3),
        }
    }

def rank_feed_candidates(
    candidates: List[dict],
    current_user: dict,
    incoming_likes_set: Set[str],
    distance_map: Dict[str, Optional[float]],
    query_prefs: Optional[dict] = None,
    limit: int = 20
) -> List[dict]:
    """
    Ranks a pool of candidates using the multi-factor scoring engine.
    Sorts descending by composite match score.
    """
    scored_profiles = []
    for candidate in candidates:
        cand_id = candidate["id"]
        dist = distance_map.get(cand_id)
        
        score_info = compute_candidate_score(
            candidate=candidate,
            current_user=current_user,
            incoming_likes_set=incoming_likes_set,
            distance_km=dist,
            query_prefs=query_prefs
        )

        item = {
            "id": candidate["id"],
            "name": candidate["name"],
            "age": candidate["age"],
            "gender": candidate.get("gender"),
            "locationName": candidate.get("locationName") or "Nearby",
            "distanceKm": dist,
            "bio": candidate.get("bio", ""),
            "photos": candidate.get("photos", []),
            "prompts": candidate.get("prompts", []),
            "isPhotoVerified": candidate.get("is_photo_verified", False),
            "dailyVibes": candidate.get("daily_vibes", []),
            "dailyVibeLabel": candidate.get("daily_vibe_label"),
            "vibeMatch": score_info["vibe_match"],
            "matchScore": score_info["match_score"],
            "_rankingSignals": score_info["breakdown"],
            "_compositeScore": score_info["composite_score"],
        }
        scored_profiles.append(item)

    # Sort descending by composite score, then ascending by distance if scores tie
    scored_profiles.sort(
        key=lambda x: (
            -x["_compositeScore"],
            x["distanceKm"] if x["distanceKm"] is not None else float("inf")
        )
    )

    return scored_profiles[:limit]
