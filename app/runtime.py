from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.db import connect, initialize, set_setting

if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
else:
    PROJECT_DIR = Path(__file__).resolve().parents[1]
    RESOURCE_DIR = PROJECT_DIR

DATA_DIR = PROJECT_DIR / "data"
BACKUP_DIR = DATA_DIR / "backup"
LOG_DIR = PROJECT_DIR / "logs"
DB_PATH = DATA_DIR / "tpa_absensi.db"


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("absensi_tpa")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


def backup_database(db_path: Path = DB_PATH) -> Path:
    """Create a consistent SQLite backup and retain only the 30 newest copies."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    initialize(db_path)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    destination = BACKUP_DIR / f"tpa_absensi_{stamp}.db"
    temporary = destination.with_suffix(".db.tmp")
    try:
        source = connect(db_path)
        target = connect(temporary)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        temporary.replace(destination)
        with connect(db_path) as connection:
            set_setting(connection, "backup_terakhir", datetime.now().astimezone().isoformat(timespec="seconds"))
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise

    backups = sorted(
        (item for item in BACKUP_DIR.glob("tpa_absensi_*.db") if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[30:]:
        old_backup.unlink()
    return destination


def last_backup(db_path: Path = DB_PATH) -> str | None:
    initialize(db_path)
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT value FROM pengaturan WHERE key = 'backup_terakhir'"
        ).fetchone()
    return row["value"] if row else None


def schedule_shutdown(delay: float = 0.5) -> None:
    def stop() -> None:
        logging.getLogger("absensi_tpa").info("Shutdown aplikasi diminta.")
        # signal.raise_signal schedules SIGINT on the main interpreter thread.
        import signal
        signal.raise_signal(signal.SIGINT)

    threading.Timer(delay, stop).start()


async def backup_loop(db_path: Path = DB_PATH) -> None:
    import asyncio

    while True:
        await asyncio.sleep(timedelta(hours=24).total_seconds())
        try:
            path = backup_database(db_path)
            logging.getLogger("absensi_tpa").info("Backup otomatis dibuat: %s", path)
        except Exception:
            logging.getLogger("absensi_tpa").exception("Backup otomatis gagal.")
