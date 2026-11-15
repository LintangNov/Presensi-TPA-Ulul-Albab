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
            student_ids = [row["id"] for row in rows]
            cards_map = self._get_cards_map(connection, student_ids)
            return [self._student(row, cards_map.get(row["id"], [])) for row in rows]

    def list_students_paginated(
        self, search: str = "", page: int = 1, per_page: int = 15
    ) -> tuple[list[dict[str, Any]], int]:
        """Ambil satu halaman data murid beserta jumlah total baris.

        Query dijalankan di level SQL (LIMIT/OFFSET) agar tidak memuat
        seluruh tabel ke memori. Mengembalikan tuple (baris, total).
        """
        page = max(1, page)
        per_page = max(1, per_page)
        offset = (page - 1) * per_page
        pattern = f"%{search}%"
        with connect(self.db_path) as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM santri WHERE nama LIKE ? OR CAST(nomor_urut AS TEXT) LIKE ?",
                (pattern, pattern),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM santri WHERE nama LIKE ? OR CAST(nomor_urut AS TEXT) LIKE ? "
                "ORDER BY aktif DESC, nomor_urut, nama "
                "LIMIT ? OFFSET ?",
                (pattern, pattern, per_page, offset),
            ).fetchall()
            student_ids = [row["id"] for row in rows]
            cards_map = self._get_cards_map(connection, student_ids)
            return [self._student(row, cards_map.get(row["id"], [])) for row in rows], int(total)

    def get_student(self, student_id: int) -> dict[str, Any] | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM santri WHERE id = ?", (student_id,)
            ).fetchone()
            if not row:
                return None
            cards_map = self._get_cards_map(connection, [student_id])
            return self._student(row, cards_map.get(student_id, []))

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
        nomor_kartu_str = str(number) if number is not None else ""
        with connect(self.db_path) as connection:
            if student_id:
                connection.execute(
                    "UPDATE santri SET nomor_urut = ?, nama = ?, extra_data = ?, paket = ? WHERE id = ?",
                    (number, name.strip(), payload, paket_val, student_id),
                )
                # Sinkronisasikan nomor_kartu_custom di tabel kartu_santri agar sesuai nomor absen murid
                connection.execute(
                    "UPDATE kartu_santri SET nomor_kartu_custom = ? WHERE santri_id = ?",
                    (nomor_kartu_str, student_id),
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
            connection.execute("DELETE FROM kartu_santri WHERE santri_id = ?", (student_id,))
            connection.execute("DELETE FROM santri WHERE id = ?", (student_id,))
            connection.commit()

    def get_cards(self, student_id: int) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM kartu_santri WHERE santri_id = ? ORDER BY slot ASC, id ASC",
                (student_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "santri_id": r["santri_id"],
                    "rfid_uid": r["rfid_uid"],
                    "nomor_kartu_custom": r["nomor_kartu_custom"],
                    "slot": r["slot"],
                    "label": r["label"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def register_card(
        self,
        student_id: int,
        uid: str,
        slot: int = 1,
        label: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_uid(uid)
        if not normalized:
            raise ValueError("UID kartu kosong.")
        slot = 2 if slot == 2 else 1
        default_label = "Kartu 1" if slot == 1 else "Kartu 2"
        card_label = label.strip() if label and label.strip() else default_label

        with connect(self.db_path) as connection:
            student = connection.execute(
                "SELECT id, nama, nomor_urut FROM santri WHERE id = ?", (student_id,)
            ).fetchone()
            if student is None:
                raise LookupError("Murid tidak ditemukan.")

            # Cek apakah UID sudah dipakai oleh murid lain
            owner_card = connection.execute(
                "SELECT santri_id FROM kartu_santri WHERE rfid_uid = ? AND santri_id != ?",
                (normalized, student_id),
            ).fetchone()
            owner_santri = connection.execute(
                "SELECT id FROM santri WHERE rfid_uid = ? AND id != ?",
                (normalized, student_id),
            ).fetchone()
            if owner_card or owner_santri:
                raise ValueError("Kartu sudah dipakai murid lain.")

            nomor_kartu_custom = str(student["nomor_urut"]) if student["nomor_urut"] is not None else ""
            now_str = now_local().isoformat(timespec="seconds")

            # Periksa apakah slot ini sudah terisi untuk santri tersebut
            existing_slot = connection.execute(
                "SELECT id FROM kartu_santri WHERE santri_id = ? AND slot = ?",
                (student_id, slot),
            ).fetchone()

            if existing_slot:
                connection.execute(
                    "UPDATE kartu_santri SET rfid_uid = ?, nomor_kartu_custom = ?, label = ?, created_at = ? WHERE id = ?",
                    (normalized, nomor_kartu_custom, card_label, now_str, existing_slot["id"]),
                )
            else:
                connection.execute(
                    "INSERT INTO kartu_santri (santri_id, rfid_uid, nomor_kartu_custom, slot, label, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (student_id, normalized, nomor_kartu_custom, slot, card_label, now_str),
                )

            # Jika slot 1 didaftarkan (atau kolom santri.rfid_uid belum terisi), update santri.rfid_uid untuk kompatibilitas
            if slot == 1 or not connection.execute("SELECT rfid_uid FROM santri WHERE id = ?", (student_id,)).fetchone()[0]:
                connection.execute(
                    "UPDATE santri SET rfid_uid = ? WHERE id = ?",
                    (normalized, student_id),
                )

            return {
                "ok": True,
                "uid": normalized,
                "nama": student["nama"],
                "nomor_urut": student["nomor_urut"],
                "slot": slot,
                "label": card_label,
                "nomor_kartu_custom": nomor_kartu_custom,
            }

    def delete_card(self, student_id: int, slot: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "DELETE FROM kartu_santri WHERE santri_id = ? AND slot = ?",
                (student_id, slot),
            )
            # Sinkronisasi santri.rfid_uid dengan kartu yang tersisa
            remaining = connection.execute(
                "SELECT rfid_uid FROM kartu_santri WHERE santri_id = ? ORDER BY slot ASC LIMIT 1",
                (student_id,),
            ).fetchone()
            new_uid = remaining["rfid_uid"] if remaining else None
            connection.execute(
                "UPDATE santri SET rfid_uid = ? WHERE id = ?",
                (new_uid, student_id),
            )

    @staticmethod
    def _get_cards_map(connection: sqlite3.Connection, student_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not student_ids:
            return {}
        placeholders = ",".join("?" for _ in student_ids)
        rows = connection.execute(
            f"SELECT * FROM kartu_santri WHERE santri_id IN ({placeholders}) ORDER BY slot ASC, id ASC",
            student_ids,
        ).fetchall()
        result: dict[int, list[dict[str, Any]]] = {sid: [] for sid in student_ids}
        for r in rows:
            result[r["santri_id"]].append({
                "id": r["id"],
                "santri_id": r["santri_id"],
                "rfid_uid": r["rfid_uid"],
                "nomor_kartu_custom": r["nomor_kartu_custom"],
                "slot": r["slot"],
                "label": r["label"],
                "created_at": r["created_at"],
            })
        return result

    @staticmethod
    def _student(row: sqlite3.Row, cards: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        try:
            extra = json.loads(row["extra_data"] or "{}")
        except json.JSONDecodeError:
            extra = {}
        row_keys = row.keys() if hasattr(row, "keys") else []
        cards_list = cards or []
        card_1 = next((c for c in cards_list if c["slot"] == 1), None)
        card_2 = next((c for c in cards_list if c["slot"] == 2), None)
        # Jika belum ada di kartu_santri tapi ada di row["rfid_uid"], gunakan row["rfid_uid"]
        effective_rfid_uid = (card_1["rfid_uid"] if card_1 else None) or row["rfid_uid"]
        nomor_absen_str = str(row["nomor_urut"]) if row["nomor_urut"] is not None else ""

        return {
            "id": row["id"],
            "nomor_urut": row["nomor_urut"],
            "nomor_kartu_custom": nomor_absen_str,
            "rfid_uid": effective_rfid_uid,
            "nama": row["nama"],
            "paket": row["paket"] if "paket" in row_keys else "A",
            "extra_data": extra,
            "aktif": bool(row["aktif"]),
            "cards": cards_list,
            "card_1": card_1,
            "card_2": card_2,
        }
