# Sistem Presensi TPA Ulul Albab

Sistem presensi dan penjemputan anak berbasis komputer lokal (offline) untuk Tempat Penitipan Anak (TPA) Ulul Albab. Aplikasi menggunakan pembaca RFID USB bertipe keyboard emulator dan berjalan sepenuhnya di PC Windows tanpa memerlukan koneksi internet, perangkat telepon genggam, maupun konfigurasi jaringan eksternal.

Antarmuka sistem terbagi menjadi dua tampilan: panel pengelolaan untuk pengurus (admin) dan layar monitor TV LED untuk konfirmasi visual anak serta orang tua saat melakukan penempelan kartu.

---

## Arsitektur Sistem

Aplikasi dirancang dengan prinsip lokal penuh:

- Server lokal: Backend FastAPI berjalan pada host loopback `127.0.0.1` pada rentang port 8000 sampai 8010. Server menolak koneksi dari luar PC.
- Dua jendela independen:
  - Panel Admin: Dibuka di browser web melalui alamat `http://127.0.0.1:8000/admin`.
  - Display TV LED: Dibuka dalam jendela aplikasi terpisah melalui `msedge.exe --app=http://127.0.0.1:8000/scan`.
- Masukan RFID: Reader USB mengirimkan kode UID kartu layaknya ketikan keyboard yang diakhiri penekanan tombol Enter. Halaman pemindai menangkap sinyal tombol pada level dokumen tanpa memerlukan elemen formulir masukan teks.
- Deteksi fokus layar: Jendela pemindai menampilkan peringatan visual jika kehilangan fokus jendela, mencegah kegagalan pencatatan saat admin sedang mengoperasikan jendela lain.

---

## Fitur Utama

### 1. Presensi Masuk dan Penjemputan Otomatis
Pencatatan kehadiran anak menggunakan logika tap bertahap pada hari yang sama:
- Tap Pertama (Kedatangan): Dicatat sebagai presensi masuk. Jam operasional normal dimulai pukul 06:30. Kedatangan sebelum waktu tersebut diberi tanda keterangan khusus.
- Tap Kedua (Kepulangan): Dicatat sebagai waktu penjemputan anak. Sistem menerapkan batas jeda minimal (default 60 menit) atau menunggu waktu pulang paket agar kartu tidak terproses ganda secara tidak sengaja di pagi hari.
- Tap Ketiga dan Seterusnya: Dikenali sebagai duplikat dengan status informatif bahwa kepulangan anak sudah tercatat hari ini, sehingga data kehadiran tidak tertimpa.

### 2. Aturan Paket dan Denda Keterlambatan
Sistem menghitung keterlambatan penjemputan secara otomatis sesuai paket penitipan:
- Paket A (Half Day): Jam pulang 13:00 dengan batas toleransi 15 menit (sampai 13:15). Penjemputan setelah pukul 13:15 dihitung denda keterlambatan per menit.
- Paket B (Full Day): Jam pulang 16:00 dengan batas toleransi 15 menit (sampai 16:15). Penjemputan setelah pukul 16:15 dihitung denda keterlambatan per menit.

### 3. Dukungan Multi-Kartu per Anak
Setiap anak dapat memiliki hingga dua kartu RFID terdaftar (Slot 1 dan Slot 2). Fasilitas ini mengakomodasi kebutuhan penjemput yang berbeda, seperti kartu untuk ayah dan kartu untuk ibu.

### 4. Presensi Manual
Admin dapat mencatat kehadiran maupun kepulangan secara manual bagi anak yang tidak membawa kartu fisik. Formulir manual menyediakan pencatatan nama pengantar, nama penjemput, serta alasan ketidakhadiran fisik kartu.

### 5. Manajemen Data Anak dan Kolom Kustom (Custom Fields)
Pengurus dapat mengelola data anak melalui menu Data Anak (tambah, ubah, nonaktifkan, dan hapus) serta menambahkan kolom informasi tambahan dinamis (seperti nomor telepon wali atau alamat rumah) sesuai kebutuhan lembaga.

### 6. Impor dan Ekspor Data Excel
- Template Excel terstandarisasi untuk pendaftaran data anak secara massal.
- Validasi data impor dengan halaman pratinjau sebelum perubahan disimpan ke dalam basis data.
- Ekspor rekapitulasi presensi harian, bulanan, dan rentang tanggal kustom ke dalam format workbook `.xlsx`.

### 7. Keamanan dan Ketahanan Data
- Proteksi CSRF berbasis spesifikasi W3C Fetch Metadata (`Sec-Fetch-Site`) serta validasi header `Origin` dan `Referer` terbatas pada alamat loopback.
- Basis data SQLite menggunakan mode WAL (Write-Ahead Logging), isolasi transaksi, dan waktu tunggu sibuk 5.000 ms.
- Pencadangan otomatis (backup) dibuat setiap aplikasi dimulai dan berulang setiap 24 jam ke folder `data/backup/`, mempertahankan 30 salinan terbaru secara bergilir.
- Pencatatan log sistem menggunakan berkas berputar (rotating log) di folder `logs/app.log`.

### 8. Simulator Pemindai
Halaman simulator tersedia di `/admin/simulator` untuk menguji alur presensi dan pendaftaran kartu melalui antarmuka web tanpa harus menyambungkan perangkat keras RFID reader.

---

## Persyaratan Sistem

### Perangkat Keras
- Komputer atau laptop dengan sistem operasi Windows 10 atau Windows 11 (64-bit).
- Pembaca kartu RFID USB tipe HID / Keyboard Emulator (frekuensi 13.56 MHz atau 125 kHz sesuai jenis kartu yang digunakan).
- Port USB yang berfungsi stabil.
- Monitor tambahan atau TV LED sebagai layar penampil publik (opsional, disarankan).

### Perangkat Lunak
- Microsoft Edge terpasang untuk menjalankan jendela scanner dalam mode aplikasi mandiri (`--app`). Jika Edge tidak tersedia, halaman dapat dibuka melalui Google Chrome atau Mozilla Firefox.
- Tidak diperlukan instalasi Python atau perangkat lunak server tambahan untuk versi terdistribusi (hasil build).

---

## Panduan Pengoperasian

### 1. Menjalankan Aplikasi
1. Sambungkan pembaca RFID USB ke port komputer.
2. Klik ganda berkas `Start-Absensi.bat`.
3. Skrip akan mendeteksi port kosong (8000-8010), menjalankan server lokal di latar belakang, membuka panel admin di peramban utama, dan membuka jendela display pemindai.

### 2. Menutup Aplikasi
Gunakan salah satu cara berikut untuk menghentikan aplikasi secara aman:
- Klik ganda berkas `Matikan-Absensi.bat`.
- Buka menu Admin > Pengaturan > Operasional Aplikasi, lalu klik tombol **Matikan Aplikasi**.

Hindari menutup paksa jendela konsol saat proses pembacaan kartu sedang berlangsung.

---

## Alur Operasional Harian

### A. Pendaftaran Kartu Anak
1. Buka menu **Data Anak** pada panel admin.
2. Tambahkan data anak baru atau pilih anak yang belum memiliki kartu.
3. Klik tombol **Daftarkan Kartu** pada baris yang dipilih.
4. Tempelkan kartu fisik pada pembaca USB. Sistem akan menangkap UID kartu dan menyimpannya ke slot kartu yang dipilih.

### B. Presensi Masuk (Pagi)
1. Posisikan jendela pemindai (`/scan`) di monitor TV LED. Pastikan jendela tersebut aktif (terfokus).
2. Anak atau pengantar menempelkan kartu pada pembaca RFID.
3. Layar TV menampilkan nama anak, waktu masuk, serta status berhasil.

### C. Penjemputan Anak (Siang atau Sore)
1. Penjemput menempelkan kartu pada pembaca RFID.
2. Sistem memverifikasi waktu kepulangan anak.
3. Jika penjemputan masih dalam batas toleransi paket, layar menampilkan status kepulangan tepat waktu.
4. Jika penjemputan melewati batas toleransi, layar menampilkan durasi keterlambatan beserta keterangan denda yang berlaku.

---

## Panduan Pengembangan

### Menyiapkan Lingkungan Lokal

Prasyarat pengembangan: Python 3.11 atau versi lebih baru terpasang di sistem.

1. Buka terminal pada direktori proyek.
2. Buat virtual environment:
   ```cmd
   python -m venv .venv
   ```
3. Aktifkan virtual environment:
   ```cmd
   .venv\Scripts\activate
   ```
4. Pasang seluruh dependensi:
   ```cmd
   pip install -r requirements.txt
   ```

### Menjalankan Server Pengembangan

Jalankan perintah berikut dari direktori root:

```cmd
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Akses layanan melalui peramban:
- Panel Admin: `http://127.0.0.1:8000/admin`
- Tampilan Pemindai: `http://127.0.0.1:8000/scan`
- Simulator Pengujian: `http://127.0.0.1:8000/admin/simulator`

### Menjalankan Rangkaian Pengujian

Jalankan pengujian otomatis menggunakan pytest:

```cmd
pytest -q
```

Rangkaian pengujian mencakup verifikasi logika presensi, perhitungan toleransi dan denda keterlambatan, paginasi data, ekspor laporan Excel, serta validasi keamanan admin.

### Membangun Paket Distribusi (PyInstaller)

Untuk mengompilasi aplikasi menjadi paket biner portabel:

```cmd
Build-Absensi.bat
```

Hasil kompilasi tersimpan pada folder `dist\AbsensiTPA`. Untuk mendistribusikan ke komputer tujuan, salin folder `dist\AbsensiTPA` bersama berkas `Start-Absensi.bat` dan `Matikan-Absensi.bat`.

---

## Struktur Direktori

```text
AbsensiTPA/
|-- app/
|   |-- routers/
|   |   `-- admin.py              # Endpoint rute admin, impor, ekspor, dan pengaturan
|   |-- services/
|   |   |-- attendance.py         # Logika presensi masuk, penjemputan, dan denda
|   |   |-- excel_io.py           # Pemrosesan impor template dan ekspor laporan Excel
|   |   |-- reports.py            # Agregasi data rekapitulasi kehadiran
|   |   |-- scanner_simulator.py  # Utilitas simulator tap kartu
|   |   `-- students.py           # Pengelolaan data anak, kartu, dan kolom kustom
|   |-- static/                   # Aset CSS lokal, berkas JavaScript, dan pustaka antarmuka
|   |-- templates/
|   |   |-- admin/                # Template halaman pengelolaan admin
|   |   `-- scan.html             # Template tampilan layar pemindai TV LED
|   |-- db.py                     # Koneksi SQLite, skema tabel, dan migrasi versi
|   |-- main.py                   # Inisialisasi aplikasi FastAPI dan lifecycle
|   |-- runtime.py                # Konfigurasi path, rotasi backup, dan logging
|-- data/                         # Direktori basis data lokal SQLite (dibuat otomatis)
|   |-- backup/                   # Salinan cadangan otomatis basis data
|   `-- tpa_absensi.db            # Berkas utama basis data SQLite
|-- logs/
|   `-- app.log                   # Berkas log aplikasi
|-- tests/                        # Rangkaian berkas pengujian otomatis pytest
|-- AbsensiTPA.spec               # Spesifikasi kompilasi PyInstaller
|-- Build-Absensi.bat             # Skrip batch kompilasi aplikasi
|-- CARA-INSTALL.txt              # Panduan instalasi dan deployment untuk pengguna akhir
|-- Matikan-Absensi.bat           # Skrip batch penghentian server lokal
|-- README.md                     # Dokumentasi utama proyek
|-- README_DEV.md                 # Catatan teknis pengembang
|-- requirements.txt              # Daftar pustaka dependensi Python
`-- Start-Absensi.bat             # Skrip batch peluncuran aplikasi lokal
```

---

## Lisensi dan Hak Cipta

Proyek ini dikembangkan untuk kebutuhan operasional Tempat Penitipan Anak (TPA) Ulul Albab. Seluruh hak cipta dan kepemilikan kode sumber berada di bawah pengelolaan tim pengembang TPA.
