"""
Test Suite: User Profile Endpoints (/api/users/me and /api/users/{target_user_id})
"""
from fastapi import HTTPException
from database import users_collection, blocks_collection
import main
from main import get_my_profile, get_user_by_id

def test_user_profile_endpoints():
    print("--- Running User Profile Endpoints Tests ---")

    test_user_1 = {
        "id": "u_test_profile_1",
        "name": "Aarav Sharma",
        "age": 24,
        "gender": "male",
        "bio": "Coffee and tech.",
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": [{"id": "p1", "question": "Dating me is...", "answer": "Fun"}],
        "is_photo_verified": True,
        "locationName": "Delhi NCR, India"
    }

    test_user_2 = {
        "id": "u_test_profile_2",
        "name": "Priya Patel",
        "age": 23,
        "gender": "female",
        "bio": "Music and books.",
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample2.jpg"],
        "prompts": [{"id": "p2", "question": "Together we could...", "answer": "Travel"}],
        "is_photo_verified": False,
        "locationName": "Mumbai, India"
    }

    # Upsert test users into DB
    users_collection.update_one({"id": test_user_1["id"]}, {"$set": test_user_1}, upsert=True)
    users_collection.update_one({"id": test_user_2["id"]}, {"$set": test_user_2}, upsert=True)

    try:
        # 1. Test GET /api/users/me
        res_me = get_my_profile(current_user=test_user_1)
        assert res_me["status"] == "SUCCESS"
        assert res_me["user"]["id"] == "u_test_profile_1"
        assert res_me["user"]["name"] == "Aarav Sharma"
        assert res_me["user"]["is_photo_verified"] is True
        print("PASS: get_my_profile (/api/users/me) returns authenticated user profile")

        # 2. Test GET /api/users/{target_user_id} for self
        res_self = get_user_by_id(target_user_id="u_test_profile_1", current_user=test_user_1)
        assert res_self["status"] == "SUCCESS"
        assert res_self["user"]["id"] == "u_test_profile_1"
        print("PASS: get_user_by_id (/api/users/u_test_profile_1) returns self profile")

        # 3. Test GET /api/users/me through get_user_by_id
        res_me_alias = get_user_by_id(target_user_id="me", current_user=test_user_1)
        assert res_me_alias["status"] == "SUCCESS"
        assert res_me_alias["user"]["id"] == "u_test_profile_1"
        print("PASS: get_user_by_id (/api/users/me) alias correctly resolved")

        # 4. Test GET /api/users/{target_user_id} for another user
        res_other = get_user_by_id(target_user_id="u_test_profile_2", current_user=test_user_1)
        assert res_other["status"] == "SUCCESS"
        assert res_other["user"]["id"] == "u_test_profile_2"
        assert res_other["user"]["name"] == "Priya Patel"
        print("PASS: get_user_by_id (/api/users/u_test_profile_2) returns target user public profile")

        # 5. Test Block Enforcement
        blocks_collection.insert_one({
            "blocker_user_id": "u_test_profile_1",
            "target_user_id": "u_test_profile_2"
        })
        try:
            get_user_by_id(target_user_id="u_test_profile_2", current_user=test_user_1)
            assert False, "Should have raised 404 for blocked user"
        except HTTPException as e:
            assert e.status_code == 404
            print("PASS: Blocked user returns 404 Not Found")
        finally:
            blocks_collection.delete_many({
                "blocker_user_id": "u_test_profile_1",
                "target_user_id": "u_test_profile_2"
            })

        # 6. Test Non-existent User
        try:
            get_user_by_id(target_user_id="u_non_existent_9999", current_user=test_user_1)
            assert False, "Should have raised 404 for non-existent user"
        except HTTPException as e:
            assert e.status_code == 404
            print("PASS: Non-existent user returns 404 Not Found")

        print("--- ALL USER PROFILE TESTS PASSED ---")

    finally:
        users_collection.delete_one({"id": test_user_1["id"]})
        users_collection.delete_one({"id": test_user_2["id"]})

if __name__ == "__main__":
    test_user_profile_endpoints()
