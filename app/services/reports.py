from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.db import connect


class ReportService:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def attendance_rows(
        self,
        start: str,
        end: str,
        student_id: int | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["a.tanggal BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        if student_id:
            clauses.append("s.id = ?")
            params.append(student_id)
        if status:
            clauses.append("a.status = ?")
            params.append(status)
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT a.tanggal, s.nomor_urut, s.nama, a.waktu, a.status, "
                "a.sumber, a.catatan, s.id AS santri_id, s.extra_data "
                "FROM absensi a JOIN santri s ON s.id = a.santri_id "
                f"WHERE {' AND '.join(clauses)} ORDER BY a.tanggal, s.nomor_urut, s.nama",
                params,
            ).fetchall()
            tpa_dates = {
                row["tanggal"]
                for row in connection.execute(
                    "SELECT DISTINCT tanggal FROM absensi WHERE tanggal BETWEEN ? AND ?",
                    (start, end),
                ).fetchall()
            }
            active_students = connection.execute(
                "SELECT id, nomor_urut, nama, extra_data FROM santri WHERE aktif = 1"
                + (" AND id = ?" if student_id else ""),
                (student_id,) if student_id else (),
            ).fetchall()
            recorded = {
                (row["santri_id"], row["tanggal"])
                for row in connection.execute(
                    "SELECT santri_id, tanggal FROM absensi WHERE tanggal BETWEEN ? AND ?",
                    (start, end),
                ).fetchall()
            }
        result = [dict(row) for row in rows]
        if not status or status == "Alpha":
            for student in active_students:
                for day in sorted(tpa_dates):
                    if (student["id"], day) not in recorded:
                        result.append(
                            {
                                "tanggal": day,
                                "nomor_urut": student["nomor_urut"],
                                "nama": student["nama"],
                                "waktu": None,
                                "status": "Alpha",
                                "sumber": "otomatis",
                                "catatan": None,
                                "santri_id": student["id"],
                                "extra_data": student["extra_data"],
                            }
                        )
        return sorted(result, key=lambda row: (row["tanggal"], row["nomor_urut"] or 0, row["nama"]))

    def summary(
        self, start: str, end: str, student_id: int | None = None
    ) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            students = connection.execute(
                "SELECT id, nomor_urut, nama FROM santri WHERE aktif = 1 "
                + ("AND id = ?" if student_id else "")
                + " ORDER BY nomor_urut, nama",
                (student_id,) if student_id else (),
            ).fetchall()
            attendance = connection.execute(
                "SELECT santri_id, tanggal, status FROM absensi WHERE tanggal BETWEEN ? AND ?",
                (start, end),
            ).fetchall()
            tpa_dates = {
                row["tanggal"]
                for row in attendance
            }
        by_student: dict[int, dict[str, int]] = {}
        for row in attendance:
            counts = by_student.setdefault(
                row["santri_id"], {"Hadir": 0, "Izin": 0, "Sakit": 0, "Alpha": 0}
            )
            if row["status"] in counts:
                counts[row["status"]] += 1
        result = []
        for student in students:
            counts = by_student.setdefault(
                student["id"], {"Hadir": 0, "Izin": 0, "Sakit": 0, "Alpha": 0}
            )
            recorded_dates = {
                row["tanggal"]
                for row in attendance
                if row["santri_id"] == student["id"]
            }
            counts["Alpha"] += len(tpa_dates - recorded_dates)
            result.append(
                {
                    "nomor_urut": student["nomor_urut"],
                    "nama": student["nama"],
                    **counts,
                }
            )
        return result

    def save_manual(
        self,
        student_id: int,
        tanggal: str,
        status: str,
        waktu: str | None,
        catatan: str | None,
    ) -> None:
        if status not in {"Hadir", "Izin", "Sakit", "Alpha"}:
            raise ValueError("Status absensi tidak valid.")
        with connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO absensi (santri_id, tanggal, waktu, status, sumber, catatan) "
                "VALUES (?, ?, ?, ?, 'manual', ?) "
                "ON CONFLICT(santri_id, tanggal) DO UPDATE SET waktu=excluded.waktu, "
                "status=excluded.status, sumber='manual', catatan=excluded.catatan",
                (student_id, tanggal, waktu or None, status, catatan or None),
            )

    def delete_manual(self, attendance_id: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "DELETE FROM absensi WHERE id = ? AND sumber = 'manual'",
                (attendance_id,),
            )
