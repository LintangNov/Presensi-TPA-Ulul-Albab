from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 2


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
                INSERT INTO schema_version (version) VALUES (2);
                """
            )
        else:
            # Migrasi skema jika tabel sudah ada dari versi sebelumnya
            santri_cols = {row["name"] for row in connection.execute("PRAGMA table_info(santri)").fetchall()}
            if "paket" not in santri_cols:
                connection.execute("ALTER TABLE santri ADD COLUMN paket TEXT NOT NULL DEFAULT 'A'")

            absensi_cols = {row["name"] for row in connection.execute("PRAGMA table_info(absensi)").fetchall()}
            if "waktu_pulang" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN waktu_pulang TEXT")
            if "status_pulang" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN status_pulang TEXT")
            if "denda_menit" not in absensi_cols:
                connection.execute("ALTER TABLE absensi ADD COLUMN denda_menit INTEGER DEFAULT 0")

            if current["version"] < SCHEMA_VERSION:
                connection.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            elif current["version"] > SCHEMA_VERSION:
                raise RuntimeError("Versi database lebih baru dari aplikasi.")


def reset_all_data(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM tap_log")
        connection.execute("DELETE FROM absensi")
        connection.execute("DELETE FROM santri")
        connection.execute("DELETE FROM custom_fields")
        connection.execute("DELETE FROM pengaturan")
        connection.execute("DELETE FROM sqlite_sequence WHERE name IN ('santri', 'absensi', 'tap_log', 'custom_fields')")
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
