"""Security: uploads are only real documents, stored files can't run script, cross-site requests are refused,
log-in guessing is limited, security headers are set, and the visitor's real address is used behind the proxy."""

import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_only_real_pdfs_jpgs_and_pngs_count_as_documents():
    from onboarding import security
    assert security.sniff(b"%PDF-1.7\n...") == "application/pdf"
    assert security.sniff(b"\x89PNG\r\n\x1a\n....") == "image/png" and security.sniff(b"\xff\xd8\xff\xe0..") == "image/jpeg"
    for bad in (b"<html><script>alert(1)</script>", b"MZ\x90\x00", b"<svg onload=alert(1)>", b""):
        assert security.sniff(bad) is None
        with pytest.raises(HTTPException) as e:
            security.require_document(bad, "The GST certificate")
        assert e.value.status_code == 415 and "PDF, JPG or PNG" in e.value.detail


def test_a_stored_file_can_never_run_script_on_the_site():
    from onboarding import security
    page = security.file_response(b"<html><script>steal()</script></html>", "application/pdf")   # whatever it was stored as
    assert page.media_type == "application/octet-stream" and page.headers["content-disposition"] == "attachment"
    assert "sandbox" in page.headers["content-security-policy"] and page.headers["x-content-type-options"] == "nosniff"
    pdf = security.file_response(b"%PDF-1.4 real", "text/html")
    assert pdf.media_type == "application/pdf" and pdf.headers["content-disposition"] == "inline" and "sandbox" in pdf.headers["content-security-policy"]


def test_cross_site_requests_are_refused_and_headers_are_set():
    from onboarding.main import app
    c = TestClient(app, raise_server_exceptions=False)
    evil = c.post("/company/login", data={"email": "a@b.c", "password": "x"}, headers={"Origin": "https://evil.example.com"})
    assert evil.status_code == 403 and "another site" in evil.json()["error"]
    api = c.post("/api/v1/session/logout", headers={"Origin": "https://evil.example.com"})
    assert api.status_code == 403
    same = c.post("/api/v1/session/logout", headers={"Origin": "http://testserver"})
    assert same.status_code == 200
    page = c.get("/", headers={"X-Forwarded-Proto": "https"})
    for h in ("x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy", "strict-transport-security"):
        assert h in page.headers, h


def test_log_in_guessing_is_limited(monkeypatch):
    import onboarding.config as cfg
    from onboarding import security
    monkeypatch.setenv("RATE_LIMITS", "true")
    cfg.get_settings.cache_clear()
    for lim in security.ALL_LIMITS:
        lim.reset()
    try:
        from fastapi import Request
        req = Request({"type": "http", "headers": [(b"x-forwarded-for", b"203.0.113.9")], "client": ("10.0.0.1", 1)})
        assert security.client_ip(req) == "203.0.113.9"                       # the visitor Render's proxy saw, not the proxy
        for _ in range(security.LOGIN_PER_ACCOUNT.limit):
            security.check_login(req, "kavita.rao@mamoni.in")
        with pytest.raises(HTTPException) as e:
            security.check_login(req, "KAVITA.RAO@mamoni.in ")
        assert e.value.status_code == 429 and "Too many log-in attempts" in e.value.detail
        security.check_login(req, "arjun.mehta@mamoni.in")                     # another account still works
        # a made-up X-Forwarded-For entry is to the LEFT of what the proxy appended: it no longer resets the limit
        spoofed = Request({"type": "http", "headers": [(b"x-forwarded-for", b"198.51.100.77, 203.0.113.9")], "client": ("10.0.0.1", 1)})
        assert security.client_ip(spoofed) == "203.0.113.9"
        with pytest.raises(HTTPException) as e:
            security.check_login(spoofed, "kavita.rao@mamoni.in")
        assert e.value.status_code == 429
    finally:
        monkeypatch.setenv("RATE_LIMITS", os.environ.get("RATE_LIMITS", "false"))
        monkeypatch.setenv("RATE_LIMITS", "false")
        cfg.get_settings.cache_clear()
        for lim in security.ALL_LIMITS:
            lim.reset()
