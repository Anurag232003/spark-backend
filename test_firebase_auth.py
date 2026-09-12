# backend/test_firebase_auth.py
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app
from database import users_collection

client = TestClient(app)

def test_firebase_login_empty_token():
    response = client.post("/api/auth/firebase-login", json={"idToken": ""})
    assert response.status_code == 400
    assert "Firebase ID token is required" in response.json()["detail"]

def test_firebase_login_dev_mock_new_user():
    # Clean up test user if exists
    test_phone = "+919999988888"
    users_collection.delete_many({"phone": test_phone})

    mock_token = f"mock_firebase_token_{test_phone}"
    response = client.post("/api/auth/firebase-login", json={"idToken": mock_token})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["isRegistered"] is False
    assert "registrationToken" in data
    assert data["target"] == test_phone

def test_firebase_login_dev_mock_existing_user():
    test_phone = "+919999977777"
    users_collection.delete_many({"phone": test_phone})
    
    # Insert existing user
    user_doc = {
        "id": "test_fb_user_123",
        "name": "Firebase User",
        "phone": test_phone,
        "role": "user",
        "is_phone_verified": True,
        "is_photo_verified": False,
        "photos": [],
        "prompts": [],
        "bio": "Hello Firebase"
    }
    users_collection.insert_one(user_doc)

    try:
        mock_token = f"mock_firebase_token_{test_phone}"
        response = client.post("/api/auth/firebase-login", json={"idToken": mock_token})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert data["isRegistered"] is True
        assert "token" in data
        assert "accessToken" in data
        assert data["user"]["name"] == "Firebase User"
        assert data["user"]["id"] == "test_fb_user_123"
    finally:
        users_collection.delete_many({"phone": test_phone})

if __name__ == "__main__":
    test_firebase_login_empty_token()
    print("test_firebase_login_empty_token passed")
    test_firebase_login_dev_mock_new_user()
    print("test_firebase_login_dev_mock_new_user passed")
    test_firebase_login_dev_mock_existing_user()
    print("test_firebase_login_dev_mock_existing_user passed")
    print("All Firebase backend tests passed successfully!")
