"""
Test Suite: Issue 52 - Multi-Factor Feed Ranking Engine
Verifies:
1. Incoming Likes Priority Boost (Instant match opportunity)
2. Location Proximity & Distance Decay
3. Activity Recency Boost (online freshness)
4. Verification & Trust Badges
5. Preferences Alignment (Gender & Age Window)
6. Preferences REST Endpoints (GET/PUT /api/users/me/preferences)
"""
from datetime import datetime, timedelta
from database import users_collection, interactions_collection
from main import (
    get_discovery_feed,
    get_my_preferences,
    update_my_preferences,
    UpdatePreferencesRequest,
)
from services.feed_ranking import (
    compute_location_score,
    compute_preferences_score,
    compute_activity_score,
    compute_compatibility_score,
    compute_interaction_score,
    compute_verification_score,
    compute_candidate_score,
    rank_feed_candidates,
)

def test_feed_ranking():
    print("--- Running Issue 52 Feed Ranking Engine Test Suite ---")

    viewer = {
        "id": "u_rank_viewer",
        "name": "Alex Viewer",
        "age": 26,
        "gender": "male",
        "locationName": "Delhi NCR, India",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "location": {"type": "Point", "coordinates": [77.2090, 28.6139]},
        "preferences": {
            "genderPreference": "female",
            "minAge": 22,
            "maxAge": 29,
            "maxDistanceKm": 50.0
        },
        "prompts": [{"id": "p1", "question": "Dating me is like...", "answer": "Adventures!"}],
        "photos": ["https://res.cloudinary.com/demo/image/upload/user.jpg"]
    }

    # 1. Test Component Mathematical Scores
    print("\n--- 1. Testing Component Scoring Functions ---")
    
    # Location decay
    loc_close = compute_location_score(3.0)
    loc_far = compute_location_score(80.0)
    assert loc_close > loc_far, f"Close distance ({loc_close}) must score higher than far ({loc_far})"
    assert loc_close >= 0.85
    print(f"PASS: Location decay: 3 km ({loc_close:.3f}) > 80 km ({loc_far:.3f})")

    # Preferences: Gender & Age
    cand_match = {"id": "c1", "gender": "female", "age": 25}
    cand_gender_mismatch = {"id": "c2", "gender": "male", "age": 25}
    cand_age_far = {"id": "c3", "gender": "female", "age": 52}
    
    pref_match = compute_preferences_score(cand_match, viewer)
    pref_gender_mis = compute_preferences_score(cand_gender_mismatch, viewer)
    pref_age_mis = compute_preferences_score(cand_age_far, viewer)
    
    assert pref_match > pref_gender_mis, "Matching gender must score higher"
    assert pref_match > pref_age_mis, "Matching age window must score higher"
    print(f"PASS: Preferences: Matching ({pref_match:.2f}) > Gender mismatch ({pref_gender_mis:.2f}) & Age mismatch ({pref_age_mis:.2f})")

    # Activity: Recency
    now = datetime.utcnow()
    act_fresh = compute_activity_score({"last_active_at": now - timedelta(minutes=30)})
    act_stale = compute_activity_score({"last_active_at": now - timedelta(days=20)})
    assert act_fresh > act_stale, "Recent activity must score higher"
    print(f"PASS: Activity recency: Active 30m ago ({act_fresh:.2f}) > 20d ago ({act_stale:.2f})")

    # Verification
    verify_both = compute_verification_score({"is_photo_verified": True, "is_phone_verified": True})
    verify_none = compute_verification_score({"is_photo_verified": False, "is_phone_verified": False})
    assert verify_both == 1.0
    assert verify_none == 0.0
    print("PASS: Verification: Verified profiles get trust bonus")

    # Interaction: Incoming likes boost
    interact_incoming = compute_interaction_score("c_fan", {"c_fan", "other"})
    interact_none = compute_interaction_score("c_normal", {"other"})
    assert interact_incoming == 1.0
    assert interact_none == 0.30
    print("PASS: Incoming likes priority boost grants 1.0 interaction score")

    # 2. Test End-to-End Feed Integration with Database Fixtures
    print("\n--- 2. Testing End-to-End Feed Priority Ordering ---")

    # Candidate A: Sent an incoming like to viewer!
    cand_incoming_like = {
        "id": "u_cand_incoming_like",
        "name": "Sarah (Liked You)",
        "age": 25,
        "gender": "female",
        "locationName": "Delhi",
        "latitude": 28.6200,
        "longitude": 77.2100,
        "location": {"type": "Point", "coordinates": [77.2100, 28.6200]},
        "bio": "Enthusiastic photographer and traveler who loves chai.",
        "photos": ["https://res.cloudinary.com/demo/image/upload/s1.jpg", "https://res.cloudinary.com/demo/image/upload/s2.jpg"],
        "prompts": [{"id": "p1", "question": "Dating me is like...", "answer": "Great coffee!"}],
        "is_photo_verified": True,
        "last_active_at": now - timedelta(minutes=15)
    }

    # Candidate B: Identical to Candidate A, but has NOT liked the viewer
    cand_no_interaction = {
        "id": "u_cand_no_interaction",
        "name": "Priya (No Like Yet)",
        "age": 25,
        "gender": "female",
        "locationName": "Delhi",
        "latitude": 28.6200,
        "longitude": 77.2100,
        "location": {"type": "Point", "coordinates": [77.2100, 28.6200]},
        "bio": "Enthusiastic photographer and traveler who loves chai.",
        "photos": ["https://res.cloudinary.com/demo/image/upload/s1.jpg", "https://res.cloudinary.com/demo/image/upload/s2.jpg"],
        "prompts": [{"id": "p1", "question": "Dating me is like...", "answer": "Great coffee!"}],
        "is_photo_verified": True,
        "last_active_at": now - timedelta(minutes=15)
    }

    # Candidate C: Inactive for months and unverified
    cand_inactive = {
        "id": "u_cand_inactive",
        "name": "Inactive User",
        "age": 25,
        "gender": "female",
        "locationName": "Delhi",
        "latitude": 28.6200,
        "longitude": 77.2100,
        "location": {"type": "Point", "coordinates": [77.2100, 28.6200]},
        "bio": "",
        "photos": ["https://res.cloudinary.com/demo/image/upload/s1.jpg"],
        "prompts": [],
        "is_photo_verified": False,
        "last_active_at": now - timedelta(days=60)
    }

    test_ids = [viewer["id"], cand_incoming_like["id"], cand_no_interaction["id"], cand_inactive["id"]]
    users_collection.delete_many({"id": {"$in": test_ids}})
    interactions_collection.delete_many({"$or": [{"from_user_id": {"$in": test_ids}}, {"target_user_id": {"$in": test_ids}}]})

    # Insert test users
    users_collection.insert_one(viewer)
    users_collection.insert_one(cand_incoming_like)
    users_collection.insert_one(cand_no_interaction)
    users_collection.insert_one(cand_inactive)

    # Candidate A sends an incoming LIKE to viewer!
    interactions_collection.insert_one({
        "from_user_id": cand_incoming_like["id"],
        "target_user_id": viewer["id"],
        "action_type": "LIKE",
        "created_at": now - timedelta(hours=1)
    })

    try:
        # Fetch feed
        feed_res = get_discovery_feed(current_user=viewer)
        profiles = feed_res["profiles"]
        profile_ids = [p["id"] for p in profiles]

        assert cand_incoming_like["id"] in profile_ids
        assert cand_no_interaction["id"] in profile_ids
        assert cand_inactive["id"] in profile_ids

        # Incoming like must rank #1 ahead of identical candidate without like!
        idx_incoming = profile_ids.index(cand_incoming_like["id"])
        idx_no_like = profile_ids.index(cand_no_interaction["id"])
        idx_inactive = profile_ids.index(cand_inactive["id"])

        score_incoming = profiles[idx_incoming].get("matchScore", 0)
        score_no_like = profiles[idx_no_like].get("matchScore", 0)
        score_inactive = profiles[idx_inactive].get("matchScore", 0)

        print(f"Candidate with Incoming Like matchScore: {score_incoming}")
        print(f"Candidate without Incoming Like matchScore: {score_no_like}")
        print(f"Inactive / incomplete candidate matchScore: {score_inactive}")

        assert idx_incoming < idx_no_like, "Profile with incoming like must rank ahead of profile without like!"
        assert score_incoming > score_no_like, "Profile with incoming like must have higher matchScore!"
        assert idx_no_like < idx_inactive, "Active verified profile must rank ahead of inactive unverified profile!"
        assert score_no_like > score_inactive, "Active profile must have higher matchScore than inactive profile!"
        print("PASS: Ranking correctly orders: Incoming Like (#1) > No Like (#2) > Inactive (#3)")

        # 3. Test Preferences REST Endpoints (GET & PUT)
        print("\n--- 3. Testing Preferences Endpoints ---")
        get_res = get_my_preferences(current_user=viewer)
        assert get_res["status"] == "SUCCESS"
        assert get_res["preferences"]["genderPreference"] == "female"
        print("PASS: GET /api/users/me/preferences returned current preferences")

        # Update preferences
        update_req = UpdatePreferencesRequest(minAge=23, maxAge=31, genderPreference="female", maxDistanceKm=25.0)
        put_res = update_my_preferences(payload=update_req, current_user=viewer)
        assert put_res["status"] == "SUCCESS"
        
        updated_db_user = users_collection.find_one({"id": viewer["id"]})
        assert updated_db_user["preferences"]["minAge"] == 23
        assert updated_db_user["preferences"]["maxAge"] == 31
        assert updated_db_user["preferences"]["maxDistanceKm"] == 25.0
        print("PASS: PUT /api/users/me/preferences updated preferences in MongoDB")

        print("\n--- ALL ISSUE 52 FEED RANKING TESTS PASSED SUCCESSFULLY! ---")

    finally:
        users_collection.delete_many({"id": {"$in": test_ids}})
        interactions_collection.delete_many({"$or": [{"from_user_id": {"$in": test_ids}}, {"target_user_id": {"$in": test_ids}}]})

if __name__ == "__main__":
    test_feed_ranking()
