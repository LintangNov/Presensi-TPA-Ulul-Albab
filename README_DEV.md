# Absensi TPA - Catatan Pengembang USB-only

## Arsitektur

Aplikasi berjalan sepenuhnya di PC Windows:

- USB RFID reader tipe keyboard emulator dicolok langsung ke PC.
- FastAPI hanya bind ke `127.0.0.1`.
- Admin dibuka di browser pada `/admin`.
- Scanner dibuka sebagai jendela Edge app pada `/scan`.
- Tidak ada HP, OTG, Wi-Fi, hotspot, QR, atau aturan firewall.

`/api/ping` dipertahankan sebagai health-check lokal untuk script Windows.
Port utama adalah 8000; `Start-Absensi.bat` memakai port 8001 sampai 8010
bila port sebelumnya sedang dipakai.

## Menjalankan dari source

```text
Start-Absensi.bat
```

Script menjalankan server di loopback, membuka halaman admin, lalu membuka
jendela scanner terpisah dengan `msedge.exe --app`. Jika Edge tidak tersedia,
buka URL `/scan` secara manual di browser apa pun.

Gunakan `Matikan-Absensi.bat` untuk menghentikan aplikasi secara bersih.

## Cara kerja scanner

Reader mengirim karakter UID seperti keyboard dan mengakhiri UID dengan Enter.
Halaman scanner menangkap `keydown` di level `document`, bukan melalui input
field. Ketika jendela kehilangan fokus, scanner menampilkan:

> SCANNER TIDAK AKTIF - klik jendela ini

Tap tidak diantrikan ke jaringan karena server dan reader berada pada PC yang
sama. Hasil tap tetap memakai logika absensi lama: berhasil, duplikat, kartu
belum terdaftar, dan murid tidak aktif.

## Daftarkan Kartu

Pada halaman Data Murid, klik **Daftarkan Kartu**. Dialog akan memfokuskan
input, lalu reader mengirim UID dan Enter. Endpoint admin lokal menormalisasi
UID dan menolak kartu yang sudah dipakai murid lain. Setelah berhasil, dialog
tetap terbuka, input dikosongkan, dan fokus dikembalikan agar kartu berikutnya
dapat didaftarkan.

## Tes dan build

Jalankan tes:

```text
.venv\Scripts\python.exe -m pytest -q
```

Buat paket PyInstaller:

```text
Build-Absensi.bat
```

Distribusikan folder `dist\AbsensiTPA` bersama `Start-Absensi.bat` dan
`Matikan-Absensi.bat`. Jalankan build ulang setelah perubahan source; jangan
mengedit isi `dist` secara manual.

## Uji manual dengan reader asli

1. Jalankan Start dan pastikan admin serta scanner terbuka sebagai jendela
   terpisah.
2. Tambah murid tanpa UID, buka Daftarkan Kartu, tempel kartu, dan pastikan
   UID tampil setelah sukses.
3. Daftarkan kartu kedua tanpa menutup dialog.
4. Coba kartu yang sama pada murid lain dan pastikan pesan penolakan muncul.
5. Tap kartu terdaftar dan pastikan absensi berhasil.
6. Tap kartu yang sama sekali lagi dan pastikan hanya feedback “Sudah absen”.
7. Tap kartu yang belum terdaftar dan pastikan feedback yang benar.
8. Klik jendela admin saat scanner terbuka; pastikan peringatan scanner tidak
   aktif muncul dan karakter tidak diproses.
9. Klik kembali jendela scanner dan pastikan reader dapat dipakai lagi.
10. Pastikan data muncul di Absensi Hari Ini, rekap, dan export Excel.
11. Jalankan Matikan lalu Start kembali dan pastikan tidak ada instance ganda.
