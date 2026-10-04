from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.db import connect, get_setting, initialize, set_setting

RESULTS = {
    "berhasil",
    "duplikat",
    "tidak_dikenal",
    "tidak_aktif",
    "registrasi",
    "uid_terpakai",
}


def normalize_uid(uid: str) -> str:
    value = uid.strip().upper()
    return re.sub(r"^[^A-Z0-9]+|[^A-Z0-9]+$", "", value)


def now_local() -> datetime:
    return datetime.now().astimezone()


class AttendanceService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        initialize(db_path)

    def add_student(
        self,
        name: str,
        uid: str | None = None,
        active: bool = True,
        number: int | None = None,
    ) -> int:
        normalized = normalize_uid(uid) if uid else None
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO santri "
                "(nomor_urut, rfid_uid, nama, aktif, created_at) VALUES (?, ?, ?, ?, ?)",
                (number, normalized, name, int(active), now_local().isoformat(timespec="seconds")),
            )
            return int(cursor.lastrowid)

    def set_registration(self, student_id: int, minutes: int = 2) -> None:
        expires = now_local() + timedelta(minutes=minutes)
        with connect(self.db_path) as connection:
            if connection.execute(
                "SELECT 1 FROM santri WHERE id = ?", (student_id,)
            ).fetchone() is None:
                raise ValueError("Santri tidak ditemukan.")
            set_setting(connection, "registrasi_santri_id", str(student_id))
            set_setting(connection, "registrasi_expires", expires.isoformat())

    def tap(
        self,
        uid: str,
        client_id: str | None = None,
        client_tap_id: str | None = None,
        age_ms: int = 0,
        current_time: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_uid(uid)
        if age_ms < 0:
            age_ms = 0
        tap_time = (current_time or now_local()) - timedelta(milliseconds=age_ms)
        tap_timestamp = tap_time.isoformat(timespec="seconds")
        date = tap_time.date().isoformat()
        time = tap_time.time().replace(microsecond=0).isoformat()

        with connect(self.db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = None
            if client_id and client_tap_id:
                existing = connection.execute(
                    "SELECT * FROM tap_log WHERE client_id = ? AND client_tap_id = ?",
                    (client_id, client_tap_id),
                ).fetchone()
            if existing:
                return self._response_for_log(connection, existing)

            registration_id = get_setting(connection, "registrasi_santri_id")
            registration_expires = get_setting(connection, "registrasi_expires")
            registration_active = False
            if registration_id and registration_expires:
                try:
                    registration_active = now_local() < datetime.fromisoformat(
                        registration_expires
                    )
                except ValueError:
                    registration_active = False

            student = connection.execute(
                "SELECT * FROM santri WHERE rfid_uid = ?", (normalized,)
            ).fetchone()
            result = "tidak_dikenal"
            student_id = None
            waktu = None
            if registration_active:
                target_id = int(registration_id)
                if student and student["id"] != target_id:
                    result = "uid_terpakai"
                    student_id = None
                elif student is None:
                    connection.execute(
                        "UPDATE santri SET rfid_uid = ? WHERE id = ?",
                        (normalized, target_id),
                    )
                    set_setting(connection, "registrasi_santri_id", None)
                    set_setting(connection, "registrasi_expires", None)
                    student = connection.execute(
                        "SELECT * FROM santri WHERE id = ?", (target_id,)
                    ).fetchone()
                    result = "registrasi"
                    student_id = target_id
                else:
                    result = "registrasi"
                    student_id = target_id
            elif student is None:
                result = "tidak_dikenal"
            elif not student["aktif"]:
                result = "tidak_aktif"
                student_id = student["id"]
            else:
                student_id = student["id"]
                attendance = connection.execute(
                    "SELECT waktu FROM absensi WHERE santri_id = ? AND tanggal = ?",
                    (student_id, date),
                ).fetchone()
                if attendance:
                    result = "duplikat"
                    waktu = attendance["waktu"]
                else:
                    connection.execute(
                        "INSERT INTO absensi "
                        "(santri_id, tanggal, waktu, status, sumber) "
                        "VALUES (?, ?, ?, 'Hadir', 'kartu')",
                        (student_id, date, time),
                    )
                    result = "berhasil"
                    waktu = time

            connection.execute(
                "INSERT INTO tap_log "
                "(rfid_uid, waktu_tap, hasil, santri_id, client_id, client_tap_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (normalized, tap_timestamp, result, student_id, client_id, client_tap_id),
            )
            public_student = None if result == "uid_terpakai" else student
            return self._response(result, public_student, waktu)

    @staticmethod
    def _response(
        result: str, student: sqlite3.Row | None, waktu: str | None
    ) -> dict[str, Any]:
        response: dict[str, Any] = {
            "hasil": result,
            "pesan": {
                "berhasil": "Absensi berhasil dicatat.",
                "duplikat": "Santri sudah absen hari ini.",
                "tidak_dikenal": "Kartu belum terdaftar.",
                "tidak_aktif": "Data santri ini sedang tidak aktif.",
                "registrasi": "Kartu berhasil didaftarkan.",
                "uid_terpakai": "Kartu sudah dipakai santri lain.",
            }[result],
        }
        if result != "tidak_dikenal" and student:
            response.update({"nama": student["nama"], "nomor_urut": student["nomor_urut"]})
        if waktu:
            response["waktu"] = waktu
        return response

    def _response_for_log(
        self, connection: sqlite3.Connection, log: sqlite3.Row
    ) -> dict[str, Any]:
        student = (
            connection.execute("SELECT * FROM santri WHERE id = ?", (log["santri_id"],)).fetchone()
            if log["santri_id"]
            else None
        )
        waktu = None
        if student and log["hasil"] in {"berhasil", "duplikat"}:
            row = connection.execute(
                "SELECT waktu FROM absensi WHERE santri_id = ? ORDER BY id DESC LIMIT 1",
                (student["id"],),
            ).fetchone()
            waktu = row["waktu"] if row else None
        return self._response(log["hasil"], student, waktu)
