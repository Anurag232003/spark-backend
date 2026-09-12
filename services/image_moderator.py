# backend/services/image_moderator.py
import io
from typing import Dict, Any, Tuple
from PIL import Image
from fastapi import HTTPException

# Dangerous binary markers that indicate polyglot files, embedded scripts, or shell injection
MALICIOUS_SIGNATURES = [
    b"<?php",
    b"<?=",
    b"<script",
    b"</script>",
    b"javascript:",
    b"<svg",
    b"onload=",
    b"onerror=",
    b"cmd.exe",
    b"/bin/sh",
    b"/bin/bash",
    b"eval(",
    b"base64_decode",
]

def scan_for_malicious_payloads(raw_bytes: bytes) -> None:
    """
    Scans raw image bytes for embedded code, PHP tags, XSS payloads, or polyglot signatures.
    Raises HTTPException(400) if any threat signature is detected.
    """
    lowered = raw_bytes.lower()
    for sig in MALICIOUS_SIGNATURES:
        if sig in lowered:
            raise HTTPException(
                status_code=400,
                detail="Security violation: File contains unauthorized embedded code or script signatures."
            )

def sanitize_and_strip_metadata(image_stream: io.BytesIO, image_format: str) -> io.BytesIO:
    """
    Re-encodes image to a clean stream without EXIF metadata.
    Prevents GPS geolocation leaks (critical privacy protection for dating app users)
    and strips any malicious payload hidden in EXIF comment chunks.
    """
    image_stream.seek(0)
    with Image.open(image_stream) as img:
        save_format = "JPEG" if image_format.upper() == "JPEG" else image_format.upper()
        if img.mode in ("RGBA", "LA") and save_format == "JPEG":
            clean_img = img.convert("RGB")
        elif img.mode not in ("RGB", "RGBA"):
            clean_img = img.convert("RGB")
        else:
            clean_img = img.copy()

        output_stream = io.BytesIO()
        clean_img.save(
            output_stream,
            format=save_format,
            quality=90 if save_format == "JPEG" else None,
            optimize=True
        )
        output_stream.seek(0)
        return output_stream

def moderate_image_content(image_stream: io.BytesIO) -> Dict[str, Any]:
    """
    Content moderation layer:
    1. Heuristic perceptual color and skin-exposure analysis.
    2. Flags anomalies or extreme ratios.
    3. Returns moderation metadata for audit and safety logging.
    """
    image_stream.seek(0)
    moderation_result = {
        "status": "APPROVED",
        "nsfw_score": 0.0,
        "is_flagged": False,
        "reason": None
    }

    try:
        with Image.open(image_stream) as img:
            thumb = img.convert("RGB").resize((100, 100))
            pixels = list(thumb.getdata())
            total_pixels = len(pixels)

            # Heuristic skin-tone approximation (YCbCr / normalized RGB range)
            skin_pixels = 0
            for r, g, b in pixels:
                if r > 95 and g > 40 and b > 20 and max(r, g, b) - min(r, g, b) > 15:
                    if abs(r - g) > 15 and r > g and r > b:
                        skin_pixels += 1

            skin_ratio = skin_pixels / total_pixels
            moderation_result["skin_exposure_ratio"] = round(skin_ratio, 3)

            # Extreme skin exposure (> 85%) on a single image triggers automated review flag
            if skin_ratio > 0.85:
                moderation_result["status"] = "FLAGGED"
                moderation_result["is_flagged"] = True
                moderation_result["reason"] = "High skin exposure detected. Flagged for review."

    except Exception as e:
        moderation_result["analysis_error"] = str(e)

    image_stream.seek(0)
    return moderation_result

def process_and_moderate_image(
    image_stream: io.BytesIO,
    image_format: str
) -> Tuple[io.BytesIO, Dict[str, Any]]:
    """
    Complete Content Safety Pipeline:
    Upload
      ↓
    1. Scan for malware / embedded script tags
      ↓
    2. Strip EXIF / GPS metadata to prevent user tracking
      ↓
    3. Run content / NSFW moderation
      ↓
    Return: (sanitized_stream, moderation_metadata)
    """
    raw_bytes = image_stream.getvalue()
    
    # 1. Malware / Polyglot scan
    scan_for_malicious_payloads(raw_bytes)

    # 2. Privacy & EXIF stripping
    sanitized_stream = sanitize_and_strip_metadata(image_stream, image_format)

    # 3. Content moderation check
    moderation_metadata = moderate_image_content(sanitized_stream)

    if moderation_metadata.get("status") == "REJECTED":
        raise HTTPException(
            status_code=400,
            detail=f"Image rejected by content safety moderation: {moderation_metadata.get('reason')}"
        )

    return sanitized_stream, moderation_metadata
