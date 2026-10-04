@echo off
setlocal
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Skrip ini harus dijalankan sebagai Administrator.
  echo Klik kanan file ini, lalu pilih "Run as administrator".
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="Absensi TPA - Port 8000-8010" >nul 2>&1
netsh advfirewall firewall add rule name="Absensi TPA - Port 8000-8010" dir=in action=allow protocol=TCP localport=8000-8010 profile=private,public
if "%errorlevel%"=="0" (
  echo Aturan firewall Absensi TPA berhasil dibuat untuk profil Private dan Public.
) else (
  echo Aturan firewall gagal dibuat.
  pause
  exit /b 1
)
pause
