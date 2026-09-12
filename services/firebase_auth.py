# backend/services/firebase_auth.py
import os
import json
import logging
from typing import Tuple, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

FIREBASE_CONFIG_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
FIREBASE_CONFIG_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
APP_ENV = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()

_firebase_initialized = False
_firebase_auth_module = None

def get_firebase_auth():
    """Lazily initializes and returns the Firebase Auth module."""
    global _firebase_initialized, _firebase_auth_module
    if _firebase_initialized:
        return _firebase_auth_module

    try:
        import firebase_admin
        from firebase_admin import credentials, auth

        if not firebase_admin._apps:
            cred = None
            if FIREBASE_CONFIG_PATH and os.path.exists(FIREBASE_CONFIG_PATH):
                cred = credentials.Certificate(FIREBASE_CONFIG_PATH)
                logger.info(f"Loaded Firebase credentials from file: {FIREBASE_CONFIG_PATH}")
            elif FIREBASE_CONFIG_JSON:
                try:
                    service_account_info = json.loads(FIREBASE_CONFIG_JSON)
                    cred = credentials.Certificate(service_account_info)
                    logger.info("Loaded Firebase credentials from environment JSON string.")
                except Exception as ex:
                    logger.error(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {ex}")
            
            options = {}
            if FIREBASE_PROJECT_ID:
                options["projectId"] = FIREBASE_PROJECT_ID

            if cred:
                firebase_admin.initialize_app(cred, options)
                _firebase_auth_module = auth
                _firebase_initialized = True
                logger.info("Firebase Admin SDK successfully initialized with Service Account.")
            elif FIREBASE_PROJECT_ID:
                # Default application credentials (GCP / environment)
                firebase_admin.initialize_app(options=options)
                _firebase_auth_module = auth
                _firebase_initialized = True
                logger.info("Firebase Admin SDK initialized with Project ID.")
            else:
                logger.warning("Firebase credentials not provided. Firebase verification will operate in mock mode if in development.")
                _firebase_initialized = False
                return None
        else:
            _firebase_auth_module = auth
            _firebase_initialized = True

        return _firebase_auth_module
    except Exception as e:
        logger.error(f"Firebase Admin initialization error: {e}")
        return None

def is_firebase_configured() -> bool:
    """Returns True if Firebase credentials are valid and active."""
    return get_firebase_auth() is not None

def verify_firebase_phone_token(id_token: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Verifies a Firebase ID token generated from Phone Authentication.
    
    Returns:
        (is_valid: bool, verified_phone_number: Optional[str], error_message: Optional[str])
    """
    if not id_token:
        return False, None, "Firebase ID Token is empty or missing."

    # Development Mock token fallback
    if APP_ENV != "production" and id_token.startswith("mock_firebase_token_"):
        # Format: mock_firebase_token_+919876543210
        phone_part = id_token.replace("mock_firebase_token_", "").strip()
        if phone_part:
            logger.info(f"[DEV MODE] Verified mock Firebase token for phone: {phone_part}")
            return True, phone_part, None
        return False, None, "Invalid mock Firebase token format."

    auth_module = get_firebase_auth()
    if not auth_module:
        if APP_ENV != "production":
            return False, None, "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH in .env or use dev mock."
        return False, None, "Firebase authentication service is not configured on the server."

    try:
        # Verify the ID token using Firebase Admin SDK
        decoded_token = auth_module.verify_id_token(id_token)
        phone_number = decoded_token.get("phone_number")
        
        if not phone_number:
            return False, None, "Firebase token did not contain a verified phone_number claim."
            
        return True, phone_number, None
    except Exception as e:
        logger.error(f"Firebase token verification failed: {str(e)}")
        return False, None, f"Invalid or expired Firebase token: {str(e)}"
