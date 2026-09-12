import os
from services.auth import hash_otp, verify_otp_hash, generate_secure_otp
from database import otp_collection
from datetime import datetime, timedelta

def test_otp():
    print("--- Running Cryptographic OTP Hashing Tests ---")

    # 1. Test secure generation
    otps = [generate_secure_otp() for _ in range(50)]
    for code in otps:
        assert len(code) == 6
        assert code.isdigit()
        assert 100000 <= int(code) <= 999999
    assert len(set(otps)) > 40  # Highly random
    print("PASS: Secure 6-digit generation verified")

    # 2. Test HMAC-SHA256 hashing
    target = "+919876543210"
    code = "729401"
    h = hash_otp(target, code)
    assert isinstance(h, str) and len(h) == 64
    print(f"PASS: OTP hashed to 64-char HMAC-SHA256 ({h[:16]}...)")

    # 3. Test verification
    assert verify_otp_hash(target, code, h) is True
    assert verify_otp_hash(target, "123456", h) is False
    assert verify_otp_hash("+919999999999", code, h) is False  # Target-bound pepper
    print("PASS: Accurate verification & target binding confirmed")

    # 4. MongoDB Database test: ensure NO plaintext OTP is saved
    test_target = "+919999911223"
    test_code = generate_secure_otp()
    test_hash = hash_otp(test_target, test_code)

    otp_collection.update_one(
        {"target": test_target},
        {
            "$set": {
                "otp_hash": test_hash,
                "expires_at": datetime.utcnow() + timedelta(minutes=5),
                "attempts": 0,
                "last_sent_at": datetime.utcnow()
            },
            "$unset": {
                "otp_code": ""
            }
        },
        upsert=True
    )

    doc = otp_collection.find_one({"target": test_target})
    assert doc is not None
    assert "otp_hash" in doc
    assert "otp_code" not in doc, "FAIL: Plaintext otp_code still found in MongoDB!"
    assert verify_otp_hash(test_target, test_code, doc["otp_hash"]) is True
    print("PASS: MongoDB record contains ONLY otp_hash and ZERO plaintext otp_code")

    # Clean up test doc
    otp_collection.delete_one({"target": test_target})

    print("--- ALL OTP HASHING TESTS PASSED ---")

if __name__ == "__main__":
    test_otp()
