from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from app.db import connect
from app.runtime import check_usb_scanner_connected
from app.services.attendance import AttendanceService
from app.services.students import StudentService

logger = logging.getLogger("absensi_tpa")

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "tpa_absensi.db"

attendance = AttendanceService(DB_PATH)
students = StudentService(DB_PATH)

TEST_CARDS = [
    {"uid": "CARD-01", "label": "Kartu Uji Paket A", "paket": "A", "description": "Murid Paket A (Half Day)"},
    {"uid": "CARD-02", "label": "Kartu Uji Paket B", "paket": "B", "description": "Murid Paket B (Full Day)"},
    {"uid": "CARD-99", "label": "Kartu Tidak Dikenal", "paket": "-", "description": "UID yang belum terdaftar"},
]


def is_simulation_enabled() -> bool:
    """Simulasi hanya aktif saat:
    1. Berjalan dari source code (bukan .exe build)
    2. Tidak ada card reader RFID fisik terdeteksi
    """
    if getattr(sys, "frozen", False):
        return False
    hardware = check_usb_scanner_connected()
    return not hardware.get("connected", False)


def log_simulation_status() -> None:
    """Cetak log ke terminal tentang status simulasi saat startup."""
    if getattr(sys, "frozen", False):
        return
    if is_simulation_enabled():
        print("[Simulasi RFID] AKTIF (source code, tidak ada card reader fisik).")
    else:
        hardware = check_usb_scanner_connected()
        print(
            "[Simulasi RFID] NONAKTIF (source code, card reader fisik terdeteksi: %s)."
            % hardware.get("details", "tidak diketahui")
        )


def get_simulation_status() -> dict[str, Any]:
    return {
        "enabled": is_simulation_enabled(),
        "hardware_connected": check_usb_scanner_connected().get("connected", False),
        "frozen": getattr(sys, "frozen", False),
        "cards": TEST_CARDS,
    }


def simulate_tap(uid: str) -> dict[str, Any]:
    """Panggil attendance.tap() untuk mensimulasikan tap kartu RFID."""
    return attendance.tap(uid, client_id="simulator", client_tap_id=None)


def register_simulator_card(student_id: int, uid: str) -> dict[str, Any]:
    """Daftarkan kartu simulasi ke murid."""
    return students.register_card(student_id, uid)


def get_all_students() -> list[dict[str, Any]]:
    return students.list_students()


def get_students_page(page: int = 1, per_page: int = 15) -> tuple[list[dict[str, Any]], int]:
    """Ambil satu halaman data murid + total baris (query di level SQL)."""
    return students.list_students_paginated("", page, per_page)