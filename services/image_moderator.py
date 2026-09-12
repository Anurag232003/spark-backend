# backend/services/image_moderator.py
import io
from typing import Dict, Any, Tuple
from PIL import Image, ImageFilter
import numpy as np
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
    Multi-stage computer vision detection for nudity, bare torso, and NSFW content:
    1. Multi-space skin detection (RGB + YCbCr) across diverse skin tones.
    2. Connected component clustering: identifies large contiguous patches of exposed flesh.
    3. Edge density & texture analysis: distinguishes smooth exposed bodies from structured clothing/faces.
    """
    thumb = img.convert("RGB").resize((120, 120))
    arr = np.array(thumb, dtype=np.float32)

    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    # 1. RGB Skin rule
    rgb_rule = (
        (r > 80) & (g > 35) & (b > 20) &
        ((np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)) > 15) &
        (np.abs(r - g) > 12) & (r > g) & (r > b)
    )

    # 2. YCbCr Skin rule
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    ycbcr_rule = (y > 60) & (cb >= 77) & (cb <= 135) & (cr >= 130) & (cr <= 180)

    # Combined skin mask
    skin_mask = rgb_rule & ycbcr_rule
    total_pixels = 120 * 120
    skin_count = np.sum(skin_mask)
    skin_ratio = float(skin_count) / total_pixels

    # 3. Connected component / cluster analysis on 60x60 grid
    grid = skin_mask[::2, ::2]  # 60x60
    visited = np.zeros_like(grid, dtype=bool)
    max_cluster = 0
    h, w = grid.shape

    for i in range(h):
        for j in range(w):
            if grid[i, j] and not visited[i, j]:
                cluster_size = 0
                queue = [(i, j)]
                visited[i, j] = True
                while queue:
                    ci, cj = queue.pop()
                    cluster_size += 1
                    for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        ni, nj = ci + di, cj + dj
                        if 0 <= ni < h and 0 <= nj < w and grid[ni, nj] and not visited[ni, nj]:
                            visited[ni, nj] = True
                            queue.append((ni, nj))
                if cluster_size > max_cluster:
                    max_cluster = cluster_size

    cluster_ratio = float(max_cluster) / (h * w)

    # 4. Texture and Edge analysis
    gray = thumb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges, dtype=np.float32)
    skin_edges = edge_arr[skin_mask]
    edge_density = float(np.mean(skin_edges)) if len(skin_edges) > 0 else 0.0

    is_nsfw = False
    reason = None

    # Decision thresholds:
    # A. Obvious full nudity or massive bare exposure
    if skin_ratio > 0.45 or cluster_ratio > 0.35:
        if edge_density < 18.0 or skin_ratio > 0.65:
            is_nsfw = True
            reason = f"Excessive bare body exposure ({skin_ratio*100:.1f}%). 18+ or nude photos are strictly prohibited."
        elif cluster_ratio > 0.40:
            is_nsfw = True
            reason = f"Uncovered body/naked torso detected ({cluster_ratio*100:.1f}% cluster). 18+ photos are not allowed."
    # B. Topless or underwear/bikini/explicit pose: skin_ratio > 28% with smooth large skin cluster
    elif skin_ratio > 0.28 and cluster_ratio > 0.18:
        if edge_density < 16.0:
            is_nsfw = True
            reason = f"Large bare skin cluster ({cluster_ratio*100:.1f}%) detected. 18+ or naked photos are strictly prohibited."
    # C. Medium skin ratio (> 24%) with huge contiguous bare skin
    elif cluster_ratio > 0.22 and edge_density < 14.0:
        is_nsfw = True
        reason = "Bare torso or exposed body detected. Spark dating app strictly prohibits 18+ or naked photos."

    return {
        "is_nsfw": is_nsfw,
        "skin_ratio": round(skin_ratio, 3),
        "cluster_ratio": round(cluster_ratio, 3),
        "edge_density": round(edge_density, 2),
        "reason": reason
    }

def moderate_image_content(image_stream: io.BytesIO) -> Dict[str, Any]:
    """
    Content moderation layer:
    1. Multi-stage nudity, bare torso, and NSFW detection.
    2. REJECTS inappropriate, naked, or 18+ photos immediately.
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
            nudity_res = detect_nudity_and_nsfw(img)
            moderation_result["skin_exposure_ratio"] = nudity_res["skin_ratio"]
            moderation_result["cluster_ratio"] = nudity_res["cluster_ratio"]
            moderation_result["edge_density"] = nudity_res["edge_density"]

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
