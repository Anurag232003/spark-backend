# backend/test_secret_interests.py
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from database import (
    users_collection,
    secret_interests_collection,
    secret_matches_collection,
    matches_collection,
)
from services.secret_interest_service import (
    get_secret_interests_catalog,
    get_user_secret_interests,
    save_user_secret_interests,
    get_secret_matches_for_user,
    consent_to_reveal,
)

def run_tests():
    print("--- Running Secret Interest Match Tests ---")
    
    # 1. Test Catalog
    catalog = get_secret_interests_catalog()
    assert len(catalog) >= 20, f"Expected at least 20 catalog items, got {len(catalog)}"
    print(f"PASS: Catalog retrieved with {len(catalog)} interests")

    # Mock user IDs
    u1 = "test_secret_user_1"
    u2 = "test_secret_user_2"

    # Cleanup any previous test artifacts
    secret_interests_collection.delete_many({"user_id": {"$in": [u1, u2]}})
    pair_key = f"{min(u1, u2)}_{max(u1, u2)}"
    secret_matches_collection.delete_many({"pair_key": pair_key})
    matches_collection.delete_many({"pair_key": pair_key})

    # Ensure mock user records exist
    users_collection.update_one(
        {"id": u1},
        {"$set": {"id": u1, "name": "Aarav Sharma", "age": 24, "photos": ["https://example.com/aarav.jpg"], "bio": "Cricket enthusiast"}},
        upsert=True
    )
    users_collection.update_one(
        {"id": u2},
        {"$set": {"id": u2, "name": "Meera Patel", "age": 23, "photos": ["https://example.com/meera.jpg"], "bio": "Foodie & gamer"}},
        upsert=True
    )

    # 2. User 1 saves 5 interests
    u1_interests = ["Cricket", "Gaming", "Harry Potter", "Travel", "Street Food"]
    res1 = save_user_secret_interests(u1, u1_interests)
    assert res1["count"] == 5
    assert "Cricket" in res1["interests"]
    print("PASS: User 1 saved 5 secret interests")

    # 3. User 2 saves 5 interests sharing 3 with User 1 ("Cricket", "Gaming", "Street Food")
    u2_interests = ["Cricket", "Gaming", "Street Food", "Anime & Manga", "Chess"]
    res2 = save_user_secret_interests(u2, u2_interests)
    assert res2["count"] == 5
    print("PASS: User 2 saved 5 secret interests sharing 3 with User 1")

    # 4. Check that a secret match was detected
    m1 = get_secret_matches_for_user(u1)
    assert m1["has_active_match"] is True, "Expected active secret match for User 1"
    match_data = m1["match"]
    assert match_data["shared_count"] == 3
    assert set(match_data["common_interests"]) == {"Cricket", "Gaming", "Street Food"}
    print(f"PASS: Secret match detected with 3 common interests: {match_data['common_interests']}")

    # 5. STRICT ANONYMITY CHECK (Zero exposure before mutual consent)
    opp = match_data["opponent"]
    assert opp["is_anonymized"] is True
    assert opp["name"] == "Secret Spark ✨"
    assert len(opp["photos"]) == 0
    assert opp["age"] is None
    print("PASS: Opponent is 100% anonymized and photos/name hidden")

    # 6. User 1 consents to reveal
    match_id = match_data["id"]
    after_u1_consent = consent_to_reveal(u1, match_id)
    assert after_u1_consent["match"]["my_consent"] is True
    assert after_u1_consent["match"]["is_revealed"] is False
    assert after_u1_consent["match"]["opponent"]["is_anonymized"] is True
    print("PASS: User 1 consented, profile remains locked until User 2 also consents")

    # 7. User 2 consents to reveal -> MUTUAL REVEAL TRIGGERED!
    after_u2_consent = consent_to_reveal(u2, match_id)
    m_revealed = after_u2_consent["match"]
    assert m_revealed["is_revealed"] is True
    assert m_revealed["status"] == "REVEALED"
    assert m_revealed["match_id"] is not None
    assert m_revealed["opponent"]["is_anonymized"] is False
    assert m_revealed["opponent"]["name"] == "Aarav Sharma"
    assert len(m_revealed["opponent"]["photos"]) > 0
    print(f"PASS: Mutual reveal unlocked! Opponent is {m_revealed['opponent']['name']}, Match ID: {m_revealed['match_id']}")

    # Clean up test records
    secret_interests_collection.delete_many({"user_id": {"$in": [u1, u2]}})
    secret_matches_collection.delete_many({"pair_key": pair_key})
    matches_collection.delete_many({"pair_key": pair_key})
    users_collection.delete_many({"id": {"$in": [u1, u2]}})

    print("--- ALL SECRET INTEREST TESTS PASSED! ---")

if __name__ == "__main__":
    run_tests()
