import os
import io
from pydantic import ValidationError
from fastapi import HTTPException
from main import RegisterRequest
from services.image_validator import is_safe_cdn_url, download_safe_profile_image

def test_ssrf_and_lfi():
    print("--- Running SSRF & Path Traversal / LFI Prevention Tests ---")
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "gvw5bnvn")

    base_payload = {
        "name": "Ananya Roy",
        "age": 23,
        "gender": "female",
        "phone": "+919876543210",
        "locationName": "Mumbai, India",
        "prompts": [{"id": "p1", "question": "Q?", "answer": "A!"}]
    }

    valid_url = f"https://res.cloudinary.com/{cloud_name}/image/upload/v1234/photo.jpg"

    # 1. Valid registration with official Cloudinary CDN photo
    ok = RegisterRequest(**{**base_payload, "photos": [valid_url]})
    assert ok.photos[0] == valid_url
    print("PASS: Official Cloudinary CDN URL accepted")

    # 2. SSRF Attack: AWS Metadata IP
    ssrf_attacks = [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/api/admin",
        "http://localhost:8000",
        "http://192.168.1.1/admin",
        "https://attacker.com/profile.jpg",
        "https://res.cloudinary.com/unauthorized_cloud/photo.jpg",
        "file:///etc/passwd",
        "C:\\Windows\\System32\\cmd.exe",
        "../../backend/.env",
        ".env"
    ]

    for attack_url in ssrf_attacks:
        try:
            RegisterRequest(**{**base_payload, "photos": [attack_url]})
            raise AssertionError(f"FAIL: Attack URL was accepted: {attack_url}")
        except ValidationError:
            print(f"PASS: Blocked in registration schema: {attack_url}")

    # 3. Path Traversal in download_safe_profile_image
    try:
        download_safe_profile_image(valid_url, "../../sensitive_file.jpg", upload_dir="./temp_uploads")
        raise AssertionError("FAIL: Path traversal outside upload_dir was allowed!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Blocked path traversal destination ({e.detail})")

    # 4. SSRF in download_safe_profile_image
    try:
        download_safe_profile_image("http://169.254.169.254/secret", "./temp_uploads/test.jpg")
        raise AssertionError("FAIL: SSRF URL was permitted in download_safe_profile_image!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Blocked SSRF URL in download service ({e.detail})")

    print("--- ALL SSRF & LFI PREVENTION TESTS PASSED ---")

if __name__ == "__main__":
    test_ssrf_and_lfi()
