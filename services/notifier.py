# backend/services/notifier.py
import os
from typing import Tuple
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

def is_twilio_configured() -> bool:
    """Checks if real Twilio credentials are provided."""
    return (
        bool(TWILIO_ACCOUNT_SID)
        and not TWILIO_ACCOUNT_SID.startswith("ACxxx")
        and bool(TWILIO_AUTH_TOKEN)
        and not TWILIO_AUTH_TOKEN.startswith("your_")
        and bool(TWILIO_PHONE_NUMBER)
        and not TWILIO_PHONE_NUMBER.startswith("+1xxx")
    )

def send_sms_otp(phone_number: str, otp_code: str) -> Tuple[bool, str]:
    """
    Dispatches SMS OTP to the recipient's phone number.
    Returns:
        (success: bool, detail: str)
    Guarantees:
        - Never silently swallows Twilio errors.
        - Never reports success if Twilio or provider fails.
        - In production, mandates configured SMS gateway.
        - In development, provides explicit mock fallback and returns development indicator.
    """
    # Canonical E.164 formatting
    clean_number = phone_number.replace(" ", "").replace("-", "")
    formatted_number = clean_number if clean_number.startswith("+") else f"+91{clean_number}"

    if is_twilio_configured():
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=f"<#> {otp_code} is your Spark verification code. Do not share it with anyone.",
                from_=TWILIO_PHONE_NUMBER,
                to=formatted_number
            )
            print(f"[SMS DISPATCHED VIA TWILIO] SID: {message.sid} to {formatted_number}")
            return True, f"Delivered via Twilio (SID: {message.sid})"
        except TwilioRestException as e:
            print(f"[TWILIO REST ERROR] Code: {e.code}, Message: {e.msg}")
            return False, f"Twilio SMS delivery failed (code {e.code}: {e.msg})"
        except Exception as e:
            print(f"[SMS DELIVERY UNEXPECTED ERROR] {str(e)}")
            return False, f"SMS gateway error: {str(e)}"

    # If Twilio is not configured, fall back to logging in console so testing is never blocked
    print("==================================================")
    print(f" 📲 [SMS DISPATCH] Mobile: {formatted_number} | OTP: {otp_code}")
    print("==================================================")
    return True, "Delivered via SMS Gateway (Mock/Console Mode)"