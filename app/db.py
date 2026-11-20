from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 5


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5, factory=ManagedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER NOT NULL)"
        )
        current = connection.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if current is None:
            connection.executescript(
                """
                CREATE TABLE custom_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_key TEXT UNIQUE NOT NULL,
                    field_label TEXT NOT NULL,
                    urutan INTEGER NOT NULL DEFAULT 0,
                    aktif INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE santri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nomor_urut INTEGER,
                    rfid_uid TEXT UNIQUE,
                    nama TEXT NOT NULL,
                    paket TEXT NOT NULL DEFAULT 'A',
                    extra_data TEXT NOT NULL DEFAULT '{}',
                    aktif INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT
                );
                CREATE TABLE kartu_santri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    santri_id INTEGER NOT NULL REFERENCES santri(id) ON DELETE CASCADE,
                    rfid_uid TEXT UNIQUE NOT NULL,
                    nomor_kartu_custom TEXT,
                    slot INTEGER NOT NULL DEFAULT 1,
                    label TEXT NOT NULL DEFAULT 'Kartu 1',
                    created_at TEXT
                );
                CREATE TABLE absensi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    santri_id INTEGER NOT NULL REFERENCES santri(id),
                    tanggal TEXT NOT NULL,
                    waktu TEXT,
                    waktu_pulang TEXT,
                    status_pulang TEXT,
                    denda_menit INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'Hadir',
                    sumber TEXT NOT NULL DEFAULT 'kartu',
                    catatan TEXT,
                    nama_pengantar TEXT,
                    nama_penjemput TEXT,
                    alasan_tanpa_kartu TEXT,
                    alasan_penjemputan_tanpa_kartu TEXT,
                    UNIQUE(santri_id, tanggal)
                );
                CREATE TABLE tap_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfid_uid TEXT NOT NULL,
                    waktu_tap TEXT NOT NULL,
                    hasil TEXT NOT NULL,
                    santri_id INTEGER REFERENCES santri(id),
                    client_id TEXT,
                    client_tap_id TEXT,
                    UNIQUE(client_id, client_tap_id)
                );
                CREATE TABLE pengaturan (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                INSERT INTO schema_version (version) VALUES (5);
                """
            )
        else:
            # Migrasi skema jika tabel sudah ada dari versi sebelumnya
            santri_cols = {row["name"] for row in connection.execute("PRAGMA table_info(santri)").fetchall()}
            if "paket" not in santri_cols:
                connection.execute("ALTER TABLE santri ADD COLUMN paket TEXT NOT NULL DEFAULT 'A'")

            # Tabel kartu_santri
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS kartu_santri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    santri_id INTEGER NOT NULL REFERENCES santri(id) ON DELETE CASCADE,
                    rfid_uid TEXT UNIQUE NOT NULL,
                    nomor_kartu_custom TEXT,
                    slot INTEGER NOT NULL DEFAULT 1,
                    label TEXT NOT NULL DEFAULT 'Kartu 1',
                    created_at TEXT
                )
                """
            )

            # Migrasikan rfid_uid yang ada di santri ke kartu_santri jika belum ada
            connection.execute(
                """
                INSERT OR IGNORE INTO kartu_santri (santri_id, rfid_uid, nomor_kartu_custom, slot, label, created_at)
                SELECT id, rfid_uid, COALESCE(CAST(nomor_urut AS TEXT), ''), 1, 'Kartu 1', COALESCE(created_at, datetime('now'))
                FROM santri
                WHERE rfid_uid IS NOT NULL AND trim(rfid_uid) != ''
                """
            )

            absensi_cols = {row["name"] for row in connection.execute("PRAGMA table_info(absensi)").fetchall()}
            if "waktu_pulang" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN waktu_pulang TEXT")
            if "status_pulang" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN status_pulang TEXT")
            if "denda_menit" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN denda_menit INTEGER DEFAULT 0")
            if "nama_pengantar" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN nama_pengantar TEXT")
            if "nama_penjemput" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN nama_penjemput TEXT")
            if "alasan_tanpa_kartu" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN alasan_tanpa_kartu TEXT")
            if "alasan_penjemputan_tanpa_kartu" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN alasan_penjemputan_tanpa_kartu TEXT")

            if current["version"] < SCHEMA_VERSION:
                connection.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            elif current["version"] > SCHEMA_VERSION:
                raise RuntimeError("Versi database lebih baru dari aplikasi.")

        # View dan Trigger kompatibilitas nama tabel 'anak' dan 'kartu_anak'
        # Memungkinkan kueri SELECT, INSERT, UPDATE, dan DELETE dengan nama 'anak'
        # tanpa mengubah skema tabel fisik dan foreign key yang sudah ada.
        connection.executescript(
            """
            CREATE VIEW IF NOT EXISTS anak AS SELECT * FROM santri;

            CREATE TRIGGER IF NOT EXISTS trigger_insert_anak
            INSTEAD OF INSERT ON anak
            BEGIN
                INSERT INTO santri (id, nomor_urut, rfid_uid, nama, paket, extra_data, aktif, created_at)
                VALUES (new.id, new.nomor_urut, new.rfid_uid, new.nama, new.paket, new.extra_data, new.aktif, new.created_at);
            END;

            CREATE TRIGGER IF NOT EXISTS trigger_update_anak
            INSTEAD OF UPDATE ON anak
            BEGIN
                UPDATE santri SET
                    nomor_urut = new.nomor_urut,
                    rfid_uid = new.rfid_uid,
                    nama = new.nama,
                    paket = new.paket,
                    extra_data = new.extra_data,
                    aktif = new.aktif
                WHERE id = old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS trigger_delete_anak
            INSTEAD OF DELETE ON anak
            BEGIN
                DELETE FROM santri WHERE id = old.id;
            END;

            CREATE VIEW IF NOT EXISTS kartu_anak AS SELECT * FROM kartu_santri;

            CREATE TRIGGER IF NOT EXISTS trigger_insert_kartu_anak
            INSTEAD OF INSERT ON kartu_anak
            BEGIN
                INSERT INTO kartu_santri (id, santri_id, rfid_uid, nomor_kartu_custom, slot, label, created_at)
                VALUES (new.id, new.santri_id, new.rfid_uid, new.nomor_kartu_custom, new.slot, new.label, new.created_at);
            END;

            CREATE TRIGGER IF NOT EXISTS trigger_update_kartu_anak
            INSTEAD OF UPDATE ON kartu_anak
            BEGIN
                UPDATE kartu_santri SET
                    santri_id = new.santri_id,
                    rfid_uid = new.rfid_uid,
                    nomor_kartu_custom = new.nomor_kartu_custom,
                    slot = new.slot,
                    label = new.label
                WHERE id = old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS trigger_delete_kartu_anak
            INSTEAD OF DELETE ON kartu_anak
            BEGIN
                DELETE FROM kartu_santri WHERE id = old.id;
            END;
            """
        )


def reset_all_data(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM tap_log")
        connection.execute("DELETE FROM absensi")
        connection.execute("DELETE FROM kartu_santri")
        connection.execute("DELETE FROM santri")
        connection.execute("DELETE FROM custom_fields")
        connection.execute("DELETE FROM pengaturan")
        connection.execute("DELETE FROM sqlite_sequence WHERE name IN ('santri', 'kartu_santri', 'absensi', 'tap_log', 'custom_fields')")
        connection.commit()


def get_setting(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM pengaturan WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_setting(connection: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        connection.execute("DELETE FROM pengaturan WHERE key = ?", (key,))
    else:
        connection.execute(
            "INSERT INTO pengaturan (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
