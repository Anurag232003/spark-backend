# backend/ml_services/verification.py
import requests

# Colab se mila hua ngrok HTTPS URL (bina trailing slash ke)
COLAB_MICROSERVICE_URL = "https://tigress-grip-crushed.ngrok-free.dev"

def verify_user_selfie(profile_path: str, selfie_path: str) -> dict:
    """
    Sends registered profile image and captured live selfie to Google Colab GPU
    microservice for DeepFace facial embedding verification.
    """
    if not COLAB_MICROSERVICE_URL or "ngrok" not in COLAB_MICROSERVICE_URL:
        print("[WARNING] Colab ngrok URL set nahi hai! Mock mode me fallback ho raha hai.")
        return {"verified": True, "distance": 0.18, "threshold": 0.30, "model": "Mock-Dev"}

    try:
        with open(profile_path, "rb") as f_profile, open(selfie_path, "rb") as f_selfie:
            files = {
                "profile_photo": ("profile.jpg", f_profile, "image/jpeg"),
                "selfie": ("selfie.jpg", f_selfie, "image/jpeg")
            }
            # Colab ngrok browser warning header bypass
            headers = {"ngrok-skip-browser-warning": "true"}

            response = requests.post(
                f"{COLAB_MICROSERVICE_URL}/verify",
                files=files,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                print(f"✅ [COLAB GPU RESULT] Verified: {data.get('verified')} | Distance: {data.get('distance')}")
                return data
            else:
                print(f"❌ [COLAB ERROR] Status {response.status_code}: {response.text}")
                return {"verified": False, "error": f"Colab error: {response.status_code}"}

    except requests.exceptions.Timeout:
        print("❌ [COLAB TIMEOUT] Google Colab worker took too long to respond.")
        return {"verified": False, "error": "Verification service timed out."}
    except Exception as e:
        print(f"❌ [COLAB REQUEST FAILED] {str(e)}")
        return {"verified": False, "error": str(e)}