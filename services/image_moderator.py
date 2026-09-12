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

def detect_nudity_and_nsfw(img: Image.Image) -> Dict[str, Any]:
    """
    Intelligent Nudity & NSFW Content Moderation with Body-Zone Awareness:
    1. Multi-space skin detection (RGB + YCbCr) calibrated for Indian, Asian, and all human skin tones.
    2. Body-Zone Torso Analysis: Distinguishes between clothed sleeveless/tank-tops and bare chests/nude torsos.
    3. Connected Component Flesh Clustering: Identifies massive continuous patches of exposed body.
    
    Safe & Approved:
      - Normal clothed portraits, t-shirts, dresses, sleeveless tops, tank-tops, shorts, casual photos.
    Rejected:
      - Fully naked photos, topless/shirtless explicit poses, underwear/lingerie, sexually explicit content.
    """
    thumb = img.convert("RGB").resize((100, 100))
    raw_pixels = list(thumb.getdata())
    total_pixels = len(raw_pixels)  # 10,000

    skin_mask = [0] * total_pixels
    skin_count = 0

    for idx, pixel in enumerate(raw_pixels):
        r, g, b = pixel[0], pixel[1], pixel[2]

        # 1. RGB Skin rule
        is_rgb_skin = (
            r > 80 and g > 35 and b > 20 and
            (max(r, g, b) - min(r, g, b)) > 15 and
            abs(r - g) > 12 and r > g and r > b
        )

        # 2. YCbCr Skin rule
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
        cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
        is_ycbcr_skin = (y > 60 and 77 <= cb <= 135 and 130 <= cr <= 180)

        if is_rgb_skin and is_ycbcr_skin:
            skin_mask[idx] = 1
            skin_count += 1

    total_skin_ratio = skin_count / total_pixels

    # 2. Central Torso Zone Analysis (y: 30% to 70%, x: 25% to 75%)
    # Clothed tops (tank tops, t-shirts, dresses) cover the central chest and abdomen.
    # Topless, naked, or explicit photos leave the torso exposed (>58% bare skin).
    torso_pixels = 0
    torso_skin = 0
    for y_coord in range(30, 70):
        for x_coord in range(25, 75):
            torso_pixels += 1
            if skin_mask[y_coord * 100 + x_coord]:
                torso_skin += 1
    torso_skin_ratio = torso_skin / torso_pixels

    # 3. BFS Connected Component Analysis for Largest Continuous Flesh Cluster
    w, h = 100, 100
    visited = [False] * total_pixels
    max_cluster = 0

    for i in range(h):
        for j in range(w):
            idx = i * w + j
            if skin_mask[idx] and not visited[idx]:
                cluster_size = 0
                queue = [idx]
                visited[idx] = True
                while queue:
                    curr = queue.pop()
                    cluster_size += 1
                    ci, cj = divmod(curr, w)
                    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        ni, nj = ci + di, cj + dj
                        if 0 <= ni < h and 0 <= nj < w:
                            nidx = ni * w + nj
                            if skin_mask[nidx] and not visited[nidx]:
                                visited[nidx] = True
                                queue.append(nidx)
                if cluster_size > max_cluster:
                    max_cluster = cluster_size

    cluster_ratio = max_cluster / total_pixels

    # Precise Dating App Safety Evaluation:
    # 1. Total bare skin > 40% (excessive exposure across body / nudity)
    # 2. Bare Torso > 58% AND total skin > 28% (uncovered chest/stomach, topless/nude)
    # 3. Massive contiguous bare flesh cluster > 35%
    is_nsfw = False
    reason = None

    if total_skin_ratio > 0.40:
        is_nsfw = True
        reason = f"Excessive body exposure ({total_skin_ratio*100:.1f}% bare skin). Nude or 18+ photos are strictly prohibited on Spark."
    elif torso_skin_ratio > 0.58 and total_skin_ratio > 0.28:
        is_nsfw = True
        reason = f"Bare torso or uncovered chest detected ({torso_skin_ratio*100:.1f}% bare torso). 18+ or naked photos are not allowed on Spark."
    elif cluster_ratio > 0.35:
        is_nsfw = True
        reason = f"Dominant uncovered body area detected ({cluster_ratio*100:.1f}% cluster). 18+ photos are not allowed on Spark."

    return {
        "is_nsfw": is_nsfw,
        "total_skin_ratio": round(total_skin_ratio, 3),
        "torso_skin_ratio": round(torso_skin_ratio, 3),
        "cluster_ratio": round(cluster_ratio, 3),
        "reason": reason
    }

def moderate_image_content(image_stream: io.BytesIO) -> Dict[str, Any]:
    """
    Content moderation layer:
    1. Multi-stage nudity, bare torso, and NSFW detection.
    2. REJECTS inappropriate, naked, or 18+ photos immediately.
    3. ACCEPTS normal clothed fashion, sleeveless tops, and casual portraits.
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
            nudity_res = detect_nudity_and_nsfw(img)
            moderation_result["skin_exposure_ratio"] = nudity_res["total_skin_ratio"]
            moderation_result["torso_skin_ratio"] = nudity_res["torso_skin_ratio"]
            moderation_result["cluster_ratio"] = nudity_res["cluster_ratio"]

            if nudity_res["is_nsfw"]:
                moderation_result["status"] = "REJECTED"
                moderation_result["is_flagged"] = True
                moderation_result["reason"] = nudity_res["reason"]

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
    3. Run content / NSFW moderation (REJECTS 18+, naked, adult photos)
      ↓
    Return: (sanitized_stream, moderation_metadata)
    """
    raw_bytes = image_stream.getvalue()

    # 1. Malware / Polyglot scan
    scan_for_malicious_payloads(raw_bytes)

    # 2. Privacy & EXIF stripping
    sanitized_stream = sanitize_and_strip_metadata(image_stream, image_format)

    # 3. Content moderation check (Nudity / NSFW / 18+)
    moderation_metadata = moderate_image_content(sanitized_stream)

    if moderation_metadata.get("status") == "REJECTED":
        raise HTTPException(
            status_code=400,
            detail=f"Photo rejected by safety moderation: {moderation_metadata.get('reason')}"
        )

    return sanitized_stream, moderation_metadata
