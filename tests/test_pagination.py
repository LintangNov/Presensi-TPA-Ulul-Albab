"""Test pagination daftar murid dan halaman Simulator RFID."""

import asyncio

from app.services.students import StudentService


def test_list_students_paginated_splits_rows_and_reports_total(tmp_path):
    students = StudentService(tmp_path / "paginasi.db")
    for index in range(1, 26):
        students.save_student(None, f"Murid {index:02d}", index, {})

    page1, total = students.list_students_paginated("", page=1, per_page=15)
    page2, total2 = students.list_students_paginated("", page=2, per_page=15)

    assert total == 25
    assert total2 == 25
    assert len(page1) == 15
    assert len(page2) == 10
    # Tidak ada baris yang terduplikasi antar halaman
    ids1 = {row["id"] for row in page1}
    ids2 = {row["id"] for row in page2}
    assert ids1.isdisjoint(ids2)
    # Urutan tetap mengikuti nomor urut
    assert [row["nomor_urut"] for row in page1] == list(range(1, 16))
    assert [row["nomor_urut"] for row in page2] == list(range(16, 26))


def test_list_students_paginated_respects_search_and_page_bounds(tmp_path):
    students = StudentService(tmp_path / "batas.db")
    for index in range(1, 21):
        students.save_student(None, f"Anak {index:02d}", index, {})
    students.save_student(None, "Budi Santoso", 99, {})

    rows, total = students.list_students_paginated("Budi", page=1, per_page=15)
    assert total == 1
    assert [row["nama"] for row in rows] == ["Budi Santoso"]

    # Halaman di luar rentang tidak error dan tetap mengembalikan total
    rows, total = students.list_students_paginated("", page=99, per_page=15)
    assert total == 21
    assert rows == []


def test_list_students_paginated_matches_full_list_order(tmp_path):
    students = StudentService(tmp_path / "urut.db")
    for index in range(1, 8):
        students.save_student(None, f"Murid {index}", index, {})
    students.set_active(3, False)

    paginated, _ = students.list_students_paginated("", page=1, per_page=100)
    full = students.list_students()

    assert [row["id"] for row in paginated] == [row["id"] for row in full]


def test_simulator_page_renders_pagination_controls(tmp_path, monkeypatch):
    """Halaman simulator harus merender link pagination dan 15 baris per halaman."""
    from app.main import app
    from app.services import scanner_simulator
    from app.services.attendance import AttendanceService
    from app.services.students import StudentService

    test_db = tmp_path / "sim_render.db"
    test_students = StudentService(test_db)
    test_attendance = AttendanceService(test_db)

    monkeypatch.setattr(scanner_simulator, "students", test_students)
    monkeypatch.setattr(scanner_simulator, "attendance", test_attendance)
    monkeypatch.setattr(scanner_simulator, "is_simulation_enabled", lambda: True)

    for index in range(1, 21):
        test_students.save_student(None, f"Murid Uji {index:02d}", index, {})

    body = _get_html(app, "/admin/simulator")
    assert 'class="pagination"' in body
    assert "pagination-btn" in body
    assert "Menampilkan 1–15 dari 20 murid" in body
    # Tombol simulasi tap hanya untuk murid yang sudah punya kartu
    assert "data-sim-tap-uid" in body


def test_simulator_page_clamps_out_of_range_page(tmp_path, monkeypatch):
    """Page di luar rentang tidak boleh 500 dan harus tetap merender halaman valid."""
    from app.main import app
    from app.services import scanner_simulator
    from app.services.attendance import AttendanceService
    from app.services.students import StudentService

    test_db = tmp_path / "sim_clamp.db"
    test_students = StudentService(test_db)
    test_attendance = AttendanceService(test_db)

    monkeypatch.setattr(scanner_simulator, "students", test_students)
    monkeypatch.setattr(scanner_simulator, "attendance", test_attendance)
    monkeypatch.setattr(scanner_simulator, "is_simulation_enabled", lambda: True)

    for index in range(1, 21):
        test_students.save_student(None, f"Murid Uji {index:02d}", index, {})

    body = _get_html(app, "/admin/simulator?page=9999")
    assert "Simulator RFID" in body
    # Page di-clamp ke halaman terakhir, jadi link pagination tetap ada.
    assert "?page=" in body


def test_simulator_page_15_items_per_page(tmp_path, monkeypatch):
    """Setiap halaman harus paling banyak 15 baris murid."""
    from app.main import app
    from app.services import scanner_simulator
    from app.services.attendance import AttendanceService
    from app.services.students import StudentService

    test_db = tmp_path / "sim_limit.db"
    test_students = StudentService(test_db)
    test_attendance = AttendanceService(test_db)

    monkeypatch.setattr(scanner_simulator, "students", test_students)
    monkeypatch.setattr(scanner_simulator, "attendance", test_attendance)
    monkeypatch.setattr(scanner_simulator, "is_simulation_enabled", lambda: True)

    for index in range(1, 31):
        test_students.save_student(None, f"Murid Limit {index:02d}", index, {})

    body1 = _get_html(app, "/admin/simulator?page=1")
    body2 = _get_html(app, "/admin/simulator?page=2")
    # Setiap halaman berisi maksimal 15 baris murid; hitung baris tabel.
    rows1 = body1.count("<td>")
    rows2 = body2.count("<td>")
    # 15 murid × 6 kolom tabel per halaman.
    assert rows1 == 90
    assert rows2 == 90


def test_students_admin_page_pagination(tmp_path, monkeypatch):
    """Menu /admin/santri harus merender link pagination saat jumlah murid > 15."""
    from app.main import app
    from app.routers import admin as admin_router
    from app.services.students import StudentService

    test_db = tmp_path / "students_admin.db"
    test_students = StudentService(test_db)

    monkeypatch.setattr(admin_router, "students", test_students)

    for index in range(1, 26):
        test_students.save_student(None, f"Murid Data {index:02d}", index, {})

    body1 = _get_html(app, "/admin/murid?page=1")
    assert 'class="pagination"' in body1
    assert "Menampilkan 1–15 dari 25 murid" in body1
    assert "/admin/murid?page=2" in body1

    body2 = _get_html(app, "/admin/murid?page=2")
    assert "Menampilkan 16–25 dari 25 murid" in body2


def test_parse_time_minutes_edge_cases():
    """Fungsi parse_time_minutes harus defensif dan tidak melempar exception."""
    from app.services.attendance import parse_time_minutes

    assert parse_time_minutes("07:30") == 7 * 60 + 30
    assert parse_time_minutes("07.30") == 7 * 60 + 30
    assert parse_time_minutes("13:45:00") == 13 * 60 + 45
    assert parse_time_minutes("") == 0
    assert parse_time_minutes(None) == 0
    assert parse_time_minutes("invalid") == 0
    assert parse_time_minutes("12") == 0
    assert parse_time_minutes("ab:cd") == 0


def test_no_santri_terminology_in_ui_pages(tmp_path, monkeypatch):
    """Memastikan kata 'santri' tidak muncul sama sekali di teks/placeholder UI yang dilihat pengguna."""
    import re
    from app.main import app
    from app.services import scanner_simulator
    from app.services.attendance import AttendanceService
    from app.services.students import StudentService

    test_db = tmp_path / "terminology.db"
    test_students = StudentService(test_db)
    test_attendance = AttendanceService(test_db)

    monkeypatch.setattr(scanner_simulator, "students", test_students)
    monkeypatch.setattr(scanner_simulator, "attendance", test_attendance)
    monkeypatch.setattr(scanner_simulator, "is_simulation_enabled", lambda: True)

    pages = ["/admin/murid", "/admin/santri", "/admin/hari-ini", "/admin/rekap", "/admin/simulator", "/admin/import", "/scan"]
    for path in pages:
        html = _get_html(app, path)
        attributes = re.findall(r'(?:placeholder|title|aria-label|alt)=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for attr in attributes:
            assert "santri" not in attr.lower(), f"Kata 'santri' ditemukan di atribut UI: '{attr}' pada halaman {path}"

        no_scripts = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text_only = re.sub(r'<[^>]+>', ' ', no_scripts)
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', text_only)]
        assert "santri" not in words, f"Kata 'santri' ditemukan di teks UI pada halaman {path}: {text_only[:200]}"


def _get_html(app, path):
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
    return bytes(body).decode("utf-8", errors="replace")
