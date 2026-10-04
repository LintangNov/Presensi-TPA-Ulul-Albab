from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from app.db import connect
from app.services.students import StudentService
from app.services.excel_io import export_workbook, preview_students, student_template
from app.services.reports import ReportService
from app.runtime import DB_PATH, backup_database, last_backup, schedule_shutdown

students = StudentService(DB_PATH)
reports = ReportService(DB_PATH)
router = APIRouter()
import_previews: dict[str, dict[str, Any]] = {}


class RegisterCardRequest(BaseModel):
    uid: str


def local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Halaman ini hanya bisa dibuka dari laptop admin.")


def context(request: Request, **values: Any) -> dict[str, Any]:
    return {"request": request, **values}


def today_data() -> dict[str, Any]:
    today = datetime.now().astimezone().date().isoformat()
    with connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT s.id, s.nomor_urut, s.nama, s.aktif, a.id AS absensi_id, a.tanggal, "
            "a.waktu, a.status, a.sumber, a.catatan "
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
    absent = [row for row in rows if row["aktif"] and row["status"] is None]
    return {
        "rows": rows,
        "present_count": len(present),
        "active_count": active_count,
        "tap_count": tap_count,
        "absent": absent,
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
    status: str = Form(...),
    waktu: str = Form(""),
    catatan: str = Form(""),
):
    local_only(request)
    reports.save_manual(student_id, tanggal, status, waktu, catatan)
    return RedirectResponse("/admin/hari-ini", status_code=303)


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
    santri_id: int | None = None,
    status: str = "",
):
    local_only(request)
    today = datetime.now().astimezone().date().isoformat()
    mulai = mulai or today
    sampai = sampai or today
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/reports.html",
        context=context(
            request,
            title="Rekap & Laporan",
            rows=reports.attendance_rows(mulai, sampai, santri_id, status or None),
            summary=reports.summary(mulai, sampai, santri_id),
            students=students.list_students(),
            mulai=mulai,
            sampai=sampai,
            selected_student=santri_id,
            selected_status=status,
        ),
    )


@router.get("/admin/rekap/export.xlsx")
async def export_report(
    request: Request,
    mulai: str = "",
    sampai: str = "",
    santri_id: int | None = None,
    status: str = "",
):
    local_only(request)
    today = datetime.now().astimezone().date().isoformat()
    mulai = mulai or today
    sampai = sampai or today
    content = export_workbook(
        reports.attendance_rows(mulai, sampai, santri_id, status or None),
        reports.summary(mulai, sampai, santri_id),
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
        context=context(request, title="Impor Data Santri", preview=None),
    )


@router.get("/admin/import/template.xlsx")
async def import_template(request: Request):
    local_only(request)
    return Response(
        content=student_template(students.fields(active_only=True)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="template_santri.xlsx"'},
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
    import secrets

    token = secrets.token_urlsafe(16)
    import_previews[token] = preview
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/import.html",
        context=context(request, title="Pratinjau Impor", preview=preview, token=token),
    )


@router.post("/admin/import/konfirmasi")
async def confirm_import(request: Request, token: str = Form(...)):
    local_only(request)
    preview = import_previews.pop(token, None)
    if not preview:
        raise HTTPException(400, "Pratinjau impor sudah tidak berlaku.")
    for row in preview["rows"]:
        students.save_student(None, row["nama"], row["nomor_urut"], row["extra_data"])
    return RedirectResponse("/admin/santri", status_code=303)


@router.get("/admin/santri", response_class=HTMLResponse)
async def student_page(request: Request, q: str = ""):
    local_only(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/students.html",
        context=context(
            request,
            students=students.list_students(q),
            fields=students.fields(active_only=True),
            all_fields=students.fields(),
            search=q,
            edit_student=None,
        ),
    )


@router.post("/admin/santri")
async def add_student(
    request: Request,
    nama: str = Form(...),
    nomor_urut: str = Form(""),
):
    local_only(request)
    data = await request.form()
    extra = {field["field_key"]: str(data.get(field["field_key"], "")) for field in students.fields(True)}
    number = int(nomor_urut) if nomor_urut.strip().isdigit() else None
    students.save_student(None, nama, number, extra)
    return RedirectResponse("/admin/santri", status_code=303)


@router.post("/admin/santri/{student_id}")
async def edit_student(
    request: Request,
    student_id: int,
    nama: str = Form(...),
    nomor_urut: str = Form(""),
):
    local_only(request)
    data = await request.form()
    extra = {field["field_key"]: str(data.get(field["field_key"], "")) for field in students.fields(True)}
    number = int(nomor_urut) if nomor_urut.strip().isdigit() else None
    students.save_student(student_id, nama, number, extra)
    return RedirectResponse("/admin/santri", status_code=303)


@router.post("/admin/santri/{student_id}/aktif")
async def toggle_student(request: Request, student_id: int):
    local_only(request)
    student = students.get_student(student_id)
    if not student:
        raise HTTPException(404, "Santri tidak ditemukan.")
    students.set_active(student_id, not student["aktif"])
    return RedirectResponse("/admin/santri", status_code=303)


@router.post("/api/admin/santri/{student_id}/daftar-kartu")
async def register_card(request: Request, student_id: int):
    local_only(request)
    payload = RegisterCardRequest.model_validate(await request.json())
    try:
        return students.register_card(student_id, payload.uid)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/admin/fields", response_class=HTMLResponse)
async def fields_page(request: Request):
    local_only(request)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin/fields.html",
        context=context(request, fields=students.fields(), backup_terakhir=last_backup(DB_PATH)),
    )


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


@router.post("/admin/matikan")
async def stop_application(request: Request):
    local_only(request)
    schedule_shutdown()
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><title>Absensi TPA</title>"
        "<p>Aplikasi sedang dimatikan. Jendela ini boleh ditutup.</p>"
    )


@router.get("/api/admin/status")
async def admin_status(request: Request):
    local_only(request)
    return today_data()
