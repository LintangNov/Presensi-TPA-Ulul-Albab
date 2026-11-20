from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from app.db import connect, reset_all_data, get_setting, set_setting
from app.services.students import StudentService
from app.services.excel_io import export_workbook, preview_students, student_template
from app.services.reports import ReportService
from app.runtime import DB_PATH, backup_database, check_usb_scanner_connected, last_backup, schedule_shutdown
from app.services import scanner_simulator

students = StudentService(DB_PATH)
reports = ReportService(DB_PATH)
router = APIRouter()

IMPORT_PREVIEW_TTL_SECONDS = 600  # Pratinjau impor kedaluwarsa setelah 10 menit
MAX_IMPORT_PREVIEWS = 20  # Batas maksimal pratinjau di memori untuk mencegah DoS
import_previews: dict[str, dict[str, Any]] = {}

ALLOWED_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def verify_csrf(request: Request) -> None:
    """Periksa apakah request mutasi (POST, PUT, DELETE) bukan berasal dari serangan CSRF cross-site."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return

    # 1. Standar Fetch Metadata W3C (Sec-Fetch-Site)
    sec_fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if sec_fetch_site == "cross-site":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Permintaan lintas-asal (cross-site) tidak diizinkan.",
        )

    # 2. Validasi Header Origin jika ada (selalu dikirim oleh browser pada POST/Fetch)
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlparse(origin)
            if parsed.hostname not in ALLOWED_ORIGIN_HOSTS:
                raise HTTPException(
                    status_code=403,
                    detail="Akses ditolak: Origin tidak diizinkan.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=403,
                detail="Akses ditolak: Header Origin tidak valid.",
            )
    else:
        # 3. Validasi Header Referer jika Origin tidak dikirim browser
        referer = request.headers.get("referer")
        if referer:
            try:
                parsed = urlparse(referer)
                if parsed.hostname not in ALLOWED_ORIGIN_HOSTS:
                    raise HTTPException(
                        status_code=403,
                        detail="Akses ditolak: Referer tidak diizinkan.",
                    )
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    status_code=403,
                    detail="Akses ditolak: Header Referer tidak valid.",
                )


def cleanup_import_previews() -> None:
    """Bersihkan entri pratinjau impor yang kedaluwarsa atau melebihi batas kapasitas memori."""
    now = time.time()
    expired_keys = [
        key
        for key, val in list(import_previews.items())
        if now - val.get("_created_at", 0) > IMPORT_PREVIEW_TTL_SECONDS
    ]
    for key in expired_keys:
        import_previews.pop(key, None)

    if len(import_previews) >= MAX_IMPORT_PREVIEWS:
        sorted_keys = sorted(
            import_previews.keys(),
            key=lambda k: import_previews[k].get("_created_at", 0),
        )
        for key in sorted_keys[: len(import_previews) - MAX_IMPORT_PREVIEWS + 1]:
            import_previews.pop(key, None)


class RegisterCardRequest(BaseModel):
    uid: str
    slot: int = 1
    label: str | None = None


def local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Halaman ini hanya bisa dibuka dari pc admin.")
    verify_csrf(request)


def context(request: Request, **values: Any) -> dict[str, Any]:
    return {"request": request, **values}


def today_data() -> dict[str, Any]:
    today = datetime.now().astimezone().date().isoformat()
    parts = today.split("-")
    today_formatted = f"{parts[2]}/{parts[1]}/{parts[0]}"
    with connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT s.id, s.nomor_urut, s.nama, s.paket, s.aktif, a.id AS absensi_id, a.tanggal, "
            "a.waktu, a.waktu_pulang, a.status_pulang, a.denda_menit, a.status, a.sumber, a.catatan, "
            "a.nama_pengantar, a.nama_penjemput, a.alasan_tanpa_kartu, a.alasan_penjemputan_tanpa_kartu "
            "FROM santri s LEFT JOIN absensi a ON a.santri_id = s.id AND a.tanggal = ? "
            "ORDER BY s.nomor_urut, s.nama",
            (today,),
        ).fetchall()
        active_count = connection.execute(
            "SELECT COUNT(*) FROM santri WHERE aktif = 1"
        ).fetchone()[0]
        tap_count = connection.execute(
            "SELECT COUNT(*) FROM tap_log WHERE date(waktu_tap) = ?",
            (today,),
        ).fetchone()[0]
    present = [row for row in rows if row["status"] == "Hadir"]
    picked_up = [row for row in rows if row["waktu_pulang"] is not None]
    denda_list = [row for row in rows if (row["denda_menit"] or 0) > 0]
    absent = [row for row in rows if row["aktif"] and row["status"] is None]
    return {
        "today": today,
        "today_formatted": today_formatted,
        "rows": rows,
        "present_count": len(present),
        "picked_up_count": len(picked_up),
        "denda_count": len(denda_list),
        "active_count": active_count,
        "tap_count": tap_count,
        "absent": absent,
        "scanner_hardware": check_usb_scanner_connected(),
    }


@router.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    local_only(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context=context(request, title="Dashboard", **today_data()),
    )


@router.get("/admin/hari-ini", response_class=HTMLResponse)
async def today(request: Request):
    local_only(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/today.html",
        context=context(request, **today_data()),
    )


@router.post("/admin/absensi-manual")
async def save_manual(
    request: Request,
    student_id: int = Form(...),
    tanggal: str = Form(...),
    status: str = Form("Hadir"),
    waktu: str = Form(""),
    catatan: str = Form(""),
    waktu_pulang: str = Form(""),
    status_pulang: str = Form(""),
    denda_menit: int = Form(0),
    nama_pengantar: str = Form(""),
    nama_penjemput: str = Form(""),
    nama_pengantar_lainnya: str = Form(""),
    nama_penjemput_lainnya: str = Form(""),
    alasan_tanpa_kartu: str = Form(""),
    alasan_penjemputan_tanpa_kartu: str = Form(""),
    return_to: str = Form(""),
):
    local_only(request)
    target_url = "/admin" if return_to == "dashboard" else "/admin/hari-ini"
    # Normalisasi format tanggal DD/MM/YYYY ke YYYY-MM-DD jika diperlukan
    clean_tanggal = tanggal.strip()
    if "/" in clean_tanggal:
        t_parts = clean_tanggal.split("/")
        if len(t_parts) == 3 and len(t_parts[0]) <= 2 and len(t_parts[2]) == 4:
            clean_tanggal = f"{t_parts[2]}-{t_parts[1].zfill(2)}-{t_parts[0].zfill(2)}"

    # Normalisasi jam 24 jam (misal 07.00 atau 07:00 menjadi 07:00)
    clean_waktu = waktu.strip().replace(".", ":") if waktu else ""
    clean_waktu_pulang = waktu_pulang.strip().replace(".", ":") if waktu_pulang else ""

    # Jika dropdown dipilih "Lainnya", gunakan nilai dari input teks kustom
    final_nama_pengantar = nama_pengantar_lainnya or None if nama_pengantar == "Lainnya" else (nama_pengantar or None)
    final_nama_penjemput = nama_penjemput_lainnya or None if nama_penjemput == "Lainnya" else (nama_penjemput or None)
    try:
        reports.save_manual(
            student_id=student_id,
            tanggal=clean_tanggal,
            status=status,
            waktu=clean_waktu,
            catatan=catatan,
            waktu_pulang=clean_waktu_pulang or None,
            status_pulang=status_pulang or None,
            denda_menit=denda_menit,
            nama_pengantar=final_nama_pengantar,
            nama_penjemput=final_nama_penjemput,
            alasan_tanpa_kartu=alasan_tanpa_kartu or None,
            alasan_penjemputan_tanpa_kartu=alasan_penjemputan_tanpa_kartu or None,
        )
    except ValueError as exc:
        logging.getLogger("absensi_tpa").warning("Gagal menyimpan absensi manual: %s", exc)
        return RedirectResponse(target_url, status_code=303)
    return RedirectResponse(target_url, status_code=303)


@router.post("/admin/absensi-manual/{attendance_id}/hapus")
async def delete_manual(request: Request, attendance_id: int):
    local_only(request)
    reports.delete_manual(attendance_id)
    return RedirectResponse("/admin/hari-ini", status_code=303)


@router.get("/admin/rekap", response_class=HTMLResponse)
async def report_page(
    request: Request,
    mulai: str = "",
    sampai: str = "",
    student_id: int | None = None,
    santri_id: int | None = None,
    anak_id: int | None = None,
    status: str = "",
):
    local_only(request)
    today = datetime.now().astimezone().date().isoformat()
    mulai = mulai or today
    sampai = sampai or today
    active_student_id = student_id if student_id is not None else (anak_id if anak_id is not None else santri_id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/reports.html",
        context=context(
            request,
            title="Rekap & Laporan",
            rows=reports.attendance_rows(mulai, sampai, active_student_id, status or None),
            summary=reports.summary(mulai, sampai, active_student_id),
            students=students.list_students(),
            mulai=mulai,
            sampai=sampai,
            selected_student=active_student_id,
            selected_status=status,
        ),
    )


@router.get("/admin/rekap/export.xlsx")
async def export_report(
    request: Request,
    mulai: str = "",
    sampai: str = "",
    student_id: int | None = None,
    santri_id: int | None = None,
    anak_id: int | None = None,
    status: str = "",
):
    local_only(request)
    today = datetime.now().astimezone().date().isoformat()
    mulai = mulai or today
    sampai = sampai or today
    active_student_id = student_id if student_id is not None else (anak_id if anak_id is not None else santri_id)
    content = export_workbook(
        reports.attendance_rows(mulai, sampai, active_student_id, status or None),
        reports.summary(mulai, sampai, active_student_id),
        students.fields(active_only=True),
    )
    filename = f"absensi_TPA_{mulai}_sampai_{sampai}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/import", response_class=HTMLResponse)
async def import_page(request: Request):
    local_only(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/import.html",
        context=context(
            request,
            title="Impor Data Anak",
            preview=None,
            custom_fields=students.fields(active_only=True),
        ),
    )


@router.get("/admin/import/template.xlsx")
async def import_template(request: Request):
    local_only(request)
    return Response(
        content=student_template(students.fields(active_only=True)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="template_anak.xlsx"'},
    )


@router.post("/admin/import", response_class=HTMLResponse)
async def import_preview(request: Request, file: UploadFile = File(...)):
    local_only(request)
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Ukuran file terlalu besar. Maksimal 5 MB.")
    try:
        preview = preview_students(content, students.fields(active_only=True))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    existing_students = students.list_students()
    existing = {student["nama"].casefold() for student in existing_students}
    existing_numbers = {
        student["nomor_urut"] for student in existing_students if student["nomor_urut"] is not None
    }
    for row in preview["rows"]:
        if row["nama"].casefold() in existing:
            preview["problems"].append(f"Nama sudah ada: {row['nama']}. Baris tidak diimpor.")
        elif row["nomor_urut"] is not None and row["nomor_urut"] in existing_numbers:
            preview["problems"].append(
                f"Nomor urut sudah ada: {row['nomor_urut']}. Baris tidak diimpor."
            )
    preview["rows"] = [
        row for row in preview["rows"]
        if row["nama"].casefold() not in existing
        and (row["nomor_urut"] is None or row["nomor_urut"] not in existing_numbers)
    ]
    cleanup_import_previews()
    preview["_created_at"] = time.time()
    token = secrets.token_urlsafe(16)
    import_previews[token] = preview
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/import.html",
        context=context(
            request,
            title="Pratinjau Impor",
            preview=preview,
            token=token,
            custom_fields=students.fields(active_only=True),
        ),
    )


@router.post("/admin/import/konfirmasi")
async def confirm_import(request: Request, token: str = Form(...)):
    local_only(request)
    cleanup_import_previews()
    preview = import_previews.pop(token, None)
    if not preview:
        raise HTTPException(400, "Pratinjau impor sudah tidak berlaku atau kedaluwarsa.")
    for row in preview["rows"]:
        students.save_student(
            None,
            row["nama"],
            row["nomor_urut"],
            row["extra_data"],
            paket=row.get("paket", "A"),
        )
    return RedirectResponse("/admin/anak", status_code=303)


def student_redirect(request: Request) -> RedirectResponse:
    if request.url.path.startswith("/admin/murid"):
        dest = "/admin/murid"
    elif request.url.path.startswith("/admin/santri"):
        dest = "/admin/santri"
    else:
        dest = "/admin/anak"
    return RedirectResponse(dest, status_code=303)


@router.get("/admin/anak", response_class=HTMLResponse)
@router.get("/admin/santri", response_class=HTMLResponse)
@router.get("/admin/murid", response_class=HTMLResponse)
async def student_page(request: Request, q: str = "", page: int = 1):
    local_only(request)
    per_page = 15
    page = max(1, page)
    students_list, total_students = students.list_students_paginated(q, page=page, per_page=per_page)
    total_pages = max(1, (total_students + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        students_list, total_students = students.list_students_paginated(q, page=page, per_page=per_page)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/students.html",
        context=context(
            request,
            students=students_list,
            fields=students.fields(active_only=True),
            all_fields=students.fields(),
            search=q,
            edit_student=None,
            page=page,
            total_pages=total_pages,
            total_students=total_students,
            per_page=per_page,
        ),
    )


@router.post("/admin/anak")
@router.post("/admin/santri")
@router.post("/admin/murid")
async def add_student(
    request: Request,
    nama: str = Form(...),
    nomor_urut: str = Form(""),
    paket: str = Form("A"),
):
    local_only(request)
    data = await request.form()
    extra = {field["field_key"]: str(data.get(field["field_key"], "")) for field in students.fields(True)}
    number = int(nomor_urut) if nomor_urut.strip().isdigit() else None
    students.save_student(None, nama, number, extra, paket=paket)
    return student_redirect(request)


@router.post("/admin/anak/{student_id}")
@router.post("/admin/santri/{student_id}")
@router.post("/admin/murid/{student_id}")
async def edit_student(
    request: Request,
    student_id: int,
    nama: str = Form(...),
    nomor_urut: str = Form(""),
    paket: str = Form("A"),
):
    local_only(request)
    data = await request.form()
    extra = {field["field_key"]: str(data.get(field["field_key"], "")) for field in students.fields(True)}
    number = int(nomor_urut) if nomor_urut.strip().isdigit() else None
    students.save_student(student_id, nama, number, extra, paket=paket)
    return student_redirect(request)


@router.post("/admin/anak/{student_id}/hapus")
@router.post("/admin/santri/{student_id}/hapus")
@router.post("/admin/murid/{student_id}/hapus")
async def delete_student(request: Request, student_id: int):
    local_only(request)
    student = students.get_student(student_id)
    if not student:
        raise HTTPException(404, "Anak tidak ditemukan.")
    students.delete_student(student_id)
    return student_redirect(request)


@router.post("/admin/anak/{student_id}/aktif")
@router.post("/admin/santri/{student_id}/aktif")
@router.post("/admin/murid/{student_id}/aktif")
async def toggle_student(request: Request, student_id: int):
    local_only(request)
    student = students.get_student(student_id)
    if not student:
        raise HTTPException(404, "Anak tidak ditemukan.")
    students.set_active(student_id, not student["aktif"])
    return student_redirect(request)


@router.post("/api/admin/anak/{student_id}/daftar-kartu")
@router.post("/api/admin/santri/{student_id}/daftar-kartu")
@router.post("/api/admin/murid/{student_id}/daftar-kartu")
async def register_card(request: Request, student_id: int):
    local_only(request)
    payload = RegisterCardRequest.model_validate(await request.json())
    try:
        return students.register_card(student_id, payload.uid, slot=payload.slot, label=payload.label)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/admin/anak/{student_id}/kartu/{slot}/hapus")
@router.post("/api/admin/santri/{student_id}/kartu/{slot}/hapus")
@router.post("/api/admin/murid/{student_id}/kartu/{slot}/hapus")
async def delete_card_endpoint(request: Request, student_id: int, slot: int):
    local_only(request)
    try:
        students.delete_card(student_id, slot)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/admin/fields", response_class=HTMLResponse)
async def fields_page(request: Request, reset: str = "", saved: str = ""):
    local_only(request)
    with connect(DB_PATH) as connection:
        jeda_tap = get_setting(connection, "jeda_tap_pulang_menit") or "60"
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/fields.html",
        context=context(
            request,
            fields=students.fields(),
            backup_terakhir=last_backup(DB_PATH),
            reset_sukses=(reset == "sukses"),
            saved_sukses=(saved == "sukses"),
            jeda_tap_pulang=jeda_tap,
        ),
    )


@router.post("/admin/settings/presensi")
async def save_presensi_settings(request: Request, jeda_tap_pulang_menit: int = Form(60)):
    local_only(request)
    jeda_val = max(1, jeda_tap_pulang_menit)
    with connect(DB_PATH) as connection:
        set_setting(connection, "jeda_tap_pulang_menit", str(jeda_val))
    return RedirectResponse("/admin/fields?saved=sukses", status_code=303)


@router.post("/admin/fields")
async def add_field(request: Request, label: str = Form(...), urutan: int = Form(0)):
    local_only(request)
    students.add_field(label, urutan)
    return RedirectResponse("/admin/fields", status_code=303)


@router.post("/admin/fields/{field_id}/nonaktif")
async def disable_field(request: Request, field_id: int):
    local_only(request)
    students.set_field_active(field_id, False)
    return RedirectResponse("/admin/fields", status_code=303)


@router.post("/admin/fields/{field_id}")
async def update_field(
    request: Request,
    field_id: int,
    label: str = Form(...),
    urutan: int = Form(0),
):
    local_only(request)
    students.update_field(field_id, label, urutan)
    return RedirectResponse("/admin/fields", status_code=303)


@router.post("/admin/backup")
async def create_backup(request: Request):
    local_only(request)
    try:
        backup_database(DB_PATH)
    except Exception as exc:
        logging.getLogger("absensi_tpa").exception("Backup manual gagal.")
        raise HTTPException(500, f"Backup gagal: {exc}") from exc
    return RedirectResponse("/admin/fields", status_code=303)


@router.post("/admin/reset-data")
async def reset_data(request: Request, konfirmasi: str = Form("")):
    local_only(request)
    if konfirmasi.strip().upper() != "HAPUS":
        raise HTTPException(400, "Konfirmasi gagal. Ketik kata HAPUS untuk mereset seluruh data.")
    try:
        backup_database(DB_PATH)
    except Exception:
        logging.getLogger("absensi_tpa").exception("Backup sebelum reset gagal.")
    reset_all_data(DB_PATH)
    return RedirectResponse("/admin/fields?reset=sukses", status_code=303)


@router.post("/admin/matikan")
async def stop_application(request: Request):
    local_only(request)
    schedule_shutdown()
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Absensi TPA</title>"
        "<p>Aplikasi sedang dimatikan. Jendela ini boleh ditutup.</p>"
    )


@router.get("/api/admin/scanner-hardware")
async def scanner_hardware(request: Request):
    local_only(request)
    return check_usb_scanner_connected()


@router.get("/admin/simulator", response_class=HTMLResponse)
async def simulator_page(request: Request, page: int = 1):
    local_only(request)
    if not scanner_simulator.is_simulation_enabled():
        raise HTTPException(404, "Halaman tidak ditemukan.")
    per_page = 15
    page = max(1, page)
    students_page, total_students = scanner_simulator.get_students_page(page, per_page)
    total_pages = max(1, (total_students + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        students_page, total_students = scanner_simulator.get_students_page(page, per_page)
    all_students = scanner_simulator.get_all_students()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/simulator.html",
        context=context(
            request,
            title="Simulator RFID",
            simulator_enabled=scanner_simulator.is_simulation_enabled(),
            students=students_page,
            all_students=all_students,
            page=page,
            total_pages=total_pages,
            total_students=total_students,
            per_page=per_page,
        ),
    )


@router.get("/api/admin/scanner-simulator/status")
async def scanner_simulator_status(request: Request):
    local_only(request)
    return scanner_simulator.get_simulation_status()


class SimulateTapRequest(BaseModel):
    uid: str


@router.post("/api/admin/scanner-simulator/tap")
async def scanner_simulator_tap(request: Request):
    local_only(request)
    if not scanner_simulator.is_simulation_enabled():
        raise HTTPException(400, "Simulasi tidak tersedia. Jalankan dari source code tanpa card reader fisik.")
    payload = SimulateTapRequest.model_validate(await request.json())
    try:
        return scanner_simulator.simulate_tap(payload.uid)
    except Exception as exc:
        raise HTTPException(500, f"Gagal simulasi tap: {exc}") from exc


class SimulatorRegisterCardRequest(BaseModel):
    student_id: int
    uid: str
    slot: int = 1


@router.post("/api/admin/scanner-simulator/register-card")
async def scanner_simulator_register_card(request: Request):
    local_only(request)
    if not scanner_simulator.is_simulation_enabled():
        raise HTTPException(400, "Simulasi tidak tersedia. Jalankan dari source code tanpa card reader fisik.")
    payload = SimulatorRegisterCardRequest.model_validate(await request.json())
    try:
        return scanner_simulator.register_simulator_card(payload.student_id, payload.uid, slot=payload.slot)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/admin/status")
async def admin_status(request: Request):
    local_only(request)
    return today_data()
