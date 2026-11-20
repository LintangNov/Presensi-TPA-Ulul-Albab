from io import BytesIO

from openpyxl import load_workbook

from app.db import connect
from app.services.excel_io import export_workbook, preview_students, student_template
from app.services.reports import ReportService
from app.services.students import StudentService


def test_manual_attendance_and_alpha_summary(tmp_path):
    db_path = tmp_path / "report.db"
    students = StudentService(db_path)
    reports = ReportService(db_path)
    first = students.save_student(None, "Hadir", 1, {})
    second = students.save_student(None, "Alpha", 2, {})
    reports.save_manual(first, "2026-10-04", "Hadir", "07:00", "Tepat waktu")
    summary = reports.summary("2026-10-04", "2026-10-04")
    assert summary == [
        {"nomor_urut": 1, "nama": "Hadir", "Hadir": 1, "Izin": 0, "Sakit": 0, "Alpha": 0},
        {"nomor_urut": 2, "nama": "Alpha", "Hadir": 0, "Izin": 0, "Sakit": 0, "Alpha": 1},
    ]
    reports.save_manual(second, "2026-10-04", "Izin", None, "Sakit ringan")
    assert reports.summary("2026-10-04", "2026-10-04")[1]["Izin"] == 1
    with connect(db_path) as connection:
        attendance_id = connection.execute(
            "SELECT id FROM absensi WHERE santri_id = ?", (second,)
        ).fetchone()[0]
    reports.delete_manual(attendance_id)
    assert reports.summary("2026-10-04", "2026-10-04")[1]["Alpha"] == 1
    alpha_rows = reports.attendance_rows("2026-10-04", "2026-10-04", status="Alpha")
    assert [(row["nama"], row["status"]) for row in alpha_rows] == [("Alpha", "Alpha")]


def test_export_round_trip_has_two_sheets_and_custom_field(tmp_path):
    content = export_workbook(
        [
            {
                "tanggal": "2026-10-04",
                "nomor_urut": 1,
                "nama": "Alya",
                "waktu": "07:00",
                "status": "Hadir",
                "sumber": "manual",
                "catatan": "Baik",
                "extra_data": {"nama_wali": "Ibu Alya"},
            }
        ],
        [{"nomor_urut": 1, "nama": "Alya", "Hadir": 1, "Izin": 0, "Sakit": 0, "Alpha": 0}],
        [{"field_key": "nama_wali", "field_label": "Nama Wali"}],
    )
    workbook = load_workbook(BytesIO(content), data_only=True)
    assert workbook.sheetnames == ["Rekap", "Ringkasan"]
    assert workbook["Rekap"].freeze_panes == "A2"
    assert workbook["Rekap"]["P1"].value == "Nama Wali"
    assert workbook["Rekap"]["P2"].value == "Ibu Alya"
    assert workbook["Ringkasan"]["D2"].value == 0


def test_import_preview_valid_and_problem_rows(tmp_path):
    students = StudentService(tmp_path / "import.db")
    students.add_field("Nama Wali")
    workbook = load_workbook(BytesIO(student_template(students.fields(True))))
    sheet = workbook.active
    sheet.append([1, "Valid", "A", "Wali Valid"])
    sheet.append([2, "", "A", "Tanpa Nama"])
    sheet.append([3, "Valid", "B", "Duplikat"])
    output = BytesIO()
    workbook.save(output)

    preview = preview_students(output.getvalue(), students.fields(True))
    assert len(preview["rows"]) == 1
    assert len(preview["problems"]) == 2
    assert preview["rows"][0]["nama"] == "Valid"
    assert preview["rows"][0]["paket"] == "A"


def test_student_template_structure_and_guide_sheet(tmp_path):
    students = StudentService(tmp_path / "tmpl.db")
    students.add_field("Nama Orang Tua")
    content = student_template(students.fields(True))
    wb = load_workbook(BytesIO(content), data_only=True)

    assert wb.sheetnames == ["Data Anak", "Panduan Pengisian"]
    sheet = wb["Data Anak"]
    assert sheet.freeze_panes == "A2"

    headers = [cell.value for cell in sheet[1]]
    assert headers == ["Nomor", "Nama", "Paket", "Nama Orang Tua"]

    # Periksa baris contoh pengisian
    row2 = [cell.value for cell in sheet[2]]
    row3 = [cell.value for cell in sheet[3]]
    assert row2[0] == 1
    assert "Ahmad Fauzi" in row2[1]
    assert "(Contoh)" in row2[1]
    assert row2[2] == "A"

    assert row3[0] == 2
    assert "Fatimah" in row3[1]
    assert "(Contoh)" in row3[1]
    assert row3[2] == "B"

    # Periksa sheet Panduan Pengisian
    guide = wb["Panduan Pengisian"]
    guide_text = "\n".join(str(cell.value) for row in guide.iter_rows() for cell in row if cell.value)
    assert "PANDUAN PENGISIAN TEMPLATE EXCEL DATA ANAK" in guide_text
    assert "Sistem Presensi TPA Ulul Albab" in guide_text
    assert "Paket A" in guide_text
    assert "Paket B" in guide_text
    assert "Daftarkan RFID" in guide_text
    assert "Scanner USB" in guide_text


def test_preview_students_paket_and_number_validation(tmp_path):
    students = StudentService(tmp_path / "valid.db")
    fields = students.fields(True)

    wb = load_workbook(BytesIO(student_template(fields)))
    sheet = wb["Data Anak"]
    # Baris contoh otomatis dilewati oleh parser
    sheet.append([3, "Murid Paket A Biasa", "A"])
    sheet.append([4, "Murid Paket B Full Day", "Paket B"])
    sheet.append([5, "Murid Non-Integer", "A"])
    # Ganti nomor baris ke-5 menjadi tidak valid
    sheet.cell(row=6, column=1, value="1.5")
    sheet.append([3, "Murid Nomor Duplikat", "B"])

    bio = BytesIO()
    wb.save(bio)

    preview = preview_students(bio.getvalue(), fields)
    assert len(preview["rows"]) == 2
    assert preview["rows"][0]["nama"] == "Murid Paket A Biasa"
    assert preview["rows"][0]["paket"] == "A"
    assert preview["rows"][1]["nama"] == "Murid Paket B Full Day"
    assert preview["rows"][1]["paket"] == "B"

    assert any("bilangan bulat" in p for p in preview["problems"])
    assert any("nomor absen duplikat" in p for p in preview["problems"])

