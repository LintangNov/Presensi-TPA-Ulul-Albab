from datetime import datetime

import pytest

from app.db import connect
from app.services.attendance import AttendanceService, normalize_uid


@pytest.fixture
def service(tmp_path):
    return AttendanceService(tmp_path / "test.db")


def test_normalize_uid_matches_reader_enter(service):
    assert normalize_uid("  ab-12\r\n") == "AB-12"


def test_successful_tap_and_duplicate(service):
    student_id = service.add_student("Aisyah", "0012", number=3)
    first = service.tap(" 0012\r\n", "hp-1", "tap-1")
    second = service.tap("0012", "hp-1", "tap-2")

    assert student_id == 1
    assert first["hasil"] == "berhasil"
    assert first["nama"] == "Aisyah"
    assert second["hasil"] == "duplikat"
    with connect(service.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM absensi").fetchone()[0] == 1


def test_unknown_card_does_not_leak_student_data(service):
    service.add_student("Rahasia", "KNOWN")
    result = service.tap("UNKNOWN", "hp-1", "tap-unknown")

    assert result["hasil"] == "tidak_dikenal"
    assert "nama" not in result
    assert "nomor_urut" not in result


def test_inactive_student(service):
    service.add_student("Tidak Aktif", "OFF", active=False)

    result = service.tap("OFF", "hp-1", "tap-off")

    assert result["hasil"] == "tidak_aktif"
    assert result["nama"] == "Tidak Aktif"


def test_same_client_tap_is_idempotent(service):
    service.add_student("Budi", "BUDI")
    first = service.tap("BUDI", "hp-1", "same-id")
    retry = service.tap("BUDI", "hp-1", "same-id")

    assert first == retry
    with connect(service.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tap_log").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM absensi").fetchone()[0] == 1


def test_registration_success(service):
    student_id = service.add_student("Citra")
    service.set_registration(student_id)

    result = service.tap("new-card\r\n", "hp-1", "register-1")

    assert result["hasil"] == "registrasi"
    with connect(service.db_path) as connection:
        assert connection.execute(
            "SELECT rfid_uid FROM santri WHERE id = ?", (student_id,)
        ).fetchone()[0] == "NEW-CARD"


def test_registration_rejects_uid_used_by_another_student(service):
    first_id = service.add_student("Dina", "USED")
    second_id = service.add_student("Eka")
    service.set_registration(second_id)

    result = service.tap("USED", "hp-1", "register-used")

    assert first_id != second_id
    assert result["hasil"] == "uid_terpakai"
    assert "nama" not in result


def test_expired_registration_is_not_used(service):
    student_id = service.add_student("Fajar")
    service.set_registration(student_id, minutes=-1)

    result = service.tap("expired-card", "hp-1", "register-expired")

    assert result["hasil"] == "tidak_dikenal"


def test_database_pragmas_and_schema_version(service):
    with connect(service.db_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 2


def test_age_ms_uses_laptop_time_for_attendance(service):
    service.add_student("Gita", "GITA")
    current = datetime.fromisoformat("2026-10-04T10:00:00+07:00")

    result = service.tap("GITA", "hp-1", "old-tap", age_ms=65_000, current_time=current)

    assert result["hasil"] == "berhasil"
    assert result["waktu"] == "09:58:55"
    with connect(service.db_path) as connection:
        row = connection.execute(
            "SELECT tanggal, waktu FROM absensi"
        ).fetchone()
        assert tuple(row) == ("2026-10-04", "09:58:55")


def test_tpa_paket_a_pickup_ontime_and_late_fee(service):
    # Paket A: Max 13:00, tolerance 15 mins -> 13:15
    service.add_student("Ahmad", "AHMAD", paket="A")
    t_masuk = datetime.fromisoformat("2026-10-08T07:15:00+07:00")
    t_pulang_ontime = datetime.fromisoformat("2026-10-08T13:10:00+07:00")

    res_masuk = service.tap("AHMAD", "lap", "tap-in", current_time=t_masuk)
    assert res_masuk["hasil"] == "berhasil"
    assert res_masuk["tipe_tap"] == "masuk"

    res_pulang = service.tap("AHMAD", "lap", "tap-out", current_time=t_pulang_ontime)
    assert res_pulang["hasil"] == "pulang"
    assert res_pulang["tipe_tap"] == "pulang"
    assert "tepat waktu" in res_pulang["pesan"].lower()

    # Student 2: late pickup at 13:30 (15 mins late past 13:15)
    service.add_student("Budi Late", "BUDILATE", paket="A")
    t_pulang_late = datetime.fromisoformat("2026-10-08T13:30:00+07:00")
    service.tap("BUDILATE", "lap", "budi-in", current_time=t_masuk)
    res_budi_out = service.tap("BUDILATE", "lap", "budi-out", current_time=t_pulang_late)

    assert res_budi_out["hasil"] == "denda"
    assert res_budi_out["denda_menit"] == 15
    assert "denda" in res_budi_out["pesan"].lower()


def test_tpa_paket_b_pickup_ontime_and_late_fee(service):
    # Paket B: Max 16:00, tolerance 15 mins -> 16:15
    service.add_student("Citra", "CITRA", paket="B")
    t_masuk = datetime.fromisoformat("2026-10-08T07:00:00+07:00")
    t_pulang_ontime = datetime.fromisoformat("2026-10-08T16:10:00+07:00")

    service.tap("CITRA", "lap", "c-in", current_time=t_masuk)
    res_ontime = service.tap("CITRA", "lap", "c-out", current_time=t_pulang_ontime)
    assert res_ontime["hasil"] == "pulang"

    # Student 2: late pickup at 16:35 (20 mins late past 16:15)
    service.add_student("Doni", "DONI", paket="B")
    t_pulang_late = datetime.fromisoformat("2026-10-08T16:35:00+07:00")
    service.tap("DONI", "lap", "d-in", current_time=t_masuk)
    res_late = service.tap("DONI", "lap", "d-out", current_time=t_pulang_late)

    assert res_late["hasil"] == "denda"
    assert res_late["denda_menit"] == 20

