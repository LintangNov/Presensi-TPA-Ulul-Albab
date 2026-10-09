from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.db import connect, get_setting, initialize, set_setting

RESULTS = {
    "berhasil",
    "pulang",
    "denda",
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


def parse_time_minutes(time_str: str) -> int:
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


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
        paket: str = "A",
    ) -> int:
        normalized = normalize_uid(uid) if uid else None
        paket_val = paket.strip().upper() if paket and paket.strip().upper() in {"A", "B"} else "A"
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO santri "
                "(nomor_urut, rfid_uid, nama, paket, aktif, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (number, normalized, name, paket_val, int(active), now_local().isoformat(timespec="seconds")),
            )
            return int(cursor.lastrowid)

    def set_registration(self, student_id: int, minutes: int = 2) -> None:
        expires = now_local() + timedelta(minutes=minutes)
        with connect(self.db_path) as connection:
            if connection.execute(
                "SELECT 1 FROM santri WHERE id = ?", (student_id,)
            ).fetchone() is None:
                raise ValueError("Murid tidak ditemukan.")
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
            tipe_tap = None
            denda_menit = 0
            custom_message = None

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
                    "SELECT * FROM absensi WHERE santri_id = ? AND tanggal = ?",
                    (student_id, date),
                ).fetchone()

                if not attendance:
                    # Tap pertama hari ini -> Absen Masuk
                    tipe_tap = "masuk"
                    result = "berhasil"
                    waktu = time
                    catatan = "Masuk sebelum jam operasional" if time < "06:30:00" else None
                    connection.execute(
                        "INSERT INTO absensi "
                        "(santri_id, tanggal, waktu, status, sumber, catatan) "
                        "VALUES (?, ?, ?, 'Hadir', 'kartu', ?)",
                        (student_id, date, time, catatan),
                    )
                else:
                    # Sudah ada absensi hari ini
                    waktu_masuk = attendance["waktu"]
                    waktu_pulang_existing = attendance["waktu_pulang"]

                    # Cek jeda tap dari waktu masuk (minimal 1 menit untuk dianggap tap pulang, mencegah double tap instan)
                    masuk_mins = parse_time_minutes(waktu_masuk) if waktu_masuk else 0
                    current_mins = parse_time_minutes(time)
                    diff_mins = current_mins - masuk_mins

                    if diff_mins < 1 and not waktu_pulang_existing:
                        # Tap dalam selisih kurang dari 1 menit setelah masuk -> duplikat masuk
                        result = "duplikat"
                        waktu = waktu_masuk
                        tipe_tap = "masuk"
                        custom_message = f"Absensi masuk baru saja dicatat pada pukul {waktu_masuk}."
                    elif not waktu_pulang_existing:
                        # Tap kedua -> Penjemputan / Pulang
                        tipe_tap = "pulang"
                        waktu = time
                        student_keys = student.keys() if hasattr(student, "keys") else []
                        paket = student["paket"] if "paket" in student_keys else "A"

                        # Batas penjemputan dan toleransi 15 menit
                        # Paket A (Half Day): 13.00 toleransi 15 mnt -> 13.15 (795 menit)
                        # Paket B (Full Day): 16.00 toleransi 15 mnt -> 16.15 (975 menit)
                        if paket == "B":
                            toleransi_mins = 16 * 60 + 15
                            batas_teks = "16:00 (toleransi 16:15)"
                        else:
                            toleransi_mins = 13 * 60 + 15
                            batas_teks = "13:00 (toleransi 13:15)"

                        if current_mins > toleransi_mins:
                            denda_menit = current_mins - toleransi_mins
                            status_pulang = "Denda Keterlambatan"
                            result = "denda"
                            custom_message = (
                                f"Penjemputan lewat batas {batas_teks}. "
                                f"Terlambat {denda_menit} menit. Dikenakan denda."
                            )
                        else:
                            status_pulang = "Tepat Waktu"
                            result = "pulang"
                            custom_message = f"Penjemputan tepat waktu ({time}). Sampai jumpa!"

                        connection.execute(
                            "UPDATE absensi SET waktu_pulang = ?, status_pulang = ?, denda_menit = ? "
                            "WHERE santri_id = ? AND tanggal = ?",
                            (time, status_pulang, denda_menit, student_id, date),
                        )
                    else:
                        # Sudah absen pulang sebelumnya
                        result = "duplikat"
                        waktu = waktu_pulang_existing
                        tipe_tap = "pulang"
                        custom_message = f"Murid sudah dijemput hari ini pada pukul {waktu_pulang_existing}."

            connection.execute(
                "INSERT INTO tap_log "
                "(rfid_uid, waktu_tap, hasil, santri_id, client_id, client_tap_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (normalized, tap_timestamp, result, student_id, client_id, client_tap_id),
            )
            public_student = None if result == "uid_terpakai" else student
            return self._response(
                result=result,
                student=public_student,
                waktu=waktu,
                tipe_tap=tipe_tap,
                denda_menit=denda_menit,
                custom_message=custom_message,
            )

    @staticmethod
    def _response(
        result: str,
        student: sqlite3.Row | None,
        waktu: str | None,
        tipe_tap: str | None = None,
        denda_menit: int = 0,
        custom_message: str | None = None,
    ) -> dict[str, Any]:
        default_messages = {
            "berhasil": "Absensi masuk berhasil dicatat.",
            "pulang": "Penjemputan tepat waktu berhasil dicatat.",
            "denda": "Penjemputan melewati batas waktu toleransi. Dikenakan denda.",
            "duplikat": "Murid sudah memiliki catatan absensi hari ini.",
            "tidak_dikenal": "Kartu belum terdaftar.",
            "tidak_aktif": "Data murid ini sedang tidak aktif.",
            "registrasi": "Kartu berhasil didaftarkan.",
            "uid_terpakai": "Kartu sudah dipakai murid lain.",
        }
        response: dict[str, Any] = {
            "hasil": result,
            "pesan": custom_message or default_messages.get(result, "Tap diproses."),
        }
        if result != "tidak_dikenal" and student:
            student_keys = student.keys() if hasattr(student, "keys") else []
            paket = student["paket"] if "paket" in student_keys else "A"
            response.update({
                "nama": student["nama"],
                "nomor_urut": student["nomor_urut"],
                "paket": paket,
                "paket_label": "Paket A (Half Day)" if paket == "A" else "Paket B (Full Day)",
            })
        if waktu:
            response["waktu"] = waktu
        if tipe_tap:
            response["tipe_tap"] = tipe_tap
        if denda_menit > 0:
            response["denda_menit"] = denda_menit
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
        tipe_tap = None
        denda_menit = 0
        if student and log["hasil"] in {"berhasil", "pulang", "denda", "duplikat"}:
            row = connection.execute(
                "SELECT * FROM absensi WHERE santri_id = ? ORDER BY id DESC LIMIT 1",
                (student["id"],),
            ).fetchone()
            if row:
                if log["hasil"] in {"pulang", "denda"}:
                    waktu = row["waktu_pulang"] or row["waktu"]
                    tipe_tap = "pulang"
                    denda_menit = row["denda_menit"] or 0
                else:
                    waktu = row["waktu"]
                    tipe_tap = "masuk"
        return self._response(
            result=log["hasil"],
            student=student,
            waktu=waktu,
            tipe_tap=tipe_tap,
            denda_menit=denda_menit,
        )
