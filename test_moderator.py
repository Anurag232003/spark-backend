import io
from PIL import Image
from fastapi import HTTPException
from services.image_moderator import (
    scan_for_malicious_payloads,
    sanitize_and_strip_metadata,
    moderate_image_content,
    process_and_moderate_image,
)

def test_moderator():
    print("--- Running Image Moderation & Safety Tests ---")

    # 1. Clean image
    buf = io.BytesIO()
    img = Image.new("RGB", (300, 300), color="blue")
    img.save(buf, format="JPEG")
    sanitized, meta = process_and_moderate_image(buf, "JPEG")
    assert meta["status"] == "APPROVED"
    print("PASS: Clean image approved")

    # 2. Malware / PHP tag injection
    malicious_buf = io.BytesIO(buf.getvalue() + b"<?php phpinfo(); ?>")
    try:
        process_and_moderate_image(malicious_buf, "JPEG")
        raise AssertionError("FAIL: Did not block PHP tag injection!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Blocked PHP injection ({e.detail})")

    # 3. Malware / JavaScript injection
    js_buf = io.BytesIO(buf.getvalue() + b"<script>alert(1)</script>")
    try:
        process_and_moderate_image(js_buf, "JPEG")
        raise AssertionError("FAIL: Did not block JS injection!")
    except HTTPException as e:
        assert e.status_code == 400
        print(f"PASS: Blocked JS tag injection ({e.detail})")

    # 4. EXIF GPS stripping test
    im = Image.new("RGB", (200, 200), color="pink")
    exif = im.getexif()
    exif[0x010e] = "Geotagged Bedroom Photo GPS: 28.6139, 77.2090"
    exif_buf = io.BytesIO()
    im.save(exif_buf, format="JPEG", exif=exif)

    # Verify input has EXIF
    with Image.open(io.BytesIO(exif_buf.getvalue())) as check_in:
        assert len(check_in.getexif()) > 0

    # Process through pipeline
    sanitized_exif, meta = process_and_moderate_image(exif_buf, "JPEG")
    with Image.open(sanitized_exif) as check_out:
        assert len(check_out.getexif()) == 0
    print("PASS: Successfully stripped EXIF/GPS metadata to protect user privacy")

    # 5. High skin exposure flagging test
    skin_img = Image.new("RGB", (200, 200), color=(220, 160, 120))  # Caucasian/Asian skin tone
    skin_buf = io.BytesIO()
    skin_img.save(skin_buf, format="JPEG")
    _, skin_meta = process_and_moderate_image(skin_buf, "JPEG")
    assert skin_meta["status"] == "FLAGGED"
    assert skin_meta["is_flagged"] is True
    print(f"PASS: Flagged high skin exposure ({skin_meta['reason']})")

    print("--- ALL MODERATION TESTS PASSED ---")

if __name__ == "__main__":
    test_moderator()
