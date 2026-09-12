import asyncio
import io
from PIL import Image
from fastapi import UploadFile, HTTPException
from services.image_validator import (
    validate_and_process_uploaded_image,
    MAX_FILE_SIZE,
    MIN_FILE_SIZE,
    MIN_WIDTH,
    MIN_HEIGHT,
    MAX_WIDTH,
    MAX_HEIGHT,
)

async def test_all():
    print("--- Running Image Validation Tests ---")
    
    # 1. Valid JPEG
    buf = io.BytesIO()
    img = Image.new("RGB", (400, 500), color="green")
    img.save(buf, format="JPEG")
    raw_jpeg = buf.getvalue()
    f = UploadFile(file=io.BytesIO(raw_jpeg), filename="avatar.jpg")
    stream, fmt, ext = await validate_and_process_uploaded_image(f)
    assert fmt == "JPEG" and ext == ".jpg"
    print("PASS: Valid JPEG processed and verified")

    # 2. Valid PNG
    buf = io.BytesIO()
    img = Image.new("RGBA", (300, 300), color="blue")
    img.save(buf, format="PNG")
    raw_png = buf.getvalue()
    f = UploadFile(file=io.BytesIO(raw_png), filename="photo.png")
    stream, fmt, ext = await validate_and_process_uploaded_image(f)
    assert fmt == "PNG" and ext == ".png"
    print("PASS: Valid PNG processed and verified")

    # 3. Valid WebP
    buf = io.BytesIO()
    img = Image.new("RGB", (350, 450), color="purple")
    img.save(buf, format="WEBP")
    raw_webp = buf.getvalue()
    f = UploadFile(file=io.BytesIO(raw_webp), filename="profile.webp")
    stream, fmt, ext = await validate_and_process_uploaded_image(f)
    assert fmt == "WEBP" and ext == ".webp"
    print("PASS: Valid WebP processed and verified")

    # 4. Spoofed MIME / Text script disguised as image (e.g. PHP/Bash with .jpg)
    fake_data = b"<?php echo 'malicious payload'; ?>" * 30
    f = UploadFile(file=io.BytesIO(fake_data), filename="exploit.jpg")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Spoofed script accepted!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Rejected spoofed script via file signature check (HTTP {e.status_code})")

    # 5. Dangerous / Disallowed Extension (.exe, .php, .py, .svg)
    f = UploadFile(file=io.BytesIO(raw_jpeg), filename="photo.exe")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Disallowed extension accepted!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Rejected dangerous extension (HTTP {e.status_code}: {e.detail})")

    # 6. Undersized / Truncated File (< 64 bytes)
    tiny_data = b"\xff\xd8\xff" + (b"\x00" * 20)
    f = UploadFile(file=io.BytesIO(tiny_data), filename="corrupt.jpg")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Tiny file accepted!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Rejected undersized file (HTTP {e.status_code}: {e.detail})")

    # 7. Dimensions Too Low (< 150x150)
    buf = io.BytesIO()
    img = Image.new("RGB", (50, 50), color="black")
    img.save(buf, format="JPEG")
    f = UploadFile(file=io.BytesIO(buf.getvalue()), filename="tracking_pixel.jpg")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Undersized image accepted!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Rejected undersized dimensions (HTTP {e.status_code}: {e.detail})")

    # 8. Dimensions Too Large (> 6000x6000)
    buf = io.BytesIO()
    img = Image.new("RGB", (6500, 200), color="white")
    img.save(buf, format="JPEG")
    f = UploadFile(file=io.BytesIO(buf.getvalue()), filename="gigantic.jpg")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Oversized image accepted!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Rejected oversized dimensions (HTTP {e.status_code}: {e.detail})")

    # 9. Oversized File Size (> 5MB)
    huge_bytes = b"\xff\xd8\xff" + (b"\x00" * (MAX_FILE_SIZE + 1024))
    f = UploadFile(file=io.BytesIO(huge_bytes), filename="huge.jpg")
    try:
        await validate_and_process_uploaded_image(f)
        raise AssertionError("FAIL: Oversized file accepted!")
    except HTTPException as e:
        assert e.status_code == 413
        assert "5MB" in e.detail or "5" in e.detail
        print(f"PASS: Rejected oversized file exceeding 5MB (HTTP {e.status_code}: {e.detail})")

    # 10. Pre-flight Content-Length header check (> 5MB)
    class FakeRequest:
        headers = {"content-length": str(MAX_FILE_SIZE + 5000)}

    f_pre = UploadFile(file=io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 100), filename="preflight.jpg")
    try:
        await validate_and_process_uploaded_image(f_pre, request=FakeRequest())
        raise AssertionError("FAIL: Preflight Content-Length check did not reject!")
    except HTTPException as e:
        assert e.status_code == 413
        print(f"PASS: Preflight Content-Length check rejected >5MB upload (HTTP {e.status_code})")

    print("--- ALL 10 TESTS PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    asyncio.run(test_all())
