from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.db import connect, initialize
from app.services.attendance import normalize_uid, now_local


def field_key(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return key or "field"


class StudentService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        initialize(db_path)

    def fields(self, active_only: bool = False) -> list[sqlite3.Row]:
        with connect(self.db_path) as connection:
            query = "SELECT * FROM custom_fields"
            if active_only:
                query += " WHERE aktif = 1"
            query += " ORDER BY urutan, id"
            return connection.execute(query).fetchall()

    def add_field(self, label: str, order: int = 0) -> int:
        key = field_key(label)
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO custom_fields (field_key, field_label, urutan) VALUES (?, ?, ?)",
                (key, label.strip(), order),
            )
            return int(cursor.lastrowid)

    def update_field(self, field_id: int, label: str, order: int, active: bool = True) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE custom_fields SET field_label = ?, urutan = ?, aktif = ? WHERE id = ?",
                (label.strip(), order, int(active), field_id),
            )

    def set_field_active(self, field_id: int, active: bool) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE custom_fields SET aktif = ? WHERE id = ?",
                (int(active), field_id),
            )

    def list_students(self, search: str = "") -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM santri WHERE nama LIKE ? OR CAST(nomor_urut AS TEXT) LIKE ? "
                "ORDER BY aktif DESC, nomor_urut, nama",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
            return [self._student(row) for row in rows]

    def get_student(self, student_id: int) -> dict[str, Any] | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM santri WHERE id = ?", (student_id,)
            ).fetchone()
            return self._student(row) if row else None

    def save_student(
        self,
        student_id: int | None,
        name: str,
        number: int | None,
        extra_data: dict[str, str],
        paket: str = "A",
    ) -> int:
        if not name.strip():
            raise ValueError("Nama murid wajib diisi.")
        paket_val = paket.strip().upper() if paket and paket.strip().upper() in {"A", "B"} else "A"
        payload = json.dumps(extra_data, ensure_ascii=False)
        with connect(self.db_path) as connection:
            if student_id:
                connection.execute(
                    "UPDATE santri SET nomor_urut = ?, nama = ?, extra_data = ?, paket = ? WHERE id = ?",
                    (number, name.strip(), payload, paket_val, student_id),
                )
                return student_id
            cursor = connection.execute(
                "INSERT INTO santri (nomor_urut, nama, extra_data, paket, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (number, name.strip(), payload, paket_val, now_local().isoformat(timespec="seconds")),
            )
            return int(cursor.lastrowid)

    def set_active(self, student_id: int, active: bool) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE santri SET aktif = ? WHERE id = ?",
                (int(active), student_id),
            )

    def delete_student(self, student_id: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM tap_log WHERE santri_id = ?", (student_id,))
            connection.execute("DELETE FROM absensi WHERE santri_id = ?", (student_id,))
            connection.execute("DELETE FROM santri WHERE id = ?", (student_id,))
            connection.commit()

    def register_card(self, student_id: int, uid: str) -> dict[str, Any]:
        normalized = normalize_uid(uid)
        if not normalized:
            raise ValueError("UID kartu kosong.")
        with connect(self.db_path) as connection:
            student = connection.execute(
                "SELECT id, nama, nomor_urut FROM santri WHERE id = ?", (student_id,)
            ).fetchone()
            if student is None:
                raise LookupError("Murid tidak ditemukan.")
            owner = connection.execute(
                "SELECT id FROM santri WHERE rfid_uid = ? AND id != ?",
                (normalized, student_id),
            ).fetchone()
            if owner:
                raise ValueError("Kartu sudah dipakai murid lain.")
            connection.execute(
                "UPDATE santri SET rfid_uid = ? WHERE id = ?",
                (normalized, student_id),
            )
            return {
                "ok": True,
                "uid": normalized,
                "nama": student["nama"],
                "nomor_urut": student["nomor_urut"],
            }

    @staticmethod
    def _student(row: sqlite3.Row) -> dict[str, Any]:
        try:
            extra = json.loads(row["extra_data"] or "{}")
        except json.JSONDecodeError:
            extra = {}
        row_keys = row.keys() if hasattr(row, "keys") else []
        return {
            "id": row["id"],
            "nomor_urut": row["nomor_urut"],
            "rfid_uid": row["rfid_uid"],
            "nama": row["nama"],
            "paket": row["paket"] if "paket" in row_keys else "A",
            "extra_data": extra,
            "aktif": bool(row["aktif"]),
        }
