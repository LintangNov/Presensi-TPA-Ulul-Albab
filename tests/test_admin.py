import asyncio
from datetime import datetime

import pytest

from app.db import connect
from app.services.attendance import AttendanceService
from app.services.students import StudentService


def test_student_and_custom_field_crud(tmp_path):
    db_path = tmp_path / "admin.db"
    students = StudentService(db_path)
    field_id = students.add_field("Nama Orang Tua", 2)
    assert students.fields()[0]["field_key"] == "nama_orang_tua"

    student_id = students.save_student(
        None, "Alya", 7, {"nama_orang_tua": "Ibu Alya"}
    )
    assert students.get_student(student_id)["extra_data"]["nama_orang_tua"] == "Ibu Alya"
    students.save_student(student_id, "Alya Baru", 8, {"nama_orang_tua": "Ayah Alya"})
    assert students.get_student(student_id)["nama"] == "Alya Baru"
    students.update_field(field_id, "Wali", 1)
    students.set_field_active(field_id, False)
    assert students.fields()[0]["aktif"] == 0


def test_direct_card_registration_normalizes_and_rejects_duplicate(tmp_path):
    students = StudentService(tmp_path / "register.db")
    first = students.save_student(None, "Alya", 1, {})
    second = students.save_student(None, "Bima", 2, {})

    result = students.register_card(first, "  card-01\r\n")

    assert result["uid"] == "CARD-01"
    assert students.get_student(first)["rfid_uid"] == "CARD-01"
    with pytest.raises(ValueError, match="sudah dipakai"):
        students.register_card(second, "CARD-01")


def test_end_to_end_registration_tap_and_today_data(tmp_path):
    db_path = tmp_path / "e2e.db"
    students = StudentService(db_path)
    attendance = AttendanceService(db_path)
    student_id = students.save_student(None, "Bima", 4, {})
    attendance.set_registration(student_id)

    registration = attendance.tap("CARD-E2E", "hp", "register")
    present = attendance.tap("CARD-E2E", "hp", "attendance")

    assert registration["hasil"] == "registrasi"
    assert present["hasil"] == "berhasil"
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT s.nama, a.status FROM santri s JOIN absensi a ON a.santri_id = s.id "
            "WHERE s.id = ?",
            (student_id,),
        ).fetchone()
        assert tuple(row) == ("Bima", "Hadir")


def _run_asgi(app, path, client, method="GET", headers=None, body=b""):
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": (client, 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(app(scope, receive, send))
    return messages[0]["status"]


def test_admin_routes_are_localhost_only():
    from app.main import SERVER_HOST, app

    assert SERVER_HOST == "127.0.0.1"
    assert _run_asgi(app, "/admin", "192.168.1.50") == 403
    assert _run_asgi(app, "/api/admin/status", "192.168.1.50") == 403
    assert _run_asgi(app, "/admin", "127.0.0.1") == 200


def test_settings_route_is_localhost_only():
    from app.main import app

    assert _run_asgi(app, "/admin/fields", "192.168.1.50") == 403
    assert _run_asgi(app, "/admin/fields", "127.0.0.1") == 200


def test_delete_student_and_reset_data(tmp_path):
    from app.db import reset_all_data
    db_path = tmp_path / "test_ops.db"
    students = StudentService(db_path)
    attendance = AttendanceService(db_path)

    sid1 = students.save_student(None, "Satu", 1, {}, paket="A")
    sid2 = students.save_student(None, "Dua", 2, {}, paket="B")
    assert len(students.list_students()) == 2

    # Delete student
    students.delete_student(sid1)
    remaining = students.list_students()
    assert len(remaining) == 1
    assert remaining[0]["id"] == sid2

    # Reset all data
    reset_all_data(db_path)
    assert len(students.list_students()) == 0


def test_csrf_cross_site_rejected():
    from app.main import app

    headers = [
        (b"sec-fetch-site", b"cross-site"),
        (b"origin", b"http://evil-website.com"),
    ]
    status = _run_asgi(app, "/admin/reset-data", "127.0.0.1", method="POST", headers=headers)
    assert status == 403


def test_csrf_evil_origin_and_referer_rejected():
    from app.main import app

    # Evil origin
    headers = [(b"origin", b"https://attacker.org")]
    status = _run_asgi(app, "/admin/backup", "127.0.0.1", method="POST", headers=headers)
    assert status == 403

    # Evil referer
    headers = [(b"referer", b"https://attacker.org/phishing")]
    status = _run_asgi(app, "/admin/backup", "127.0.0.1", method="POST", headers=headers)
    assert status == 403


def test_csrf_local_origin_allowed(monkeypatch):
    from app.main import app
    import app.routers.admin as admin_module

    # Hindari eksekusi backup database fisik saat pengujian routing
    monkeypatch.setattr(admin_module, "backup_database", lambda path: None)

    headers = [
        (b"origin", b"http://127.0.0.1:8000"),
        (b"sec-fetch-site", b"same-origin"),
    ]
    status = _run_asgi(app, "/admin/backup", "127.0.0.1", method="POST", headers=headers)
    # Lolos CSRF: response 303 Redirect ke /admin/fields
    assert status == 303


def test_tap_age_ms_bounds():
    import json
    from app.main import app

    headers = [
        (b"content-type", b"application/json"),
        (b"origin", b"http://127.0.0.1:8000"),
    ]
    # age_ms > 120_000 harus ditolak dengan status 422 Unprocessable Entity
    body_invalid = json.dumps({"uid": "CARD01", "age_ms": 999_999}).encode()
    status = _run_asgi(app, "/api/tap", "127.0.0.1", method="POST", headers=headers, body=body_invalid)
    assert status == 422

    # age_ms < 0 harus ditolak dengan status 422
    body_negative = json.dumps({"uid": "CARD01", "age_ms": -100}).encode()
    status = _run_asgi(app, "/api/tap", "127.0.0.1", method="POST", headers=headers, body=body_negative)
    assert status == 422

    # age_ms valid (dalam batas 120_000 ms) diizinkan
    body_valid = json.dumps({"uid": "CARD01", "age_ms": 5000}).encode()
    status = _run_asgi(app, "/api/tap", "127.0.0.1", method="POST", headers=headers, body=body_valid)
    assert status == 200


def test_import_previews_ttl_and_lru():
    import time
    from app.routers.admin import (
        cleanup_import_previews,
        import_previews,
        IMPORT_PREVIEW_TTL_SECONDS,
        MAX_IMPORT_PREVIEWS,
    )

    import_previews.clear()

    # 1. Uji TTL: token lama harus dibersihkan
    import_previews["expired_token"] = {
        "_created_at": time.time() - IMPORT_PREVIEW_TTL_SECONDS - 5,
        "rows": [],
    }
    import_previews["fresh_token"] = {
        "_created_at": time.time(),
        "rows": [],
    }
    cleanup_import_previews()
    assert "expired_token" not in import_previews
    assert "fresh_token" in import_previews

    # 2. Uji LRU: jika entri melebihi kapasitas MAX_IMPORT_PREVIEWS, entri tertua dibuang
    import_previews.clear()
    for i in range(MAX_IMPORT_PREVIEWS + 5):
        import_previews[f"token_{i}"] = {
            "_created_at": time.time() + i,
            "rows": [],
        }
    assert len(import_previews) == MAX_IMPORT_PREVIEWS + 5
    cleanup_import_previews()
    assert len(import_previews) < MAX_IMPORT_PREVIEWS + 5
    assert len(import_previews) <= MAX_IMPORT_PREVIEWS
    assert "token_0" not in import_previews  # token paling tua terbuang
    import_previews.clear()


def test_scan_page_renders_focus_guard():
    from app.main import app

    messages = []
    body = bytearray()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/scan",
        "raw_path": b"/scan",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 200
    html = body.decode("utf-8")
    assert "tv-focus-warning" in html
    assert "SCANNER TIDAK AKTIF" in html
    assert "btn-activate-scanner" in html


def test_route_alias_admin_murid_and_santri():
    from app.main import app

    assert _run_asgi(app, "/admin/murid", "127.0.0.1") == 200
    assert _run_asgi(app, "/admin/santri", "127.0.0.1") == 200
    assert _run_asgi(app, "/admin/murid", "192.168.1.100") == 403


def test_reports_parameter_student_id_and_legacy_santri_id(tmp_path, monkeypatch):
    from app.main import app
    from app.routers import admin as admin_module
    from app.services.reports import ReportService
    from app.services.students import StudentService

    db_path = tmp_path / "test_reports_param.db"
    students = StudentService(db_path)
    reports = ReportService(db_path)
    monkeypatch.setattr(admin_module, "students", students)
    monkeypatch.setattr(admin_module, "reports", reports)

    sid = students.save_student(None, "Fulan", 1, {})
    reports.save_manual(sid, "2026-11-15", "Hadir", "07:00", "")

    # Menggunakan student_id
    code1, html1 = _run_asgi_full(app, f"/admin/rekap?student_id={sid}")
    assert code1 == 200
    assert "Fulan" in html1

    # Menggunakan legacy santri_id
    code2, html2 = _run_asgi_full(app, f"/admin/rekap?santri_id={sid}")
    assert code2 == 200
    assert "Fulan" in html2


def _run_asgi_full(app, path):
    messages = []
    body = bytearray()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path.split("?")[0],
        "raw_path": path.split("?")[0].encode(),
        "query_string": path.split("?")[1].encode() if "?" in path else b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(app(scope, receive, send))
    status = next((m["status"] for m in messages if m["type"] == "http.response.start"), 500)
    return status, body.decode("utf-8", errors="replace")


