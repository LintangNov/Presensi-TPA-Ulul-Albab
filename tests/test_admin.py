import asyncio
from datetime import datetime

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


def _run_asgi(app, path, client):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (client, 1234),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(app(scope, receive, send))
    return messages[0]["status"]


def test_admin_routes_are_localhost_only():
    from app.main import app

    assert _run_asgi(app, "/admin", "192.168.1.50") == 403
    assert _run_asgi(app, "/api/admin/status", "192.168.1.50") == 403
    assert _run_asgi(app, "/admin", "127.0.0.1") == 200
