from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation


def _fit_columns(sheet) -> None:
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column) + 2
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(width, 40)


def export_workbook(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    fields: list[Any],
) -> bytes:
    workbook = Workbook()
    detail = workbook.active
    detail.title = "Rekap"
    field_headers = [field["field_label"] for field in fields]
    headers = [
        "Tanggal",
        "Nomor",
        "Nama",
        "Paket",
        "Jam Masuk",
        "Jam Pulang",
        "Nama Pengantar",
        "Nama Penjemput",
        "Alasan Masuk Tanpa Kartu",
        "Alasan Penjemputan Tanpa Kartu",
        "Status Pulang",
        "Denda (Menit)",
        "Status",
        "Sumber",
        "Catatan",
    ] + field_headers
    detail.append(headers)
    for cell in detail[1]:
        cell.font = Font(bold=True)
    for row in rows:
        extra = row.get("extra_data") or {}
        detail.append(
            [
                row.get("tanggal", ""),
                row.get("nomor_urut", ""),
                row.get("nama", ""),
                row.get("paket", "A"),
                row.get("waktu", "") or "-",
                row.get("waktu_pulang", "") or "-",
                row.get("nama_pengantar", "") or "",
                row.get("nama_penjemput", "") or "",
                row.get("alasan_tanpa_kartu", "") or "",
                row.get("alasan_penjemputan_tanpa_kartu", "") or "",
                row.get("status_pulang", "") or "-",
                row.get("denda_menit", 0),
                row.get("status", ""),
                row.get("sumber", ""),
                row.get("catatan", "") or "",
            ]
            + [extra.get(field["field_key"], "") for field in fields]
        )
    detail.freeze_panes = "A2"
    _fit_columns(detail)

    sheet = workbook.create_sheet("Ringkasan")
    sheet.append(["Nomor", "Nama", "Hadir", "Izin", "Sakit", "Alpha"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in summary:
        sheet.append(
            [row["nomor_urut"], row["nama"], row["Hadir"], row["Izin"], row["Sakit"], row["Alpha"]]
        )
    sheet.freeze_panes = "A2"
    _fit_columns(sheet)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def student_template(fields: list[Any]) -> bytes:
    workbook = Workbook()

    # SHEET 1: Data Anak (Lembar input utama)
    sheet = workbook.active
    sheet.title = "Data Anak"
    headers = ["Nomor", "Nama", "Paket"] + [field["field_label"] for field in fields]
    sheet.append(headers)

    header_fill = PatternFill(start_color="3283E7", end_color="3283E7", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E0"),
        right=Side(style="thin", color="CBD5E0"),
        top=Side(style="thin", color="CBD5E0"),
        bottom=Side(style="thin", color="CBD5E0"),
    )

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    sheet.row_dimensions[1].height = 28

    # Baris Contoh Pengisian (Baris 2 dan 3)
    ex_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    ex_font = Font(name="Segoe UI", size=10, italic=True, color="4A5568")
    ex_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    ex1 = [1, "Ahmad Fauzi (Contoh)", "A"] + [f"Contoh {field['field_label']}" for field in fields]
    ex2 = [2, "Fatimah Az-Zahra (Contoh)", "B"] + [f"Contoh {field['field_label']}" for field in fields]
    sheet.append(ex1)
    sheet.append(ex2)

    for row_idx in (2, 3):
        sheet.row_dimensions[row_idx].height = 22
        for col_idx, cell in enumerate(sheet[row_idx], 1):
            cell.fill = ex_fill
            cell.font = ex_font
            cell.border = ex_border
            if col_idx in (1, 3):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Dropdown Validation untuk kolom Paket
    paket_col_idx = headers.index("Paket") + 1
    paket_col_letter = get_column_letter(paket_col_idx)
    dv = DataValidation(type="list", formula1='"A,B"', allow_blank=True)
    dv.prompt = "Pilih 'A' (Half Day 06.30-13.00) atau 'B' (Full Day 06.30-16.00)"
    dv.promptTitle = "Pilihan Paket Anak"
    dv.error = "Nilai paket harus 'A' atau 'B'"
    dv.errorTitle = "Pilihan Paket Tidak Valid"
    sheet.add_data_validation(dv)
    dv.add(f"{paket_col_letter}2:{paket_col_letter}1000")

    sheet.freeze_panes = "A2"

    # Lebar kolom otomatis dengan batas minimum
    sheet.column_dimensions["A"].width = 12
    sheet.column_dimensions["B"].width = 30
    sheet.column_dimensions["C"].width = 14
    for idx, field in enumerate(fields, 4):
        sheet.column_dimensions[get_column_letter(idx)].width = max(len(str(field["field_label"])) + 6, 20)

    # SHEET 2: Panduan Pengisian
    guide = workbook.create_sheet("Panduan Pengisian")
    guide.views.sheetView[0].showGridLines = True

    guide.column_dimensions["A"].width = 18
    guide.column_dimensions["B"].width = 20
    guide.column_dimensions["C"].width = 16
    guide.column_dimensions["D"].width = 30
    guide.column_dimensions["E"].width = 52
    guide.column_dimensions["F"].width = 24

    # Judul
    guide["A2"] = "PANDUAN PENGISIAN TEMPLATE EXCEL DATA ANAK"
    guide["A2"].font = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
    guide["A3"] = "Sistem Presensi TPA Ulul Albab - Harap dibaca sebelum mengisi data"
    guide["A3"].font = Font(name="Segoe UI", size=10, italic=True, color="64748B")

    # Bagian 1: Spesifikasi Kolom
    guide["A5"] = "1. ATURAN & SPESIFIKASI SETIAP KOLOM"
    guide["A5"].font = Font(name="Segoe UI", size=11, bold=True, color="1E293B")

    t1_headers = ["Nama Kolom", "Status", "Tipe Data", "Format / Pilihan", "Keterangan", "Contoh Pengisian"]
    t1_row_start = 6
    guide.row_dimensions[t1_row_start].height = 24
    for col_idx, h_text in enumerate(t1_headers, 1):
        c = guide.cell(row=t1_row_start, column=col_idx, value=h_text)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border

    t1_rows = [
        [
            "Nomor",
            "Opsional / Disarankan",
            "Angka Bulat",
            "Angka unik (1, 2, 3...)",
            "Nomor absen anak. Otomatis disinkronkan ke nomor kartu fisik. Tidak boleh duplikat dengan anak lain di sistem.",
            "1",
        ],
        [
            "Nama",
            "Wajib Diisi",
            "Teks",
            "Nama lengkap anak",
            "Nama anak wajib diisi dan tidak boleh sama dengan anak yang sudah aktif di sistem.",
            "Ahmad Fauzi",
        ],
        [
            "Paket",
            "Wajib (Default A)",
            "Pilihan (A / B)",
            "A = Half Day | B = Full Day",
            "Menentukan jam operasional dan batas toleransi penjemputan anak (tersedia dropdown di lembar Data Anak).",
            "A",
        ],
    ]
    for field in fields:
        t1_rows.append([
            field["field_label"],
            "Opsional",
            "Teks Bebas",
            "Teks informasi tambahan",
            f"Kolom kustom: {field['field_label']}. Tersimpan dalam profil data anak.",
            f"Contoh {field['field_label']}",
        ])

    curr_row = t1_row_start + 1
    body_font = Font(name="Segoe UI", size=10, color="1E293B")
    for r_data in t1_rows:
        guide.row_dimensions[curr_row].height = 22
        for col_idx, val in enumerate(r_data, 1):
            c = guide.cell(row=curr_row, column=col_idx, value=val)
            c.font = body_font
            c.border = thin_border
            if col_idx in (1, 2, 3, 4, 6):
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        curr_row += 1

    # Bagian 2: Jam Operasional
    curr_row += 1
    guide.cell(row=curr_row, column=1, value="2. KETENTUAN JAM OPERASIONAL & PAKET ANAK").font = Font(
        name="Segoe UI", size=11, bold=True, color="1E293B"
    )
    curr_row += 1

    t2_headers = ["Paket", "Kategori", "Jam Masuk", "Jam Pulang", "Ketentuan Penjemputan", "Keterangan Toleransi"]
    teal_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    guide.row_dimensions[curr_row].height = 24
    for col_idx, h_text in enumerate(t2_headers, 1):
        c = guide.cell(row=curr_row, column=col_idx, value=h_text)
        c.fill = teal_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border
    curr_row += 1

    t2_rows = [
        [
            "Paket A",
            "Half Day",
            "06.30 WIB",
            "13.00 WIB",
            "Tap keluar diizinkan mulai 13.00 WIB",
            "Penjemputan setelah toleransi dihitung denda",
        ],
        [
            "Paket B",
            "Full Day",
            "06.30 WIB",
            "16.00 WIB",
            "Tap keluar diizinkan mulai 16.00 WIB",
            "Penjemputan setelah toleransi dihitung denda",
        ],
    ]
    for r_data in t2_rows:
        guide.row_dimensions[curr_row].height = 22
        for col_idx, val in enumerate(r_data, 1):
            c = guide.cell(row=curr_row, column=col_idx, value=val)
            c.font = body_font
            c.border = thin_border
            c.alignment = Alignment(horizontal="center", vertical="center")
        curr_row += 1

    # Bagian 3: Petunjuk Penting & Kartu RFID
    curr_row += 1
    guide.cell(row=curr_row, column=1, value="3. ATURAN PENTING & PENDAFTARAN KARTU RFID").font = Font(
        name="Segoe UI", size=11, bold=True, color="1E293B"
    )
    curr_row += 1

    notes = [
        "• Data Aman & Tidak Menimpa: Anak yang nama atau nomor absennya sudah terdaftar di sistem akan otomatis dilewati (data lama tidak dihapus/ditimpa).",
        "• Baris Contoh: Baris 2 dan 3 di sheet 'Data Anak' merupakan contoh pengisian bertanda '(Contoh)'. Anda dapat langsung menimpanya dengan data anak asli atau menghapusnya.",
        "• Pendaftaran Kartu RFID: Kartu RFID TIDAK diisi di Excel. Setelah data anak berhasil diimpor, daftarkan kartu RFID fisik melalui menu 'Data Anak' > tombol 'Daftarkan Kartu' (Daftarkan RFID) menggunakan alat Scanner USB.",
        "• Format Berkas: Pastikan berkas disimpan dalam format .xlsx sebelum diunggah kembali ke sistem presensi.",
    ]
    note_font = Font(name="Segoe UI", size=10, color="334155")
    for n in notes:
        c = guide.cell(row=curr_row, column=1, value=n)
        c.font = note_font
        curr_row += 1

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def preview_students(content: bytes, fields: list[Any]) -> dict[str, Any]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sheet = None
    for target in ["Data Anak", "Data Murid", "Anak", "Murid"]:
        if target in workbook.sheetnames:
            sheet = workbook[target]
            break
    if sheet is None:
        sheet = workbook.active

    headers = [str(value).strip() if value is not None else "" for value in next(sheet.iter_rows(values_only=True))]
    required = {"Nomor", "Nama"}
    if not required.issubset(headers):
        raise ValueError("Header Excel harus memiliki kolom Nomor dan Nama.")
    indexes = {header: index for index, header in enumerate(headers)}
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    seen_names: set[str] = set()
    seen_numbers: set[int] = set()

    for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        if not any(value not in (None, "") for value in values):
            continue

        name = str(values[indexes["Nama"]]).strip() if values[indexes["Nama"]] is not None else ""

        # Lewati baris contoh bawaan template jika belum dihapus/diganti
        if "(contoh)" in name.lower() or "[contoh]" in name.lower():
            continue

        raw_number = values[indexes["Nomor"]]
        parsed_number: int | None = None
        if raw_number not in (None, ""):
            try:
                num_float = float(str(raw_number).strip())
                if not num_float.is_integer():
                    problems.append(
                        f"Baris {row_number}: Nomor absen harus berupa bilangan bulat (ditemukan: {raw_number})."
                    )
                    continue
                parsed_number = int(num_float)
                if parsed_number < 1:
                    problems.append(
                        f"Baris {row_number}: Nomor absen harus bernilai 1 atau lebih besar (ditemukan: {raw_number})."
                    )
                    continue
            except (ValueError, TypeError):
                problems.append(
                    f"Baris {row_number}: Nomor absen harus berupa angka bulat (ditemukan: {raw_number})."
                )
                continue

        paket_val = "A"
        if "Paket" in indexes and values[indexes["Paket"]] is not None:
            raw_p = str(values[indexes["Paket"]]).strip().upper()
            if "B" in raw_p or "FULL" in raw_p:
                paket_val = "B"
            elif "A" in raw_p or "HALF" in raw_p:
                paket_val = "A"

        if not name:
            problems.append(f"Baris {row_number}: nama wajib diisi.")
            continue

        key = name.casefold()
        if key in seen_names:
            problems.append(f"Baris {row_number}: nama duplikat di file ({name}).")
            continue
        seen_names.add(key)

        if parsed_number is not None:
            if parsed_number in seen_numbers:
                problems.append(
                    f"Baris {row_number}: nomor absen duplikat di file ({parsed_number})."
                )
                continue
            seen_numbers.add(parsed_number)

        extra = {
            field["field_key"]: str(values[indexes[field["field_label"]]] or "").strip()
            for field in fields
            if field["field_label"] in indexes and values[indexes[field["field_label"]]] is not None
        }
        rows.append({
            "nama": name,
            "nomor_urut": parsed_number,
            "paket": paket_val,
            "extra_data": extra,
        })
    return {"rows": rows, "problems": problems}
