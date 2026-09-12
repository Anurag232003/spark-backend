# backend/test_profile_update.py
from fastapi.testclient import TestClient
from main import app
from database import users_collection
from services.auth import create_access_token

client = TestClient(app)

def test_immutable_fields_and_profile_updates():
    test_user_id = "test_immutable_user_99"
    test_phone = "+919988776655"
    
    # Setup test user
    users_collection.delete_many({"id": test_user_id})
    user_doc = {
        "id": test_user_id,
        "name": "Krishna",
        "age": 24,
        "gender": "male",
        "phone": test_phone,
        "role": "user",
        "bio": "Initial bio",
        "photos": ["https://res.cloudinary.com/demo/image/upload/v1/sample.jpg"],
        "prompts": [],
        "interests": [],
        "occupation": "Student",
    }
    users_collection.insert_one(user_doc)
    token = create_access_token({"sub": test_user_id})

    try:
        # Attempt to update profile + try to maliciously tamper with name, age, phone, gender, role
        update_payload = {
            "bio": "Updated bio with passions!",
            "photos": [
                "https://res.cloudinary.com/demo/image/upload/v1/sample1.jpg",
                "https://res.cloudinary.com/demo/image/upload/v1/sample2.jpg"
            ],
            "occupation": "Senior Software Engineer",
            "company": "Tech Corp",
            "education": "IIT Delhi",
            "hometown": "New Delhi",
            "height": "5' 11''",
            "relationshipGoals": "Long-term relationship",
            "drinking": "Socially",
            "smoking": "Never",
            "exercise": "Active",
            "interests": ["Travel", "Coffee", "Music"],
            "prompts": [
                {"id": "1", "question": "My simple pleasures in life...", "answer": "Good filter coffee and rains."}
            ],
            # Attempted malicious modifications:
            "name": "Hacked Name",
            "age": 99,
            "gender": "female",
            "phone": "+910000000000",
            "role": "admin",
        }

        response = client.put(
            "/api/users/me",
            json=update_payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "SUCCESS"
        user = data["user"]

        # 1. VERIFY IMMUTABILITY: Name, Age, Gender, Phone, Role MUST NOT CHANGE
        assert user["name"] == "Krishna", f"Name changed! Expected Krishna, got {user['name']}"
        assert user["age"] == 24, f"Age changed! Expected 24, got {user['age']}"
        assert user["gender"] == "male", f"Gender changed! Expected male, got {user['gender']}"
        assert user["phone"] == test_phone, f"Phone changed! Expected {test_phone}, got {user['phone']}"
        assert user["role"] == "user", f"Role escalated! Expected user, got {user['role']}"

        # 2. VERIFY MUTABILITY: Allowed fields must be successfully updated
        assert user["bio"] == "Updated bio with passions!"
        assert len(user["photos"]) == 2
        assert user["occupation"] == "Senior Software Engineer"
        assert user["company"] == "Tech Corp"
        assert user["education"] == "IIT Delhi"
        assert user["hometown"] == "New Delhi"
        assert user["height"] == "5' 11''"
        assert user["relationshipGoals"] == "Long-term relationship"
        assert user["drinking"] == "Socially"
        assert user["smoking"] == "Never"
        assert user["exercise"] == "Active"
        assert "Travel" in user["interests"]
        assert len(user["prompts"]) == 1

        print("PASS: Immutable fields (Name, Age, Gender, Phone, Role) are strictly protected.")
        print("PASS: Allowed fields (Photos, Bio, Prompts, Vitals, Habits, Interests) updated successfully.")
    finally:
        users_collection.delete_many({"id": test_user_id})

if __name__ == "__main__":
    test_immutable_fields_and_profile_updates()
    print("--- ALL PROFILE UPDATE IMMUTABILITY TESTS PASSED ---")
