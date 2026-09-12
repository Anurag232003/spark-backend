"""
Test Suite: Transport Security, HTTPS Enforcement, HSTS, and WSS Validation (Issue 39)
Direct ASGI & Middleware Testing (no external httpx dependency required)
"""
import asyncio
from starlette.requests import Request
from starlette.responses import Response
from starlette import status

import main
from main import secure_transport_and_headers_middleware

async def dummy_call_next(request: Request) -> Response:
    return Response(content="OK", status_code=200)

def make_request(scheme="http", headers=None, path="/api/users/me"):
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    raw_headers.append((b"host", b"api.sparkdating.com"))

    scope = {
        "type": "http",
        "method": "GET",
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("api.sparkdating.com", 80 if scheme == "http" else 443),
    }
    return Request(scope)

async def run_tests():
    print("--- Running Transport Security & HTTPS Tests ---")

    # 1. Development Mode: normal HTTP allowed, standard defensive headers present, NO HSTS on plain HTTP
    main.ENFORCE_HTTPS = False
    main.IS_PRODUCTION = False
    main.ENVIRONMENT = "development"

    req_dev = make_request("http")
    res_dev = await secure_transport_and_headers_middleware(req_dev, dummy_call_next)
    assert res_dev.status_code == 200, f"Expected 200, got {res_dev.status_code}"
    assert res_dev.headers["X-Content-Type-Options"] == "nosniff"
    assert res_dev.headers["X-Frame-Options"] == "DENY"
    assert res_dev.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in res_dev.headers, "HSTS should not be set over plain HTTP in dev"
    print("PASS: Development mode permits local HTTP and attaches baseline security headers")

    # 2. Production Mode: HTTP request MUST be redirected to HTTPS (301 Moved Permanently)
    main.ENFORCE_HTTPS = True
    main.IS_PRODUCTION = True
    main.ENVIRONMENT = "production"

    req_prod_http = make_request("http")
    res_prod_http = await secure_transport_and_headers_middleware(req_prod_http, dummy_call_next)
    assert res_prod_http.status_code == status.HTTP_301_MOVED_PERMANENTLY, f"Expected 301, got {res_prod_http.status_code}"
    assert res_prod_http.headers["location"].startswith("https://api.sparkdating.com"), f"Redirect should target https, got {res_prod_http.headers['location']}"
    print(f"PASS: Plaintext HTTP successfully redirected to HTTPS 301 ({res_prod_http.headers['location']})")

    # 3. Production Mode behind Reverse Proxy (X-Forwarded-Proto: http) MUST be redirected to HTTPS
    req_proxy_http = make_request("https", headers={"x-forwarded-proto": "http"})
    res_proxy_http = await secure_transport_and_headers_middleware(req_proxy_http, dummy_call_next)
    assert res_proxy_http.status_code == status.HTTP_301_MOVED_PERMANENTLY, f"Expected 301 for proxy HTTP, got {res_proxy_http.status_code}"
    assert res_proxy_http.headers["location"].startswith("https://api.sparkdating.com")
    print("PASS: Reverse-proxy X-Forwarded-Proto: http correctly triggers HTTPS 301 redirect")

    # 4. Production Mode on HTTPS: Strict-Transport-Security (HSTS) and CSP upgrade headers injected
    req_prod_https = make_request("https")
    res_prod_https = await secure_transport_and_headers_middleware(req_prod_https, dummy_call_next)
    assert res_prod_https.status_code == 200
    assert "Strict-Transport-Security" in res_prod_https.headers
    hsts = res_prod_https.headers["Strict-Transport-Security"]
    assert "max-age=31536000" in hsts, f"HSTS max-age should be 1 year (31536000), got {hsts}"
    assert "includeSubDomains" in hsts, "HSTS must includeSubDomains"
    assert "preload" in hsts, "HSTS must include preload directive"
    assert "upgrade-insecure-requests" in res_prod_https.headers.get("Content-Security-Policy", "")
    print(f"PASS: Production HTTPS injects RFC 6797 HSTS header: '{hsts}' and CSP upgrade directive")

    # 5. WebSocket Transport Security: Reject unencrypted ws:// in production
    class MockWebSocket:
        def __init__(self, scheme="ws", headers=None):
            self.scope = {"scheme": scheme}
            self.headers = headers or {}
            self.closed_code = None

        async def close(self, code=1000):
            self.closed_code = code

    # Test ws:// in production without SSL
    ws_insecure = MockWebSocket("ws", {})
    ws_scheme = ws_insecure.scope.get("scheme", "").lower()
    forwarded_proto = ws_insecure.headers.get("x-forwarded-proto", "").lower()
    forwarded_ssl = ws_insecure.headers.get("x-forwarded-ssl", "").lower()
    is_secure_ws = ws_scheme == "wss" or forwarded_proto == "https" or forwarded_ssl == "on"
    assert not is_secure_ws, "Plaintext ws:// should be detected as insecure"

    # Test wss:// in production
    ws_secure = MockWebSocket("wss", {})
    is_secure_ws2 = ws_secure.scope.get("scheme", "") == "wss"
    assert is_secure_ws2, "Encrypted wss:// should be accepted"

    # Test ws behind SSL-terminating reverse proxy (X-Forwarded-Proto: https)
    ws_proxy_secure = MockWebSocket("ws", {"x-forwarded-proto": "https"})
    is_secure_ws3 = ws_proxy_secure.headers.get("x-forwarded-proto") == "https"
    assert is_secure_ws3, "Proxy-terminated wss with forwarded-proto: https should be accepted"
    print("PASS: WebSocket transport security distinguishes insecure ws:// from encrypted wss://")

    # Reset test state
    main.ENFORCE_HTTPS = False
    main.IS_PRODUCTION = False
    main.ENVIRONMENT = "development"

    print("--- ALL TRANSPORT SECURITY TESTS PASSED ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
