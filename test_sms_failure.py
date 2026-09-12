import os
from unittest.mock import patch
from fastapi import HTTPException
from services import notifier
from main import send_otp, SendOTPRequest
from database import otp_collection
from twilio.base.exceptions import TwilioRestException

from starlette.requests import Request

def build_request():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/send-otp",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)

def test_sms_behavior():
    print("--- Running SMS Failure & Success Tests ---")
    test_phone = "+919876543210"

    # Clean up test records
    otp_collection.delete_one({"target": test_phone})

    # 1. Simulate Twilio Failure
    with patch("services.notifier.is_twilio_configured", return_value=True):
        with patch("services.notifier.Client") as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("Twilio unreachable / Network error")
            
            success, detail = notifier.send_sms_otp(test_phone, "123456")
            assert success is False
            assert "Twilio" in detail or "error" in detail.lower()
            print(f"PASS: send_sms_otp returned False on Twilio error ({detail})")

    # 2. Simulate Twilio Rest Exception (e.g. Invalid Number / Insufficient funds)
    with patch("services.notifier.is_twilio_configured", return_value=True):
        with patch("services.notifier.Client") as mock_client:
            mock_client.return_value.messages.create.side_effect = TwilioRestException(
                status=400, uri="/Messages", msg="Authenticate failed", code=20003
            )
            
            success, detail = notifier.send_sms_otp(test_phone, "123456")
            assert success is False
            assert "20003" in detail
            print(f"PASS: TwilioRestException accurately captured ({detail})")

    # 3. Simulate send_otp endpoint behavior during SMS failure
    with patch("main.send_sms_otp", return_value=(False, "Twilio account balance zero")):
        try:
            send_otp(request=build_request(), payload=SendOTPRequest(target=test_phone))
            raise AssertionError("FAIL: send_otp should have raised HTTPException 502!")
        except HTTPException as e:
            assert e.status_code == 502
            assert "SMS delivery failed" in e.detail
            print(f"PASS: send_otp raised 502 Bad Gateway ({e.detail})")

        # Verify no OTP was written and no cooldown was started in MongoDB
        doc = otp_collection.find_one({"target": test_phone})
        assert doc is None, "FAIL: Failed SMS still saved an OTP record in database!"
        print("PASS: Zero orphaned records in MongoDB after SMS failure")

    # 4. Simulate successful dispatch
    with patch("main.send_sms_otp", return_value=(True, "Delivered via Twilio (SID: SM12345)")):
        res = send_otp(request=build_request(), payload=SendOTPRequest(target=test_phone))
        assert res["status"] == "SUCCESS"
        assert "SM12345" in res["delivery"]
        print(f"PASS: Successful delivery correctly confirmed ({res['delivery']})")

        doc = otp_collection.find_one({"target": test_phone})
        assert doc is not None
        assert "otp_hash" in doc
        print("PASS: OTP and cooldown recorded only upon verified delivery")

    # Clean up
    otp_collection.delete_one({"target": test_phone})
    print("--- ALL SMS TESTS PASSED ---")

if __name__ == "__main__":
    test_sms_behavior()
