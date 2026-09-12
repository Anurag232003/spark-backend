# backend/services/cloudinary_uploader.py
import os
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

def upload_image_to_cloud(file_obj, folder: str = "spark_dating_profiles") -> str:
    """
    Image binary stream ko Cloudinary par upload karke secure CDN URL return karta hai.
    """
    try:
        response = cloudinary.uploader.upload(
            file_obj,
            folder=folder,
            transformation=[
                {"width": 800, "height": 1000, "crop": "limit"}, # dating cards ke liye standard aspect limit
                {"quality": "auto"}, # automatic compression
                {"fetch_format": "auto"} # auto WebP/JPEG format
            ]
        )
        return response.get("secure_url")
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        raise e