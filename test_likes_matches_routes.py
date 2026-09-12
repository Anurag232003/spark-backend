"""
Test Suite: Likes and Matches Parameterized Endpoints
Routes tested:
- GET /api/users/me/likes
- GET /api/users/{target_user_id}/likes (self vs 3rd-party)
- GET /api/users/me/matches
- GET /api/users/{target_user_id}/matches (self vs 3rd-party)
"""
from datetime import datetime
from fastapi import HTTPException
from database import users_collection, interactions_collection, matches_collection, blocks_collection
import main
from main import get_my_likes, get_user_likes, get_my_matches, get_user_matches

def test_likes_matches_routes():
    print("--- Running Likes & Matches Parameterized Endpoints Tests ---")

    test_user_1 = {
        "id": "u_test_likes_1",
        "name": "Aarav Sharma",
        "age": 24,
        "gender": "male",
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample1.jpg"]
    }

    test_user_2 = {
        "id": "u_test_likes_2",
        "name": "Priya Patel",
        "age": 23,
        "gender": "female",
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample2.jpg"]
    }

    # Clean up previous test state if any
    users_collection.delete_one({"id": test_user_1["id"]})
    users_collection.delete_one({"id": test_user_2["id"]})
    interactions_collection.delete_many({
        "$or": [
            {"from_user_id": test_user_1["id"]},
            {"target_user_id": test_user_1["id"]},
            {"from_user_id": test_user_2["id"]},
            {"target_user_id": test_user_2["id"]}
        ]
    })
    matches_collection.delete_many({
        "$or": [
            {"user1_id": test_user_1["id"]},
            {"user2_id": test_user_1["id"]},
            {"user1_id": test_user_2["id"]},
            {"user2_id": test_user_2["id"]}
        ]
    })

    # Upsert test users
    users_collection.insert_one(test_user_1)
    users_collection.insert_one(test_user_2)

    # Insert a LIKE interaction from test_user_2 to test_user_1
    like_interaction = {
        "from_user_id": test_user_2["id"],
        "target_user_id": test_user_1["id"],
        "type": "LIKE",
        "target_item_type": "PHOTO",
        "comment": "Nice smile!",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    interactions_collection.insert_one(like_interaction)

    try:
        # 1. Test GET /api/users/me/likes directly
        res_me_likes = get_my_likes(current_user=test_user_1)
        assert res_me_likes["status"] == "SUCCESS"
        assert len(res_me_likes["likes"]) == 1
        assert res_me_likes["likes"][0]["senderId"] == "u_test_likes_2"
        assert res_me_likes["likes"][0]["comment"] == "Nice smile!"
        print("PASS: get_my_likes returns incoming likes")

        # 2. Test GET /api/users/{target_user_id}/likes for self (own userId)
        res_self_likes = get_user_likes(target_user_id="u_test_likes_1", current_user=test_user_1)
        assert res_self_likes["status"] == "SUCCESS"
        assert len(res_self_likes["likes"]) == 1
        assert res_self_likes["likes"][0]["senderId"] == "u_test_likes_2"
        print("PASS: get_user_likes with own userId returns incoming likes")

        # 3. Test GET /api/users/{target_user_id}/likes for self with 'me' alias
        res_me_alias = get_user_likes(target_user_id="me", current_user=test_user_1)
        assert res_me_alias["status"] == "SUCCESS"
        assert len(res_me_alias["likes"]) == 1
        print("PASS: get_user_likes with 'me' alias returns incoming likes")

        # 4. Test GET /api/users/{target_user_id}/likes for 3rd-party user (should raise 403 Forbidden)
        try:
            get_user_likes(target_user_id="u_test_likes_2", current_user=test_user_1)
            assert False, "Should have raised 403 Forbidden for another user's likes"
        except HTTPException as e:
            assert e.status_code == 403
            assert "Unauthorized" in e.detail
            print("PASS: get_user_likes rejects unauthorized access to another user's likes with 403")

        # 5. Test GET /api/users/me/matches
        res_me_matches = get_my_matches(current_user=test_user_1)
        assert res_me_matches["status"] == "SUCCESS"
        assert isinstance(res_me_matches["matches"], list)
        print("PASS: get_my_matches returns matches list")

        # 6. Test GET /api/users/{target_user_id}/matches for self
        res_self_matches = get_user_matches(target_user_id="u_test_likes_1", current_user=test_user_1)
        assert res_self_matches["status"] == "SUCCESS"
        print("PASS: get_user_matches with own userId succeeds")

        # 7. Test GET /api/users/{target_user_id}/matches for 3rd-party user (should raise 403 Forbidden)
        try:
            get_user_matches(target_user_id="u_test_likes_2", current_user=test_user_1)
            assert False, "Should have raised 403 Forbidden for another user's matches"
        except HTTPException as e:
            assert e.status_code == 403
            assert "Unauthorized" in e.detail
            print("PASS: get_user_matches rejects unauthorized access to another user's matches with 403")

        print("--- ALL LIKES & MATCHES ROUTE TESTS PASSED ---")

    finally:
        # Cleanup
        users_collection.delete_one({"id": test_user_1["id"]})
        users_collection.delete_one({"id": test_user_2["id"]})
        interactions_collection.delete_many({
            "$or": [
                {"from_user_id": test_user_1["id"]},
                {"target_user_id": test_user_1["id"]},
                {"from_user_id": test_user_2["id"]},
                {"target_user_id": test_user_2["id"]}
            ]
        })

if __name__ == "__main__":
    test_likes_matches_routes()
