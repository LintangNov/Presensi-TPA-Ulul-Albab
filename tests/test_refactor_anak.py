"""Pengujian otomatis refactoring penyebutan 'murid' dan 'santri' menjadi 'anak'.

Memastikan seluruh fungsionalitas sistem (UI, endpoint alias, database view/trigger,
layanan absensi, dan penanganan excel) bekerja normal dan kompatibel.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import re
import urllib.parse

import pytest
from openpyxl import Workbook, load_workbook

from app.db import connect, initialize
from app.main import app
from app.services.attendance import AttendanceService
from app.services.excel_io import preview_students, student_template
from app.services.students import StudentService


def _run_asgi(target_app, path: str, client_ip: str = "127.0.0.1", method: str = "GET", headers=None, body: bytes = b""):
    status_box = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status_box.append(message["status"])

    hdr = list(headers or [])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path.split("?")[0],
        "raw_path": path.split("?")[0].encode(),
        "query_string": path.split("?")[1].encode() if "?" in path else b"",
        "headers": hdr,
        "client": (client_ip, 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(target_app(scope, receive, send))
    return status_box[0] if status_box else 500


def _get_html(target_app, path: str, client_ip: str = "127.0.0.1") -> str:
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
        "client": (client_ip, 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(target_app(scope, receive, send))
    return bytes(body).decode("utf-8", errors="replace")


def test_no_murid_or_santri_in_ui_pages(tmp_path, monkeypatch):
    """Memastikan kata 'murid' dan 'santri' tidak muncul di teks maupun atribut user-facing."""
    from app.routers import admin as admin_router
    from app.services import scanner_simulator
    from app.services.reports import ReportService

    test_db = tmp_path / "ui_clean.db"
    test_students = StudentService(test_db)
    test_attendance = AttendanceService(test_db)
    test_reports = ReportService(test_db)

    test_students.save_student(None, "Anak Pertama", 1, {}, paket="A")
    test_students.save_student(None, "Anak Kedua", 2, {}, paket="B")

    monkeypatch.setattr(admin_router, "DB_PATH", test_db)
    monkeypatch.setattr(admin_router, "students", test_students)
    monkeypatch.setattr(admin_router, "reports", test_reports)
    monkeypatch.setattr(scanner_simulator, "students", test_students)
    monkeypatch.setattr(scanner_simulator, "attendance", test_attendance)
    monkeypatch.setattr(scanner_simulator, "is_simulation_enabled", lambda: True)

    pages = [
        "/admin",
        "/admin/anak",
        "/admin/hari-ini",
        "/admin/rekap",
        "/admin/import",
        "/admin/fields",
        "/admin/simulator",
        "/scan",
    ]

    for path in pages:
        html = _get_html(app, path)
        # 1. Atribut UI
        attributes = re.findall(r'(?:placeholder|title|aria-label|alt)=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for attr in attributes:
            assert "murid" not in attr.lower(), f"Kata 'murid' ditemukan di atribut: '{attr}' pada {path}"
            assert "santri" not in attr.lower(), f"Kata 'santri' ditemukan di atribut: '{attr}' pada {path}"

        # 2. Teks tampilan pengguna (abaikan script dan style)
        no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text_only = re.sub(r"<[^>]+>", " ", no_scripts)
        words = [w.lower() for w in re.findall(r"\b[a-zA-Z]+\b", text_only)]

        assert "murid" not in words, f"Kata 'murid' ditemukan di teks UI pada {path}: {text_only[:300]}"
        assert "santri" not in words, f"Kata 'santri' ditemukan di teks UI pada {path}: {text_only[:300]}"

    # Pastikan istilah 'anak' aktif ditampilkan
    admin_anak_html = _get_html(app, "/admin/anak")
    assert "Data Anak" in admin_anak_html
    assert "Tambah Anak Baru" in admin_anak_html
    assert "Nama Anak" in admin_anak_html


def test_endpoint_aliases_and_backwards_compatibility(tmp_path, monkeypatch):
    """Memastikan endpoint baru /admin/anak dan endpoint warisan /admin/murid, /admin/santri bekerja."""
    from app.routers import admin as admin_router

    test_db = tmp_path / "endpoints.db"
    test_students = StudentService(test_db)
    monkeypatch.setattr(admin_router, "DB_PATH", test_db)
    monkeypatch.setattr(admin_router, "students", test_students)

    # Akses GET ke ketiga rute harus 200
    assert _run_asgi(app, "/admin/anak") == 200
    assert _run_asgi(app, "/admin/murid") == 200
    assert _run_asgi(app, "/admin/santri") == 200

    # Mutasi POST tambah anak via /admin/anak
    payload = urllib.parse.urlencode({"nama": "Budi Anak", "nomor_urut": "10", "paket": "A"}).encode()
    headers = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-length", str(len(payload)).encode()),
        (b"origin", b"http://127.0.0.1:8000"),
        (b"sec-fetch-site", b"same-origin"),
    ]
    code = _run_asgi(app, "/admin/anak", method="POST", headers=headers, body=payload)
    assert code == 303

    # Mutasi POST tambah anak via /admin/murid (kompatibilitas)
    payload2 = urllib.parse.urlencode({"nama": "Citra Anak", "nomor_urut": "11", "paket": "B"}).encode()
    headers2 = [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-length", str(len(payload2)).encode()),
        (b"origin", b"http://127.0.0.1:8000"),
        (b"sec-fetch-site", b"same-origin"),
    ]
    code2 = _run_asgi(app, "/admin/murid", method="POST", headers=headers2, body=payload2)
    assert code2 == 303

    # Pastikan data tersimpan
    list_anak = test_students.list_students()
    names = [s["nama"] for s in list_anak]
    assert "Budi Anak" in names
    assert "Citra Anak" in names


def test_database_views_and_triggers_anak_compatibility(tmp_path):
    """Memastikan view 'anak' dan 'kartu_anak' mendukung kueri CRUD tanpa mengubah struktur fisik."""
    test_db = tmp_path / "view_test.db"
    initialize(test_db)

    with connect(test_db) as conn:
        # 1. Kueri tabel santri fisik langsung
        conn.execute(
            "INSERT INTO santri (nomor_urut, nama, paket, extra_data, aktif) VALUES (1, 'Dewi', 'A', '{}', 1)"
        )
        sid = conn.execute("SELECT id FROM santri WHERE nama = 'Dewi'").fetchone()[0]

        # 2. Baca lewat view 'anak'
        row_view = conn.execute("SELECT * FROM anak WHERE id = ?", (sid,)).fetchone()
        assert row_view is not None
        assert row_view["nama"] == "Dewi"
        assert row_view["paket"] == "A"

        # 3. Insert lewat view 'anak' (didukung oleh trigger trigger_insert_anak)
        conn.execute(
            "INSERT INTO anak (nomor_urut, nama, paket, extra_data, aktif) VALUES (2, 'Eko', 'B', '{}', 1)"
        )
        row_eko = conn.execute("SELECT * FROM santri WHERE nama = 'Eko'").fetchone()
        assert row_eko is not None
        assert row_eko["nomor_urut"] == 2
        assert row_eko["paket"] == "B"

        # 4. Update lewat view 'anak'
        conn.execute("UPDATE anak SET nama = 'Eko Prasetyo' WHERE id = ?", (row_eko["id"],))
        updated = conn.execute("SELECT nama FROM santri WHERE id = ?", (row_eko["id"],)).fetchone()
        assert updated["nama"] == "Eko Prasetyo"

        # 5. Insert lewat view 'kartu_anak'
        conn.execute(
            "INSERT INTO kartu_anak (santri_id, rfid_uid, slot, label) VALUES (?, 'CARD-EKO', 1, 'Kartu 1')",
            (row_eko["id"],),
        )
        card_row = conn.execute("SELECT * FROM kartu_santri WHERE santri_id = ?", (row_eko["id"],)).fetchone()
        assert card_row is not None
        assert card_row["rfid_uid"] == "CARD-EKO"

        # 6. Delete lewat view 'anak'
        conn.execute("DELETE FROM anak WHERE id = ?", (row_eko["id"],))
        assert conn.execute("SELECT * FROM santri WHERE id = ?", (row_eko["id"],)).fetchone() is None


def test_attendance_service_messages_use_anak_terminology(tmp_path):
    """Memastikan pesan hasil tap absensi menggunakan penyebutan 'anak'."""
    test_db = tmp_path / "att_msg.db"
    attendance = AttendanceService(test_db)
    students = StudentService(test_db)

    sid = attendance.add_student("Fajar", uid="UID-FAJAR", active=True, paket="A")

    # Tap 1: Masuk
    res1 = attendance.tap("UID-FAJAR")
    assert res1["hasil"] == "berhasil"

    # Tap duplikat masuk instan (< 1 menit)
    res_dup = attendance.tap("UID-FAJAR")
    assert res_dup["hasil"] == "duplikat"
    assert "anak" in res_dup["pesan"].lower() or "absensi masuk baru saja" in res_dup["pesan"].lower()

    # Murid nonaktif
    students.set_active(sid, False)
    res_nonaktif = attendance.tap("UID-FAJAR")
    assert res_nonaktif["hasil"] == "tidak_aktif"
    assert "data anak ini sedang tidak aktif" in res_nonaktif["pesan"].lower()

    # UID terpakai
    students.set_active(sid, True)
    sid2 = students.save_student(None, "Gita", 5, {}, paket="B")
    with pytest.raises(ValueError) as exc:
        students.register_card(sid2, "UID-FAJAR")
    assert "kartu sudah dipakai anak lain" in str(exc.value).lower()


def test_excel_template_and_preview_supports_both_data_anak_and_murid(tmp_path):
    """Memastikan sheet template resmi adalah 'Data Anak' dan preview mendukung format lama maupun baru."""
    students = StudentService(tmp_path / "excel_compat.db")
    fields = students.fields(True)

    # 1. Template default menggunakan 'Data Anak'
    content = student_template(fields)
    wb = load_workbook(BytesIO(content), data_only=True)
    assert "Data Anak" in wb.sheetnames
    assert "Panduan Pengisian" in wb.sheetnames

    # 2. Preview dari sheet 'Data Anak'
    wb_anak = Workbook()
    sheet_anak = wb_anak.active
    sheet_anak.title = "Data Anak"
    sheet_anak.append(["Nomor", "Nama", "Paket"])
    sheet_anak.append([1, "Hasan Anak", "A"])
    bio_anak = BytesIO()
    wb_anak.save(bio_anak)

    preview_anak = preview_students(bio_anak.getvalue(), fields)
    assert len(preview_anak["rows"]) == 1
    assert preview_anak["rows"][0]["nama"] == "Hasan Anak"

    # 3. Preview dari file lama dengan sheet 'Data Murid' tetap didukung tanpa error
    wb_murid = Workbook()
    sheet_murid = wb_murid.active
    sheet_murid.title = "Data Murid"
    sheet_murid.append(["Nomor", "Nama", "Paket"])
    sheet_murid.append([2, "Indah Murid Lama", "B"])
    bio_murid = BytesIO()
    wb_murid.save(bio_murid)

    preview_murid = preview_students(bio_murid.getvalue(), fields)
    assert len(preview_murid["rows"]) == 1
    assert preview_murid["rows"][0]["nama"] == "Indah Murid Lama"
