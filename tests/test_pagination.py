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


def test_simulator_page_renders_pagination_controls():
    """Halaman simulator harus merender link pagination dan 15 baris per halaman."""
    from app.main import app
    from app.runtime import DB_PATH

    students = StudentService(DB_PATH)
    before = students.list_students()
    try:
        # Siapkan lebih dari 15 murid agar pagination nav muncul.
        for index in range(1, 21):
            students.save_student(None, f"Murid Uji {index:02d}", index, {})

        total_expected = len(before) + 20
        body = _get_html(app, "/admin/simulator")
        assert 'class="pagination"' in body
        assert "pagination-btn" in body
        assert f"Menampilkan 1–15 dari {total_expected} murid" in body
        # Tombol simulasi tap hanya untuk murid yang sudah punya kartu
        assert "data-sim-tap-uid" in body
    finally:
        # Kembalikan DB ke kondisi awal.
        for s in students.list_students():
            if s["id"] not in {x["id"] for x in before}:
                students.delete_student(s["id"])


def test_simulator_page_clamps_out_of_range_page():
    """Page di luar rentang tidak boleh 500 dan harus tetap merender halaman valid."""
    from app.main import app
    from app.runtime import DB_PATH

    students = StudentService(DB_PATH)
    before = students.list_students()
    try:
        for index in range(1, 21):
            students.save_student(None, f"Murid Uji {index:02d}", index, {})

        body = _get_html(app, "/admin/simulator?page=9999")
        assert "Simulator RFID" in body
        # Page di-clamp ke halaman terakhir, jadi link pagination tetap ada.
        assert "?page=" in body
    finally:
        for s in students.list_students():
            if s["id"] not in {x["id"] for x in before}:
                students.delete_student(s["id"])


def test_simulator_page_15_items_per_page():
    """Setiap halaman harus paling banyak 15 baris murid."""
    from app.main import app
    from app.runtime import DB_PATH

    students = StudentService(DB_PATH)
    before = students.list_students()
    try:
        for index in range(1, 31):
            students.save_student(None, f"Murid Limit {index:02d}", index, {})

        body1 = _get_html(app, "/admin/simulator?page=1")
        body2 = _get_html(app, "/admin/simulator?page=2")
        # Setiap halaman berisi maksimal 15 judul kolom/table-bar murid; hitung baris tabel.
        rows1 = body1.count("<td>")
        rows2 = body2.count("<td>")
        # 15 murid × 6 kolom tabel per halaman.
        assert rows1 == 90
        assert rows2 == 90
    finally:
        for s in students.list_students():
            if s["id"] not in {x["id"] for x in before}:
                students.delete_student(s["id"])


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
