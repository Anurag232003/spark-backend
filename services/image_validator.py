import io
import os
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, Optional
import requests
from PIL import Image
from fastapi import HTTPException, UploadFile, Request

# --- Security Boundaries & Configurations ---
MAX_FILE_SIZE = 5 * 1024 * 1024   # 5 MB maximum upload size
MIN_FILE_SIZE = 64                 # Minimum 64 bytes to reject empty or truncated files
MAX_IMAGE_PIXELS = 25_000_000     # 25 Megapixels (Decompression Bomb / Pixel Flood protection)
MIN_WIDTH = 150                    # Minimum width in pixels for dating profile photos
MIN_HEIGHT = 150                   # Minimum height in pixels
MAX_WIDTH = 6000                   # Maximum width in pixels
MAX_HEIGHT = 6000                  # Maximum height in pixels

# Enforce PIL decompression bomb limit
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

def validate_magic_bytes(header: bytes) -> str:
    """
    Validates actual binary file signature against authentic image signatures.
    Prevents MIME-type spoofing by malicious clients.
    """
    if len(header) < 12:
        raise HTTPException(
            status_code=400,
            detail="File too small or corrupted to determine file type."
        )

    # JPEG: starts with FF D8 FF
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"

    # PNG: starts with 89 50 4E 47 0D 0A 1A 0A
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"

    # WEBP: starts with RIFF, bytes 8..12 are WEBP
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "WEBP"

    raise HTTPException(
        status_code=400,
        detail="Invalid file signature. Only authentic JPEG, PNG, and WebP images are permitted."
    )

async def validate_and_process_uploaded_image(file: UploadFile, request: Optional[Request] = None) -> Tuple[io.BytesIO, str, str]:
    """
    Robust multi-layered security validation for uploaded images:
    1. Pre-flight Content-Length verification (drops oversized requests upfront)
    2. File extension validation (reject dangerous/non-image extensions)
    3. File size enforcement (streaming chunked read strictly capped at 5 MB)
    4. Binary magic byte signature inspection (never trusts client Content-Type)
    5. Decompression bomb protection (PIL MAX_IMAGE_PIXELS boundary)
    6. Structural integrity check (img.verify())
    7. Dimension checks (resolution boundaries)

    Returns:
        (BytesIO stream ready for upload, detected_format, canonical_extension)
    """
    # 0. Pre-flight Content-Length check
    if request is not None:
        content_len = request.headers.get("content-length")
        if content_len and content_len.isdigit() and int(content_len) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB."
            )
    # 1. File Extension Validation
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 2. File Size Enforcement (streaming chunked read)
    content_bytes = bytearray()
    chunk_size = 64 * 1024  # 64 KB per chunk

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content_bytes.extend(chunk)
        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB."
            )

    if len(content_bytes) < MIN_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty or too small to be a valid image."
        )

    raw_bytes = bytes(content_bytes)

    # 3. Magic Byte Signature Verification (Do not trust client MIME type)
    magic_format = validate_magic_bytes(raw_bytes[:16])

    # 4 & 5. Structural integrity & Decompression Limit Verification
    stream = io.BytesIO(raw_bytes)
    try:
        with Image.open(stream) as img:
            detected_format = (img.format or "").upper()
            if detected_format not in ALLOWED_FORMATS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported image container format: '{detected_format}'. Allowed: JPEG, PNG, WEBP."
                )

            # Reconcile container format with magic bytes
            if detected_format != magic_format:
                raise HTTPException(
                    status_code=400,
                    detail="Image header signature does not match internal image container format."
                )

            # 6. Dimensions and Pixel Count Validation
            width, height = img.size
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image resolution too low ({width}x{height}px). Minimum required is {MIN_WIDTH}x{MIN_HEIGHT}px."
                )
            if width > MAX_WIDTH or height > MAX_HEIGHT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image resolution too high ({width}x{height}px). Maximum allowed is {MAX_WIDTH}x{MAX_HEIGHT}px."
                )

            total_pixels = width * height
            if total_pixels > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=400,
                    detail="Image exceeds maximum allowable pixel count (decompression bomb protection)."
                )

            # Structural integrity verification
            img.verify()

    except Image.DecompressionBombError:
        raise HTTPException(
            status_code=400,
            detail="Image triggered decompression bomb protection. Image is too large to safely process."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Corrupted or invalid image data: {str(e)}"
        )

    # Rewind stream for downstream consumption
    stream.seek(0)
    canonical_ext = ".jpg" if magic_format == "JPEG" else f".{magic_format.lower()}"
    return stream, magic_format, canonical_ext

def is_safe_cdn_url(url: str, expected_cloud_name: Optional[str] = None) -> bool:
    """
    Validates that a URL belongs strictly to the authorized Cloudinary CDN
    and does not point to internal networks, loopback, or metadata services (SSRF protection).
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        # Scheme must strictly be https
        if parsed.scheme != "https":
            return False
        # Host must strictly be res.cloudinary.com
        if parsed.hostname != "res.cloudinary.com":
            return False
        # Port must be default HTTPS (443 or None)
        if parsed.port not in (None, 443):
            return False
        # If cloud_name configured, path must target our designated cloud namespace
        if expected_cloud_name and not parsed.path.startswith(f"/{expected_cloud_name}/"):
            return False

        # Resolve IP to verify it is not private, loopback, link-local, or reserved (Anti-DNS Rebinding / SSRF)
        ip_str = socket.gethostbyname(parsed.hostname)
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False

        return True
    except Exception:
        return False

def download_safe_profile_image(url: str, dest_path: str, upload_dir: str = "./temp_uploads") -> None:
    """
    Securely downloads an authorized profile photo from the approved CDN.
    Guarantees:
    1. Zero SSRF: Whitelisted CDN domain only, no local IP resolution.
    2. Zero LFI / Path Traversal: Path is strictly confined to upload_dir.
    3. Zero File Bomb: Streaming read capped at MAX_FILE_SIZE (5 MB).
    4. Zero Open Redirect: allow_redirects=False.
    """
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    if not is_safe_cdn_url(url, cloud_name):
        raise HTTPException(
            status_code=400,
            detail="Security violation: Profile photo must be a valid HTTPS URL from the official Cloudinary CDN."
        )

    # Path traversal prevention: dest_path must remain strictly inside upload_dir
    abs_upload_dir = os.path.abspath(upload_dir)
    abs_dest = os.path.abspath(dest_path)
    if not abs_dest.startswith(abs_upload_dir + os.sep) and abs_dest != abs_upload_dir:
        raise HTTPException(
            status_code=400,
            detail="Security violation: Invalid destination path."
        )

    # Secure HTTP streaming download
    try:
        response = requests.get(
            url,
            stream=True,
            timeout=10,
            allow_redirects=False,
            headers={"User-Agent": "Spark-Photo-Verification/1.0"}
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to retrieve profile photo from CDN (HTTP {response.status_code})."
            )

        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="Profile photo exceeds maximum allowable file size (5MB)."
            )

        total_downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    total_downloaded += len(chunk)
                    if total_downloaded > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=400,
                            detail="Profile photo download exceeded maximum allowable file size."
                        )
                    f.write(chunk)

    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to securely fetch profile photo: {str(e)}"
        )
