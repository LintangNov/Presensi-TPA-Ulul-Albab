# Absensi TPA - Catatan Pengembang

## Tahap 0: Prototipe jaringan dan hardware

Hasil uji lapangan: semua langkah berhasil pada Wi-Fi TPA dan hotspot laptop,
termasuk tanpa memasang `Install-Firewall.bat`. HP tidak dapat dicas sambil
terhubung ke reader melalui OTG, sehingga baterai harus cukup untuk satu sesi.

### Asumsi Tahap 0

- Reader terbukti dapat digunakan melalui OTG. Format UID yang lebih rinci
  tetap dapat dilihat pada log mentah di halaman scanner.
- `NoSleep.js` disimpan lokal di `app/static/js/nosleep.min.js` agar tidak ada
  CDN atau request internet dari aplikasi.
- IP privat yang terdeteksi dari Windows digunakan sebagai kandidat QR. Label
  adapter pada prototipe bersifat perkiraan sampai diuji di laptop TPA.

## CHECKLIST UJI LAPANGAN

Isi kolom hasil setelah pengujian langsung di lokasi TPA.

| Poin | Yang diuji | Hasil |
|---|---|---|
| a | HP dengan Wi-Fi TPA dapat membuka halaman laptop. Jika gagal, coba Mode 2 hotspot laptop. | berhasil |
| b | Reader terdeteksi lewat OTG. Catat format UID, termasuk awalan/akhiran, Enter, spasi, dan panjang karakter. | berhasil |
| c | Layar tetap menyala setelah menekan MULAI SESI. Catat apakah baterai cukup untuk satu sesi dan apakah HP dapat dicas sambil OTG. | baterai cukup, tapi hp tidak dapat dicas sambil OTG |
| d | HP tidak berpindah diam-diam ke data seluler saat digunakan. | berhasil |
| e | Tanpa `Install-Firewall.bat` koneksi gagal, lalu setelah aturan firewall dipasang koneksi berhasil. | berhasil tanpa install firewall.bat |

Catatan hasil lapangan:

semua langkah berhasil termasuk pengujian dengan wifi dan hotspot bahkan tanpa install firewall. Namun, HP tidak dapat dicas sambil OTG, sehingga baterai HP harus cukup untuk satu sesi.
______________________________________________________________________________

______________________________________________________________________________

## Tahap 1: Database dan API inti

Data aplikasi sekarang disimpan di `data/tpa_absensi.db`. UID dinormalisasi
dengan menghapus spasi di luar, mengubah huruf menjadi kapital, dan membuang
karakter non-alfanumerik di awal atau akhir. Ini sesuai hasil uji bahwa reader
mengirim UID lalu Enter; isi mentah tetap dapat dilihat pada log scanner.

Tombol scanner berubah menjadi **AKHIRI SESI** ketika sesi aktif, sehingga
NoSleep dapat dilepas secara jelas setelah pemakaian.

## Tahap 2: Halaman scanner lengkap

Halaman scanner sekarang memakai tampilan gelap, antrean `localStorage` per
alamat laptop, pengiriman ulang otomatis setiap 3 detik, `age_ms`, feedback
berwarna, getar/bunyi jika didukung perangkat, dan debounce kartu sama selama
1,5 detik. Tap disimpan lebih dahulu sebelum dicoba dikirim; tap tertunda tidak
dihapus sampai server menjawab.

## Tahap 3: Admin inti

Admin hanya dapat dibuka dari localhost. Halaman admin menyediakan dua kartu
jaringan (Wi-Fi TPA dan Hotspot Laptop), QR lokal, segarkan IP, status koneksi
HP, absensi hari ini dengan polling, CRUD santri, kolom tambahan, dan
pendaftaran kartu melalui tap HP. Pendaftaran kartu berlaku dua menit.

## Tahap 4: Absensi manual, rekap, dan Excel

Perhitungan Alpha memakai asumsi sederhana: “hari TPA” adalah tanggal yang
memiliki minimal satu catatan pada tabel absensi. Santri aktif yang tidak punya
catatan pada tanggal tersebut dihitung Alpha. Tanggal tanpa satu pun catatan
tidak dihitung sebagai hari TPA.

Impor Excel tidak menimpa data santri yang sudah ada. Nama yang sudah ada atau
duplikat dalam file ditampilkan sebagai masalah dan tidak ikut disimpan setelah
konfirmasi.

## Tahap 5: Pengemasan dan operasional

### Menjalankan aplikasi

Untuk komputer pengembang, `Start-Absensi.bat` memakai `.venv`. Untuk komputer
TPA, distribusikan isi folder `dist/AbsensiTPA` hasil PyInstaller bersama
`Start-Absensi.bat`, `Matikan-Absensi.bat`, dan `Install-Firewall.bat` pada satu
folder. Aplikasi tidak memerlukan Python di laptop TPA.

`Start-Absensi.bat` memeriksa port 8000 sampai 8010. Jika aplikasi sudah
berjalan, browser diarahkan ke instance tersebut sehingga tidak dibuat instance
ganda. Jika port 8000 sedang dipakai program lain, port berikutnya dipilih dan
alamat QR otomatis menggunakan port yang sedang menerima request.

Jalankan `Install-Firewall.bat` sekali dengan klik kanan **Run as
administrator**. Aturan mengizinkan TCP 8000–8010 pada profil jaringan Private
dan Public, sehingga Wi-Fi TPA dan hotspot laptop tercakup. Gunakan
`Matikan-Absensi.bat` untuk menghentikan server melalui endpoint shutdown yang
graceful, atau tombol **Matikan Aplikasi** pada menu **Pengaturan**.

### Backup dan restore database

Backup konsisten dibuat saat aplikasi mulai dan setiap 24 jam. Tombol
**Cadangkan sekarang** ada di **Pengaturan**. Tiga puluh file terbaru disimpan
di `data/backup/` dengan nama `tpa_absensi_YYYY-MM-DD_HH-MM-SS.db`; waktu
backup terakhir tampil di halaman Pengaturan. Log aplikasi berada di
`logs/app.log` dan berotasi otomatis (maksimal lima file lama).

Untuk restore:

1. Matikan aplikasi dengan `Matikan-Absensi.bat`.
2. Salin file backup yang dipilih dari `data\backup\` ke tempat aman.
3. Ganti nama database aktif menjadi `tpa_absensi_sebelum_restore.db` (jangan
   menghapusnya), termasuk memastikan tidak ada proses Python/AbsensiTPA yang
   masih berjalan.
4. Salin file backup pilihan ke `data\tpa_absensi.db`.
5. Hapus file sementara SQLite `data\tpa_absensi.db-shm` dan
   `data\tpa_absensi.db-wal` bila ada.
6. Jalankan `Start-Absensi.bat` dan periksa **Absensi Hari Ini**, **Data
   Santri**, serta **Rekap & Laporan**.

### Membuat paket PyInstaller

Di komputer yang memiliki Python dan `.venv`, jalankan `Build-Absensi.bat`.
Hasilnya adalah `dist\AbsensiTPA\` (mode onedir). Folder `app\templates` dan
`app\static` dimasukkan ke bundle; folder tulis `data\`, `data\backup\`, dan
`logs\` selalu dibuat di samping executable sehingga data tidak hilang ketika
paket diperbarui.

### Uji persis di laptop lain tanpa Python

1. Salin satu folder paket lengkap ke laptop Windows lain. Pastikan di dalamnya
   ada `AbsensiTPA.exe`, `Start-Absensi.bat`, `Matikan-Absensi.bat`, dan
   `Install-Firewall.bat`.
2. Pastikan laptop terhubung ke Wi-Fi TPA atau nyalakan Mobile hotspot.
3. Klik kanan `Install-Firewall.bat` lalu pilih **Run as administrator** dan
   pastikan selesai tanpa pesan gagal.
4. Jalankan `Start-Absensi.bat` dengan klik ganda. Browser harus terbuka ke
   `/admin`; buka menu Pengaturan dan pastikan waktu backup tampil.
5. Tambahkan satu santri, daftarkan kartu, lalu scan dari HP. Pastikan QR
   membuka `/scan` dan absensi muncul.
6. Tekan **Cadangkan sekarang**. Pastikan file baru muncul di
   `data\backup\` dan waktu berubah.
7. Jalankan `Start-Absensi.bat` lagi. Pastikan hanya satu server tetap berjalan.
8. Untuk uji port, tutup aplikasi lain yang memakai 8000, jalankan server
   tersebut, lalu jalankan `Start-Absensi.bat`; aplikasi harus pindah ke 8001
   atau port kosong berikutnya dan QR harus memakai port baru.
9. Uji `Matikan-Absensi.bat`, pastikan browser tidak lagi dapat membuka admin,
   lalu jalankan Start lagi.
10. Uji restore memakai salinan backup pada langkah di atas; data harus kembali
    tanpa error dan file `logs\app.log` mencatat operasi aplikasi.
